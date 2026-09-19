"""The pool's capital in three tranches, and the order losses run in."""

from __future__ import annotations

import pytest

from clause.pricing import PricingEngine
from clause.protocol import Pool, PoolError
from clause.protocol.pool import YIELD_WEIGHT


def layered() -> Pool:
    pool = Pool(engine=PricingEngine(trials=2_000, seed=3))
    pool.deposit("senior.lp", 3_000_000)
    pool.deposit("mezz.lp", 600_000, tranche="mezzanine")
    pool.deposit("junior.lp", 400_000, tranche="first_loss")
    return pool


def write_some(pool: Pool, n: int = 4):
    out = []
    for i in range(n):
        out.append(pool.write(
            peril_key="earthquake",
            subject={"location": "IST-KADIKOY", "radius_km": 50},
            limit=150_000, term_days=365, holder=f"buyer{i}",
        ))
    return out


def test_each_tranche_prices_its_own_shares() -> None:
    pool = layered()
    assert pool.balance == pytest.approx(4_000_000)
    assert pool.tranches["first_loss"].shares == pytest.approx(400_000)
    assert pool.providers["junior.lp/first_loss"].tranche == "first_loss"
    # Senior holdings keep the bare address, as before tranches existed.
    assert pool.providers["senior.lp"].tranche == "senior"


def test_premium_funds_expected_loss_where_it_falls_and_shares_the_margin() -> None:
    pool = layered()
    before = {n: t.balance for n, t in pool.tranches.items()}
    policy = write_some(pool, 1)[0]
    gained = {n: pool.tranches[n].balance - before[n] for n in before}
    assert sum(gained.values()) == pytest.approx(policy.premium)
    assert policy.metadata["tranche_split"]
    # The first loss tranche takes the expected loss, so it is funded for it:
    # it gets more than the margin alone would give it.
    margin = policy.premium - policy.expected_loss
    weights = {n: before[n] * YIELD_WEIGHT[n] for n in before}
    margin_only = margin * weights["first_loss"] / sum(weights.values())
    assert gained["first_loss"] > margin_only


def test_every_tranche_expects_a_positive_return_on_a_priced_book() -> None:
    pool = layered()
    write_some(pool, 6)
    for row in pool.tranche_view():
        assert row["expected_return"] is None or row["expected_return"] > 0, row


def test_a_loss_is_taken_from_the_bottom_up() -> None:
    pool = layered()
    policies = write_some(pool, 3)
    fl, mz, sr = (pool.tranches[n].balance for n in ("first_loss", "mezzanine", "senior"))
    pool.pay(policies[0], 7.4)
    paid = policies[0].payout
    assert paid <= fl
    assert pool.tranches["first_loss"].balance == pytest.approx(fl - paid)
    assert pool.tranches["mezzanine"].balance == pytest.approx(mz)
    assert pool.tranches["senior"].balance == pytest.approx(sr)
    assert policies[0].metadata["tranche_loss"] == {"first_loss": pytest.approx(paid)}
    pool.check_ledger()


def test_a_loss_larger_than_the_first_loss_tranche_reaches_the_mezzanine() -> None:
    pool = Pool(engine=PricingEngine(trials=500, seed=1))
    pool.deposit("s", 1_000_000)
    pool.deposit("m", 50_000, tranche="mezzanine")
    pool.deposit("f", 20_000, tranche="first_loss")
    pool.balance -= 60_000
    assert pool.tranches["first_loss"].balance == pytest.approx(0)
    assert pool.tranches["mezzanine"].balance == pytest.approx(10_000)
    assert pool.tranches["senior"].balance == pytest.approx(1_000_000)
    # The share price moved only for the tranches that took the loss.
    assert pool.tranches["senior"].price == pytest.approx(1.0)
    assert pool.tranches["mezzanine"].price == pytest.approx(0.2)


def test_a_refund_takes_back_the_premium_as_it_was_shared() -> None:
    pool = layered()
    before = {n: t.balance for n, t in pool.tranches.items()}
    policy = write_some(pool, 1)[0]
    pool.expire(policy)
    for name, amount in before.items():
        assert pool.tranches[name].balance == pytest.approx(amount)
    pool.check_ledger()


def test_capital_beneath_the_senior_tranche_cannot_leave_below_the_floor(monkeypatch) -> None:
    pool = layered()
    write_some(pool, 2)
    # The floor is the book's one in ten year loss; set it where the rule binds.
    monkeypatch.setattr(pool, "subordination_floor", lambda: 900_000.0)
    with pytest.raises(PoolError, match="beneath the senior tranche"):
        pool.withdraw("junior.lp", 200_000, tranche="first_loss")
    monkeypatch.setattr(pool, "subordination_floor", lambda: 0.0)
    assert pool.withdraw("junior.lp", 1_000, tranche="first_loss") > 0
    # Senior money is governed only by the free capital rule.
    small = 1_000 / pool.tranches["senior"].price
    assert pool.withdraw("senior.lp", small) == pytest.approx(1_000)


def test_the_floor_is_a_real_quantile_of_the_book() -> None:
    pool = layered()
    assert pool.subordination_floor() == 0.0   # nothing written, nothing at risk
    write_some(pool, 3)
    losses = sorted(pool.engine.simulate(pool.exposures()).losses)
    assert pool.subordination_floor() == losses[int(len(losses) * 0.9)]


def test_unknown_tranche_is_refused() -> None:
    pool = layered()
    with pytest.raises(PoolError, match="tranche"):
        pool.deposit("x", 100, tranche="equity")
    with pytest.raises(PoolError, match="no shares"):
        pool.withdraw("senior.lp", 1, tranche="first_loss")


def test_the_view_publishes_attachment_and_expected_loss() -> None:
    pool = layered()
    write_some(pool, 5)
    view = {row["name"]: row for row in pool.tranche_view()}
    assert view["first_loss"]["attaches_at"] == 0
    assert view["mezzanine"]["attaches_at"] == pytest.approx(view["first_loss"]["exhausted_at"])
    assert view["senior"]["attaches_at"] == pytest.approx(view["mezzanine"]["exhausted_at"])
    # The junior tranche is hit at least as often as anything above it.
    assert view["first_loss"]["probability_of_loss"] >= view["mezzanine"]["probability_of_loss"]
    assert view["mezzanine"]["probability_of_loss"] >= view["senior"]["probability_of_loss"]
    assert view["first_loss"]["expected_premium"] > 0


def test_a_pool_with_one_tranche_behaves_as_before() -> None:
    pool = Pool(engine=PricingEngine(trials=500, seed=1))
    pool.deposit("lp", 1_000_000)
    pool.balance += 100_000
    assert pool.share_price == pytest.approx(1.1)
    assert pool.total_shares == pytest.approx(1_000_000)


def total_capital(pool: Pool) -> float:
    return sum(t.balance for t in pool.tranches.values())


def test_a_premium_paid_in_parts_is_booked_as_it_arrives() -> None:
    """The tranches hold what the pool has received, never what it is owed."""
    pool = layered()
    before = total_capital(pool)
    policy = pool.write(peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50.0},
                        limit=100_000, term_days=365, holder="buyer", paid_now=100.0)
    assert policy.metadata["premium_owed"] == pytest.approx(policy.premium - 100.0, abs=0.01)
    assert total_capital(pool) - before == pytest.approx(100.0, abs=0.01)
    assert sum(policy.metadata["tranche_split"].values()) == pytest.approx(100.0, abs=0.01)
    # An instalment arrives, with a financing surcharge on top.
    got = pool.collect(policy, 50.0, extra=2.5)
    assert got == pytest.approx(50.0)
    assert total_capital(pool) - before == pytest.approx(152.5, abs=0.01)
    assert policy.metadata["financing_paid"] == pytest.approx(2.5)
    # Cancelled for a full refund: only what was paid comes back, the debt is written off.
    refund = pool.cancel(policy)
    assert refund == pytest.approx(150.0, abs=0.01)
    assert policy.metadata["premium_owed"] == 0.0 and policy.metadata["written_off"] > 0
    assert total_capital(pool) - before == pytest.approx(2.5, abs=0.02)
    pool.check_ledger()


def test_expiry_and_lapse_forget_the_debt_and_refund_only_what_was_paid() -> None:
    pool = layered()
    a = pool.write(peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50.0},
                   limit=100_000, term_days=365, holder="a", paid_now=100.0)
    b = pool.write(peril_key="earthquake", subject={"location": "ANK-CANKAYA", "radius_km": 25.0},
                   limit=100_000, term_days=365, holder="b", paid_now=20.0)
    assert pool.expire(a) == pytest.approx(100.0, abs=0.01)
    pool.lapse(b)
    assert a.metadata["premium_owed"] == 0.0 and b.metadata["premium_owed"] == 0.0
    pool.check_ledger()


def test_commission_is_paid_once_and_only_out_of_premium_received() -> None:
    pool = layered()
    policy = pool.write(peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50.0},
                        limit=100_000, term_days=365, holder="buyer", paid_now=60.0)
    assert pool.pay_commission(policy, "partner", 100.0) == pytest.approx(60.0)
    with pytest.raises(PoolError):
        pool.pay_commission(policy, "partner", 10.0)


def test_income_with_no_shareholders_is_kept_by_the_pool_not_the_next_depositor() -> None:
    from clause.protocol.pool import RETAINED
    pool = layered()
    layer = pool.tranches["mezzanine"]
    # Everyone leaves the mezzanine, then income lands there.
    for key, p in list(pool.providers.items()):
        if p.tranche == "mezzanine":
            pool.withdraw(p.account, p.shares, tranche="mezzanine")
    assert layer.shares == pytest.approx(0.0)
    layer.balance += 500.0
    shares = pool.deposit("late", 100.0, tranche="mezzanine")
    assert shares == pytest.approx(100.0)
    assert pool.providers[f"{RETAINED}/mezzanine"].shares == pytest.approx(500.0)
