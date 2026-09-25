"""The pool: accounting that has to balance, and rules that have to bind.

Two kinds of test here. The accounting ones are ordinary correctness: value
does not appear or vanish, and the ledger replays to the balance. The rule ones
are the interesting half, because a pool that never refuses anything is not
underwriting, it is gambling with other people's capital.
"""

from __future__ import annotations

import pytest

from clause.pricing import PricingEngine
from clause.protocol import Pool, PoolError, PolicyStatus, build_policy, settle_index
from conftest import FLIGHT_DATE

TRIALS = 3_000


@pytest.fixture()
def pool() -> Pool:
    return Pool(engine=PricingEngine(trials=TRIALS, seed=5))


def funded(pool: Pool, amount: float = 4_000_000.0) -> Pool:
    pool.deposit("lp.one", amount * 0.6)
    pool.deposit("lp.two", amount * 0.4)
    return pool


# ---------------------------------------------------------------------------
# Capital
# ---------------------------------------------------------------------------


def test_the_first_deposit_prices_shares_at_one(pool: Pool) -> None:
    shares = pool.deposit("lp.one", 1_000_000)
    assert shares == pytest.approx(1_000_000)
    assert pool.share_price == pytest.approx(1.0)
    assert pool.balance == pytest.approx(1_000_000)


def test_later_deposits_buy_in_at_the_current_price(pool: Pool) -> None:
    pool.deposit("lp.one", 1_000_000)
    # Premium arriving lifts the value of a share before the next provider.
    pool.balance += 100_000
    shares = pool.deposit("lp.two", 1_100_000)
    assert pool.share_price == pytest.approx(1.1)
    assert shares == pytest.approx(1_000_000)


def test_a_provider_cannot_withdraw_more_than_they_hold(pool: Pool) -> None:
    pool.deposit("lp.one", 500_000)
    with pytest.raises(PoolError, match="holds"):
        pool.withdraw("lp.one", 900_000)


def test_an_unknown_account_cannot_withdraw(pool: Pool) -> None:
    with pytest.raises(PoolError, match="no shares"):
        pool.withdraw("stranger", 1.0)


def test_deposits_and_withdrawals_must_be_positive(pool: Pool) -> None:
    with pytest.raises(PoolError):
        pool.deposit("lp.one", 0)
    pool.deposit("lp.one", 100)
    with pytest.raises(PoolError):
        pool.withdraw("lp.one", -1)


def test_capital_behind_live_policies_cannot_leave(pool: Pool) -> None:
    """The rule that makes the pool's capital actually capital.

    The provider here holds most of the pool, so their full stake is larger
    than what the live book leaves free. A provider holding a small share could
    walk out without touching the rule, which is correct: their capital is not
    what the policies are leaning on.
    """
    pool.deposit("lp.major", 1_600_000)
    pool.deposit("lp.minor", 400_000)

    # Write until the book is leaning on a real share of the capital.
    for index in range(6):
        try:
            pool.write(
                peril_key="earthquake",
                subject={"location": "IST-KADIKOY", "radius_km": 50},
                limit=200_000, term_days=365, holder=f"buyer{index}",
            )
        except PoolError:
            break

    free = pool.free_capital()
    assert 0 < free < pool.balance

    major = pool.providers["lp.major"]
    assert major.shares * pool.share_price > free, "setup must actually bind"

    with pytest.raises(PoolError, match="standing behind"):
        pool.withdraw("lp.major", major.shares)

    # What is genuinely free still comes out.
    released = pool.withdraw("lp.major", (free * 0.5) / pool.share_price)
    assert released == pytest.approx(free * 0.5, rel=1e-6)


# ---------------------------------------------------------------------------
# Underwriting rules
# ---------------------------------------------------------------------------


def test_a_pool_with_no_capital_writes_nothing(pool: Pool) -> None:
    allowed, reasons = pool.can_write(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365,
    )
    assert not allowed
    assert any("capital" in reason for reason in reasons)


def test_the_concentration_limit_stops_a_pile_up(pool: Pool) -> None:
    """A pool can be solvent on average and one earthquake from nothing."""
    funded(pool, 2_000_000)

    written = 0
    for index in range(20):
        try:
            pool.write(
                peril_key="earthquake",
                subject={"location": "IST-KADIKOY", "radius_km": 50},
                limit=250_000, term_days=365, holder=f"buyer{index}",
            )
            written += 1
        except PoolError as error:
            assert "concentration" in str(error)
            break
    else:
        pytest.fail("the concentration limit never bound")

    assert written >= 1
    worst = pool.largest_single_event_loss()
    assert worst <= pool.balance * pool.concentration_limit * 1.05


def test_spreading_the_book_lets_the_pool_write_more(pool: Pool) -> None:
    """Diversification is not a slogan here, it buys capacity."""
    funded(pool, 2_000_000)
    places = ["IST-KADIKOY", "IZM-KONAK", "ADY-MERKEZ", "ANK-CANKAYA"]

    written = 0
    for index in range(20):
        try:
            pool.write(
                peril_key="earthquake",
                subject={"location": places[index % 4], "radius_km": 50},
                limit=250_000, term_days=365, holder=f"buyer{index}",
            )
            written += 1
        except PoolError:
            break

    assert written >= 4


def test_writing_a_policy_takes_the_premium_in(pool: Pool) -> None:
    funded(pool, 3_000_000)
    before = pool.balance
    policy = pool.write(
        peril_key="drought",
        subject={"station": "TR-KONYA", "distance_km": 8, "hectares": 50},
        limit=80_000, term_days=150, holder="farm",
    )
    assert pool.balance == pytest.approx(before + policy.premium)
    assert pool.premiums_earned == pytest.approx(policy.premium)
    assert policy.status is PolicyStatus.ACTIVE


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------


def test_a_triggered_policy_is_paid_from_the_pool(pool: Pool) -> None:
    funded(pool, 3_000_000)
    policy = pool.write(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=200_000, term_days=365, holder="buyer",
    )
    before = pool.balance

    paid = pool.pay(policy, 7.2)
    assert paid == pytest.approx(200_000)
    assert pool.balance == pytest.approx(before - 200_000)
    assert policy.status is PolicyStatus.PAID
    assert policy.settled_index == 7.2
    assert "without a claim" in policy.settlement_note


def test_a_partial_trigger_pays_its_band(pool: Pool) -> None:
    funded(pool, 3_000_000)
    policy = pool.write(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=200_000, term_days=365, holder="buyer",
    )
    assert pool.pay(policy, 5.6) == pytest.approx(50_000)


def test_an_index_below_attachment_pays_nothing(pool: Pool) -> None:
    funded(pool, 3_000_000)
    policy = pool.write(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=200_000, term_days=365, holder="buyer",
    )
    with pytest.raises(PoolError, match="pays nothing"):
        pool.pay(policy, 4.9)


def test_a_policy_settles_once(pool: Pool) -> None:
    funded(pool, 3_000_000)
    policy = pool.write(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365, holder="buyer",
    )
    pool.pay(policy, 7.2)
    with pytest.raises(PoolError, match="already"):
        pool.pay(policy, 7.2)
    with pytest.raises(PoolError, match="already"):
        pool.lapse(policy)


def test_lapsing_closes_a_policy_without_paying(pool: Pool) -> None:
    funded(pool, 3_000_000)
    policy = pool.write(
        peril_key="drought",
        subject={"station": "TR-EDIRNE", "distance_km": 5, "hectares": 60},
        limit=70_000, term_days=150, holder="farm",
    )
    before = pool.balance
    pool.lapse(policy)
    assert policy.status is PolicyStatus.LAPSED
    assert pool.balance == before


def test_a_dead_source_returns_the_premium(pool: Pool) -> None:
    """The case most parametric designs leave undefined."""
    funded(pool, 3_000_000)
    policy = pool.write(
        peril_key="drought",
        subject={"station": "TR-SANLIURFA", "distance_km": 20, "hectares": 40},
        limit=55_000, term_days=140, holder="farm",
    )
    before = pool.balance

    refund = pool.expire(policy)
    assert refund == pytest.approx(policy.premium)
    assert pool.balance == pytest.approx(before - policy.premium)
    assert pool.premiums_earned == pytest.approx(0.0, abs=1e-6)
    assert policy.status is PolicyStatus.EXPIRED
    assert "returned in full" in policy.settlement_note


def test_the_pool_says_so_when_it_cannot_pay(pool: Pool) -> None:
    funded(pool, 3_000_000)
    policy = pool.write(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=300_000, term_days=365, holder="buyer",
    )
    pool.balance = 1_000.0
    with pytest.raises(PoolError, match="is owed"):
        pool.pay(policy, 7.2)


# ---------------------------------------------------------------------------
# Accounting
# ---------------------------------------------------------------------------


def test_the_ledger_replays_to_the_balance(pool: Pool) -> None:
    funded(pool, 4_000_000)
    written = []
    for index, (peril, subject, limit, term) in enumerate([
        ("earthquake", {"location": "IST-KADIKOY", "radius_km": 50}, 150_000, 365),
        ("drought", {"station": "TR-KONYA", "distance_km": 8, "hectares": 50}, 80_000, 150),
        ("flight_delay", {"route": "TK-IST-LHR", "flight_number": "TK1", "departure_date": FLIGHT_DATE}, 1_500, 2),
    ]):
        written.append(
            pool.write(
                peril_key=peril, subject=subject, limit=limit,
                term_days=term, holder=f"h{index}",
            )
        )

    pool.pay(written[0], 7.2)
    pool.expire(written[1])
    pool.lapse(written[2])
    pool.withdraw("lp.two", 100_000 / pool.share_price)

    pool.check_ledger()
    assert pool.balance == pytest.approx(pool.ledger[-1].balance_after)


def test_a_broken_ledger_is_caught(pool: Pool) -> None:
    funded(pool, 1_000_000)
    pool.balance += 12_345  # value from nowhere
    with pytest.raises(PoolError, match="ledger sums"):
        pool.check_ledger()


def test_the_summary_adds_up(pool: Pool) -> None:
    funded(pool, 3_000_000)
    policy = pool.write(
        peril_key="earthquake",
        subject={"location": "IZM-KONAK", "radius_km": 50},
        limit=120_000, term_days=365, holder="buyer",
    )
    summary = pool.summary()
    assert summary["open_policies"] == 1
    assert summary["limit_at_risk"] == pytest.approx(120_000)
    assert summary["premiums_earned"] == pytest.approx(policy.premium)
    assert summary["free_capital"] <= summary["balance"]
    assert summary["solvency_ratio"] > 0


def test_the_risk_view_groups_what_pays_together(pool: Pool) -> None:
    funded(pool, 4_000_000)
    pool.write(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365, holder="b0",
    )
    # Düzce is a hundred and eighty kilometres away and on the same fault. The
    # grouping has to see that, because one rupture sequence is one exposure
    # however far apart the towns are.
    pool.write(
        peril_key="earthquake",
        subject={"latitude": 40.84, "longitude": 31.16, "radius_km": 50},
        limit=100_000, term_days=365, holder="b1",
    )
    pool.write(
        peril_key="drought",
        subject={"station": "TR-KONYA", "distance_km": 8, "hectares": 50},
        limit=60_000, term_days=150, holder="farm",
    )

    view = pool.risk_view()
    assert view["accumulation"]["earthquake on North Anatolian Fault"] == pytest.approx(
        200_000
    )
    assert view["accumulation"]["drought at TR-KONYA"] == pytest.approx(60_000)
    assert view["exceedance_curve"]


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


def test_a_policy_carries_its_predicate_and_its_deadline() -> None:
    policy = build_policy(
        peril_key="drought",
        subject={"station": "TR-KONYA", "distance_km": 8, "hectares": 50},
        limit=80_000, term_days=150, holder="farm",
        premium=1000, expected_loss=800, risk_load=150,
        expense_load=50, marginal_capital=5000,
        now=1_800_000_000.0,
    )
    assert "window_closed" in policy.predicate
    assert policy.data_reference in policy.predicate
    assert policy.settlement_deadline_days == 14
    assert policy.deadline_at == pytest.approx(policy.ends_at + 14 * 86400)


def test_policy_identifiers_are_distinct() -> None:
    made = [
        build_policy(
            peril_key="earthquake",
            subject={"location": "IST-KADIKOY", "radius_km": 50},
            limit=100_000, term_days=365, holder=f"h{i}",
            premium=1, expected_loss=1, risk_load=0,
            expense_load=0, marginal_capital=0, now=1_800_000_000.0 + i,
        )
        for i in range(8)
    ]
    assert len({policy.policy_id for policy in made}) == 8


def test_settle_index_uses_the_converted_curve_for_drought() -> None:
    """A drought curve is written in shares of normal and settled in millimetres."""
    policy = build_policy(
        peril_key="drought",
        subject={"station": "TR-KONYA", "distance_km": 8, "hectares": 50},
        limit=100_000, term_days=150, holder="farm",
        premium=1, expected_loss=1, risk_load=0,
        expense_load=0, marginal_capital=0,
    )
    # Konya's normal is 118 mm, so forty percent of normal is about 47 mm.
    assert settle_index(policy, 47.2) == pytest.approx(100_000, rel=1e-3)
    assert settle_index(policy, 200.0) == 0.0


# ---------------------------------------------------------------------------
# The price the buyer was shown
# ---------------------------------------------------------------------------


def test_a_policy_is_refused_rather_than_bound_above_the_agreed_price() -> None:
    """A quote and a bind are two different moments, and the book moves between.

    Pricing again at bind time is correct: the premium depends on what the pool
    already carries, and that changes while a buyer is deciding. But it is also
    a way to charge more than the figure on the screen, which is the oldest
    trick in the trade. So a buyer names the most they agreed to pay, and a
    price that has moved past it refuses the policy instead of writing it.
    """
    pool = funded(Pool(engine=PricingEngine(trials=TRIALS, seed=5)), 3_000_000)
    terms = dict(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=200_000, term_days=365, holder="buyer",
    )
    shown = pool.quote(**{k: v for k, v in terms.items() if k != "holder"}).premium

    # A price that has moved past what was agreed: refused, and nothing taken.
    with pytest.raises(PoolError, match="the price moved"):
        pool.write(**terms, max_premium=shown * 0.5)
    assert not pool.policies
    assert pool.balance == pytest.approx(3_000_000)

    # The price the buyer was actually shown: it binds, at no more than that.
    bound = pool.write(**terms, max_premium=shown)
    assert bound.premium <= shown + 1e-9


def test_naming_no_price_still_binds_at_whatever_the_book_says() -> None:
    """The guard is the buyer's to raise, not a new requirement on everyone."""
    pool = funded(Pool(engine=PricingEngine(trials=TRIALS, seed=5)), 3_000_000)
    policy = pool.write(
        peril_key="earthquake",
        subject={"location": "ANK-CANKAYA", "radius_km": 50},
        limit=100_000, term_days=365, holder="buyer",
    )
    assert policy.premium > 0


def test_a_price_rounded_down_for_display_is_still_the_price_agreed() -> None:
    """The quote shows cents; the pool prices to many places. Agreeing to the
    figure shown must be enough to buy at it."""
    from clause.protocol.pool import Pool
    from clause.pricing.engine import PricingEngine

    pool = Pool(engine=PricingEngine(trials=800, seed=3))
    pool.deposit("lp", 5_000_000)
    subject = {"location": "IST-KADIKOY", "radius_km": 50.0}
    quote = pool.quote(peril_key="earthquake", subject=subject, limit=50_000, term_days=365) \
        if hasattr(pool, "quote") else None
    premium = quote.premium if quote is not None else None
    if premium is None:
        return
    import math
    shown = math.floor(premium * 100) / 100     # the worst case: displayed rounded down
    assert shown < premium
    policy = pool.write(peril_key="earthquake", subject=subject, limit=50_000, term_days=365,
                        holder="0xbuyer", max_premium=shown)
    assert abs(policy.premium - premium) < 0.01


def test_one_rupture_cannot_take_the_whole_pool() -> None:
    """The rule that was missing, and the one the old name hid.

    The pool capped the worst modelled *year* at 35% of capital -- one order
    statistic out of twenty thousand trials -- through a method called
    ``largest_single_event_loss``, which is not what it measured. Nothing
    asked what a single rupture takes. At the top of an earthquake's curve
    every magnitude policy on the fault pays its whole limit at once, so the
    aggregate on one fault is the loss from one event there, with no modelling
    left to do and no diversification to hope for.

    Each policy below passes every other test. Together they are one
    earthquake.
    """
    from clause.pricing import PricingEngine
    from clause.protocol.pool import Pool

    pool = Pool(engine=PricingEngine(trials=800, seed=3))
    pool.deposit("lp", 2_000_000)
    istanbul = {"location": "IST-KADIKOY", "radius_km": 50}

    written = 0
    refusal = ""
    while written < 40:
        allowed, reasons = pool.can_write(
            peril_key="earthquake", subject=dict(istanbul), limit=80_000,
            term_days=365)
        if not allowed:
            refusal = " ".join(reasons)
            break
        pool.write(peril_key="earthquake", subject=dict(istanbul), limit=80_000,
                   term_days=365, holder="holder", simulated=True)
        written += 1

    assert refusal, "the pool took forty policies on one fault without a word"
    assert "pays together" in refusal
    assert "for one event" in refusal

    zone, held = pool.zone_exposure()
    assert "Fault" in zone or "earthquake" in zone
    assert held <= pool.balance * pool.zone_limit, (
        f"{held:,.0f} in force on {zone} against a cap of "
        f"{pool.balance * pool.zone_limit:,.0f}")
    # And it bound before the worst-modelled-year rule did, which is the whole
    # point: that rule was satisfied all the way through.
    assert "concentration limit" not in refusal


def test_cover_somewhere_else_does_not_fill_the_same_zone() -> None:
    """The limit is on what pays together, not on how much is written."""
    from clause.pricing import PricingEngine
    from clause.protocol.pool import Pool

    pool = Pool(engine=PricingEngine(trials=800, seed=3))
    pool.deposit("lp", 2_000_000)
    for where in ("IST-KADIKOY", "ANK-CANKAYA", "IZM-KONAK"):
        for _ in range(3):
            pool.write(peril_key="earthquake",
                       subject={"location": where, "radius_km": 50},
                       limit=80_000, term_days=365, holder="holder",
                       simulated=True)

    zones = pool.accumulation()
    assert len(zones) >= 2, f"three cities landed in one zone: {zones}"
    assert max(zones.values()) < sum(zones.values()), "no zone holds the whole book"


def test_premium_taken_for_cover_not_yet_given_is_not_capital() -> None:
    """Every premium was booked as the pool's own money the moment it was
    taken. The part of it that belongs to days the policy has not run is owed
    back if the cover is cancelled and owed to the risk if it is not, so it is
    a liability and not capital standing behind anybody else's policy.

    The capacity rules measured themselves against the whole balance, which
    meant each policy paid for the capacity to write the next one.
    """
    from clause.pricing import PricingEngine
    from clause.protocol.pool import Pool

    pool = Pool(engine=PricingEngine(trials=400, seed=3))
    pool.deposit("lp", 1_000_000)
    assert pool.unearned_premium() == 0.0
    assert pool.own_funds() == pytest.approx(1_000_000)

    policy = pool.write(peril_key="earthquake",
                        subject={"location": "ANK-CANKAYA", "radius_km": 25},
                        limit=50_000, term_days=365, holder="holder",
                        simulated=True)
    # Taken today, earned over the year: none of it is earned yet.
    assert pool.balance == pytest.approx(1_000_000 + policy.premium)
    assert pool.unearned_premium() == pytest.approx(policy.premium, abs=0.02)
    assert pool.own_funds() == pytest.approx(1_000_000, abs=0.02), (
        "the pool counted its own sale as the capital behind the next one")

    # Halfway through the term, half of it has been earned.
    half = policy.starts_at + (policy.ends_at - policy.starts_at) / 2
    assert pool.unearned_premium(half) == pytest.approx(policy.premium / 2, rel=0.02)
    # And once it is over, none of it is owed to that cover any more.
    assert pool.unearned_premium(policy.ends_at + 1) == 0.0


def test_the_bordereau_does_not_book_a_tax_of_zero_it_never_computed() -> None:
    """The column held a hardcoded 0.0 for every policy in every country,
    which reads as a figure somebody worked out. This protocol's own branch
    table puts earthquake in Yangın ve Doğal Afetler, the fire branch, and
    the fire insurance tax under Law 2464 is ten per cent of the premium."""
    from clause.protocol.bordereaux import premium_tax

    owed, basis = premium_tax("TR", "earthquake", 1_000.0)
    assert owed == pytest.approx(100.0)
    assert "2464" in basis

    # Where nothing is owed it is a zero with nothing behind it, and says so.
    assert premium_tax("TR", "flight_delay", 1_000.0) == (0.0, "")
    assert premium_tax("DE", "earthquake", 1_000.0) == (0.0, "")
