"""The chain: predicates waking, settling, and running out of time.

The last test in this file is the one that matters most. A parametric protocol
has two models of the world inside it: the one it prices against, and the one
it settles against. If they disagree, the protocol is either overcharging its
buyers or walking towards insolvency, and neither shows up in any other test.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from clause.chain import Chain, ChainConfig
from clause.chain.world import BLOCK_TIME_SECONDS
from clause.perils import DROUGHT, EARTHQUAKE, FLIGHT_DELAY
from clause.pricing import PricingEngine
from clause.protocol import Pool, PolicyStatus
from conftest import FLIGHT_DATE

KONYA = "api.meteo.example/v1/station/TR-KONYA/cumulative"
URFA = "api.meteo.example/v1/station/TR-SANLIURFA/cumulative"
KADIKOY = "api.seismic.example/v1/max-magnitude?lat=40.99&lon=29.03&radius_km=50"

# The world runs faster than wall time, so a term of so many days is a fixed
# number of blocks. Deriving it here means the clock can be retuned without
# quietly turning these tests into tests of the block budget.
_GRACE_DAYS = 45.0


def blocks_for(term_days: float, config: ChainConfig | None = None) -> int:
    """Blocks enough to cover a term plus its settlement deadline."""
    config = config or ChainConfig(seed=0)
    per_block = BLOCK_TIME_SECONDS * config.world_acceleration / 86400.0
    return int((term_days + _GRACE_DAYS) / per_block) + 200


def built(seed: int = 3, trials: int = 2_000, capital: float = 20_000_000.0):
    pool = Pool(engine=PricingEngine(trials=trials, seed=seed))
    pool.deposit("lp", capital)
    return pool, Chain(pool, ChainConfig(seed=seed))


def write(pool: Pool, chain: Chain, peril: str, subject: dict, limit: float, term: float):
    policy = pool.write(
        peril_key=peril, subject=subject, limit=limit,
        term_days=term, holder="holder",
    )
    chain.register(policy)
    return policy


# ---------------------------------------------------------------------------
# Registration and waking
# ---------------------------------------------------------------------------


def test_buying_a_policy_arms_a_predicate() -> None:
    pool, chain = built()
    policy = write(pool, chain, "earthquake", {"location": "IST-KADIKOY", "radius_km": 50}, 100_000, 365)

    assert len(chain.armed) == 1
    armed = next(iter(chain.armed.values()))
    assert armed.policy_id == policy.policy_id
    assert f"edge:{policy.data_reference}" in armed.keys


def test_only_policies_reading_a_moved_signal_are_evaluated() -> None:
    """The narrowing step, which is why the chain can hold a large book."""
    pool, chain = built()
    for index in range(4):
        write(pool, chain, "earthquake", {"location": "ANK-CANKAYA", "radius_km": 25}, 50_000, 365)

    before = chain._evaluations
    for _ in range(40):
        chain.produce_block()
    after = chain._evaluations

    # Far fewer than one evaluation per policy per block.
    assert after - before < 4 * 40


def test_an_attested_reading_wakes_exactly_its_own_policies() -> None:
    pool, chain = built()
    quake = write(pool, chain, "earthquake", {"location": "IST-KADIKOY", "radius_km": 50}, 100_000, 365)
    other = write(pool, chain, "earthquake", {"location": "IZM-KONAK", "radius_km": 50}, 100_000, 365)

    chain.attest(KADIKOY, "max_magnitude", 7.2)
    through_window(chain)

    assert pool.policies[quake.policy_id].status is PolicyStatus.PAID
    assert pool.policies[other.policy_id].status is PolicyStatus.ACTIVE


def through_window(chain, attested=True) -> None:
    from clause.chain.world import CONFIRM_HOURS, BLOCK_TIME_SECONDS
    per_block = BLOCK_TIME_SECONDS * chain.config.world_acceleration / 3600.0
    import math
    for _ in range(math.ceil(CONFIRM_HOURS["earthquake"] / per_block) + 3):
        chain.produce_block()


def test_attesting_an_unknown_source_returns_nothing() -> None:
    _, chain = built()
    assert chain.attest("api.nowhere.example/v1/x", "value", 1.0) is None


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------


def test_a_trigger_pays_the_band_the_structure_specifies() -> None:
    pool, chain = built()
    policy = write(pool, chain, "earthquake", {"location": "IST-KADIKOY", "radius_km": 50}, 200_000, 365)

    chain.attest(KADIKOY, "max_magnitude", 5.8)
    through_window(chain)

    settled = pool.policies[policy.policy_id]
    assert settled.status is PolicyStatus.PAID
    assert settled.payout == pytest.approx(50_000)  # the 25% band


def test_one_event_settles_every_policy_inside_its_circle() -> None:
    """Correlation, as the capital model prices it, actually happening."""
    pool, chain = built()
    policies = [
        write(pool, chain, "earthquake", {"location": "IST-KADIKOY", "radius_km": 50}, 100_000, 365)
        for _ in range(3)
    ]

    chain.attest(KADIKOY, "max_magnitude", 7.2)
    settled_in = set()
    for _ in range(chain.confirm_blocks(policies[0]) + 4):
        block = chain.produce_block()
        for item in block["settlements"]:
            settled_in.add(item["block_number"])

    assert all(pool.policies[p.policy_id].status is PolicyStatus.PAID for p in policies)
    assert pool.claims_paid == pytest.approx(300_000)
    # All in one block: they are one event, not three coincidences.
    assert len(settled_in) == 1


def test_settlement_runs_when_the_confirmation_window_closes() -> None:
    """Not in the block the reading landed any more: the first figure waits a
    stated window for revisions, and the payment runs in the block it ends."""
    pool, chain = built()
    policy = write(pool, chain, "earthquake", {"location": "IST-KADIKOY", "radius_km": 50}, 100_000, 365)

    chain.attest(KADIKOY, "max_magnitude", 7.2)
    chain.produce_block()
    assert pool.policies[policy.policy_id].status is PolicyStatus.ACTIVE
    assert pool.policies[policy.policy_id].metadata.get("provisional")
    story = chain.lineage(policy.policy_id)
    assert story["provisional"] is not None
    through_window(chain)

    paid = [s for s in chain.settlements if s.kind == "paid"]
    assert paid
    window = chain.confirm_blocks(policy)
    assert all(window <= item.latency_blocks <= window + 1 for item in paid)
    assert "provisional" not in pool.policies[policy.policy_id].metadata


def test_a_trigger_the_sources_withdraw_does_not_pay() -> None:
    """A magnitude revised below the trigger inside the window sends the policy
    back to waiting instead of paying on a figure nobody stands behind."""
    pool, chain = built()
    policy = write(pool, chain, "earthquake", {"location": "IST-KADIKOY", "radius_km": 50}, 100_000, 365)
    chain.attest(KADIKOY, "max_magnitude", 5.6)
    chain.produce_block()
    assert pool.policies[policy.policy_id].metadata.get("provisional")
    reading = chain.readings[KADIKOY]
    reading.fields["max_magnitude"] = 5.3      # the network's revision
    through_window(chain, attested=False)
    settled = pool.policies[policy.policy_id]
    assert settled.status is PolicyStatus.ACTIVE
    assert settled.metadata.get("withdrawn_trigger")
    assert any(a.policy_id == policy.policy_id for a in chain.armed.values())


def test_a_drought_does_not_settle_before_the_window_closes() -> None:
    """The guard that separates insurance from a bet on the weather so far."""
    pool, chain = built()
    policy = write(
        pool, chain, "drought",
        {"station": "TR-KONYA", "distance_km": 6, "hectares": 50}, 80_000, 150,
    )

    # A total far below the trigger, but the season is still running.
    chain.attest(KONYA, "rainfall_mm", 10.0, final=False)
    for _ in range(5):
        chain.produce_block()
    assert pool.policies[policy.policy_id].status is PolicyStatus.ACTIVE

    # Now the window closes on that total.
    chain.attest(KONYA, "window_closed", 1, final=False)
    chain.attest(KONYA, "rainfall_mm", 10.0)
    for _ in range(3):
        chain.produce_block()
    assert pool.policies[policy.policy_id].status is PolicyStatus.PAID


def test_a_term_that_ends_untriggered_lapses() -> None:
    pool, chain = built()
    policy = write(
        pool, chain, "flight_delay",
        {"route": "TK-IST-LHR", "flight_number": "TK1", "departure_date": FLIGHT_DATE},
        1_500, 2,
    )
    before = pool.balance

    for _ in range(blocks_for(2)):
        chain.produce_block()
        if pool.policies[policy.policy_id].status is not PolicyStatus.ACTIVE:
            break

    settled = pool.policies[policy.policy_id]
    assert settled.status in {PolicyStatus.LAPSED, PolicyStatus.PAID}
    if settled.status is PolicyStatus.LAPSED:
        assert pool.balance == pytest.approx(before)


def test_a_source_that_goes_quiet_returns_the_premium() -> None:
    """The failure most parametric designs leave undefined."""
    pool, chain = built()
    policy = write(
        pool, chain, "drought",
        {"station": "TR-SANLIURFA", "distance_km": 20, "hectares": 40}, 55_000, 140,
    )
    chain.silence(URFA)
    before = pool.balance

    for _ in range(blocks_for(140)):
        chain.produce_block()
        if pool.policies[policy.policy_id].status is not PolicyStatus.ACTIVE:
            break

    settled = pool.policies[policy.policy_id]
    assert settled.status is PolicyStatus.EXPIRED
    assert pool.balance == pytest.approx(before - policy.premium)
    assert pool.refunds_paid == pytest.approx(policy.premium)
    assert any(item.kind == "expired" for item in chain.settlements)


def test_a_quiet_source_is_visible_before_it_expires() -> None:
    pool, chain = built()
    write(
        pool, chain, "drought",
        {"station": "TR-SANLIURFA", "distance_km": 20, "hectares": 40}, 55_000, 140,
    )
    chain.silence(URFA)
    chain.produce_block()

    rows = chain.pending()
    assert rows
    assert rows[0]["source_silent"] is True


def test_the_pool_ledger_survives_a_full_run() -> None:
    pool, chain = built()
    for index in range(4):
        write(pool, chain, "earthquake", {"location": "IZM-KONAK", "radius_km": 50}, 80_000, 365)
    write(pool, chain, "drought", {"station": "TR-KONYA", "distance_km": 6, "hectares": 50}, 60_000, 150)

    for _ in range(blocks_for(150)):
        chain.produce_block()

    pool.check_ledger()


def test_blocks_are_retained_within_a_bound() -> None:
    pool = Pool(engine=PricingEngine(trials=500, seed=1))
    chain = Chain(pool, ChainConfig(seed=1, retain_blocks=200))
    for _ in range(700):
        chain.produce_block()
    assert len(chain.blocks) <= 200


# ---------------------------------------------------------------------------
# The two models have to agree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "peril, subject, term, level",
    [
        ("earthquake", {"location": "IST-KADIKOY", "radius_km": 50.0}, 365, 5.5),
        # None: the trigger level comes from the converted curve.
        ("drought", {"station": "TR-KONYA", "distance_km": 6.0, "hectares": 50.0}, 150, None),
    ],
)
def test_the_chain_settles_at_the_frequency_the_price_assumes(
    peril: str, subject: dict, term: float, level: float | None
) -> None:
    """The check that keeps the protocol coherent.

    Pricing believes one thing about how often an index triggers. The chain
    produces its own world and settles against that. If the two drift apart,
    every premium quoted is wrong in the same direction, and nothing else in
    this suite would notice.

    The bound is the sampling error of the count itself rather than a number
    chosen to fit. Seventy runs of a one in sixteen event is a noisy estimate,
    and a tolerance tighter than that noise would only be testing the seed.
    """
    runs = 70
    engine = PricingEngine(trials=800, seed=2)

    if peril == "earthquake":
        validated = EARTHQUAKE.validate_subject(subject)
        modelled = EARTHQUAKE.exceedance(validated, term)(level)
    else:
        validated = DROUGHT.validate_subject(subject)
        curve = DROUGHT.curve_in_mm(validated, DROUGHT.default_curve())
        modelled = DROUGHT.exceedance(validated, term)(curve.attachment)

    outcomes: Counter[str] = Counter()
    for run in range(runs):
        pool = Pool(engine=engine)
        pool.deposit("lp", 50_000_000)
        chain = Chain(pool, ChainConfig(seed=9_000 + run))
        policy = write(pool, chain, peril, dict(subject), 10_000, term)

        for _ in range(blocks_for(term)):
            chain.produce_block()
            if pool.policies[policy.policy_id].status is not PolicyStatus.ACTIVE:
                break

        outcomes[pool.policies[policy.policy_id].status.value] += 1

    observed = outcomes["paid"] / runs
    # Three standard errors of a binomial count at the modelled rate. Drift
    # large enough to matter to a premium clears this; sampling noise does not.
    band = 3.0 * math.sqrt(modelled * (1.0 - modelled) / runs)
    assert abs(observed - modelled) < band, (
        f"{peril}: the chain paid {observed:.1%} against a priced {modelled:.1%}, "
        f"outside the {band:.1%} sampling band"
    )
    # And every policy reached a terminal state rather than hanging.
    assert outcomes["active"] == 0


def test_cover_a_person_bought_runs_in_real_time_not_the_demonstrations() -> None:
    """The world of the demonstration turns forty thousand times faster than
    the clock, so its opening book settles while someone watches. A policy a
    person bought and declared an interest in keeps the term on its document:
    it does not lapse the same afternoon."""
    pool, chain = built()
    synthetic = write(
        pool, chain, "flight_delay",
        {"route": "TK-IST-LHR", "flight_number": "TK1", "departure_date": FLIGHT_DATE},
        1_500, 2,
    )
    real = pool.write(
        peril_key="flight_delay", limit=1_500, term_days=2, holder="holder",
        subject={"route": "TK-IST-JFK", "flight_number": "TK3", "departure_date": FLIGHT_DATE},
    )
    real.metadata["interest"] = {"what": "my flight", "country": "TR"}
    chain.register(real)
    for _ in range(blocks_for(2) * 3):
        chain.produce_block()
    assert pool.policies[synthetic.policy_id].status is not PolicyStatus.ACTIVE
    assert pool.policies[real.policy_id].status is PolicyStatus.ACTIVE
