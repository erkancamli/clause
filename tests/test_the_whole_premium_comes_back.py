"""A full refund returns everything that was taken, not only the premium.

Three bases give the whole premium back: the hour after buying, Rider's
first day, and the statutory cooling off period. Under a plan that pays in
parts there are three amounts in what the buyer actually paid: the premium
instalment, the issuing fee's share of it, and a surcharge the plan charges
for paying in parts. The fee came back. The surcharge did not, because it
went in as income to the pool and nothing ever reversed it.

Measured against the running app at Osaka, on Japan's twelve monthly plan
at 5%: a buyer who paid 38.16 was given 36.34 back, keeping 1.82, which is
4.8% of what they paid. The same arithmetic was measured by the audit at a
larger size: 912.38 paid and 868.93 back. In Japan that is the right under
the Insurance Business Act article 309 being settled short; in the EU, the
EEA and the UK it is the distance marketing right, and in the UK the plan
is this repository's own "monthly, as a credit agreement", where
withdrawing from the insurance unwinds the credit with it.

A pro rata cancellation is different and keeps it: the credit was used for
the months that ran.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from clause.protocol.cancellation import assess
from clause.protocol.policy import PolicyStatus

DAY = 86400.0


def policy(resident="JP", **meta):
    now = time.time()
    return SimpleNamespace(
        policy_id="CLS-X", premium=1000.0, term_days=365.0, peril_key="earthquake",
        bought_at=now - meta.pop("age_days", 0.0) * DAY,
        starts_at=now, ends_at=now + 365 * DAY, is_open=True, status=PolicyStatus.ACTIVE,
        metadata={"interest": {"resident": resident}, "contract_hash": "accepted", **meta})


# -- what the buyer is told ------------------------------------------------

def test_the_three_parts_of_a_full_refund_are_named_and_totalled() -> None:
    out = assess(policy(age_days=0.01, premium_owed=900.0, fee_paid=2.8, financing_paid=5.0))
    assert out["basis"] == "mistake"
    assert out["refund"] == 100.0, "the premium instalment, which the pool reverses"
    assert out["fee_back"] == 2.8
    assert out["financing_back"] == 5.0
    assert out["whole_back"] == 107.8, "and what leaves the protocol is the sum"


@pytest.mark.parametrize("basis,meta", [
    ("mistake", {"age_days": 0.01}),
    ("rider", {"age_days": 2.0, "bought_by": "rider", "cancel_until": time.time() + 3600}),
    # Japan's eight days exclude cover of a year or less, so the
    # statutory basis is read where a year of cover carries it.
    ("cooling_off", {"age_days": 2.0, "resident": "DE"}),
])
def test_every_basis_that_gives_all_of_it_back_gives_the_surcharge_back(basis, meta) -> None:
    out = assess(policy(fee_paid=2.8, financing_paid=5.0, **meta))
    assert out["basis"] == basis
    assert out["financing_back"] == 5.0
    assert out["whole_back"] == pytest.approx(out["refund"] + 2.8 + 5.0, abs=0.01)


def test_a_pro_rata_cancellation_keeps_the_fee_and_the_surcharge() -> None:
    """Half the term has run, so half the credit was used."""
    out = assess(policy(age_days=182.5, fee_paid=2.8, financing_paid=5.0))
    assert out["basis"] == "pro_rata"
    assert out["fee_back"] == 0.0 and out["financing_back"] == 0.0
    assert out["whole_back"] == out["refund"]


def test_nothing_is_offered_twice() -> None:
    """Both parts are nil once they have been returned, so a second reading
    of the same policy does not promise them again."""
    out = assess(policy(age_days=0.01, fee_paid=2.8, financing_paid=5.0,
                        fee_returned=2.8, financing_returned=5.0))
    assert out["fee_back"] == 0.0 and out["financing_back"] == 0.0
    assert out["whole_back"] == out["refund"]


def test_a_policy_with_no_plan_is_unchanged() -> None:
    out = assess(policy(age_days=0.01))
    assert out["financing_back"] == 0.0 and out["whole_back"] == out["refund"] == 1000.0


# -- and what the pool does about it ---------------------------------------

def test_the_surcharge_leaves_the_pool_the_way_it_arrived() -> None:
    from test_tranches import layered, total_capital

    pool = layered()
    before = total_capital(pool)
    written = pool.write(peril_key="earthquake",
                         subject={"location": "IST-KADIKOY", "radius_km": 50.0},
                         limit=100_000, term_days=365, holder="buyer", paid_now=100.0)
    pool.collect(written, 50.0, extra=2.5)
    assert total_capital(pool) - before == pytest.approx(152.5, abs=0.01)
    assert pool.cancel(written) == pytest.approx(150.0, abs=0.01)
    assert total_capital(pool) - before == pytest.approx(2.5, abs=0.02), (
        "cancel() reverses the premium only, which is what it is given")
    assert pool.return_financing(written) == pytest.approx(2.5, abs=0.01)
    assert total_capital(pool) - before == pytest.approx(0.0, abs=0.02)
    assert pool.return_financing(written) == 0.0, "and not a second time"
    pool.check_ledger()


def test_a_pool_that_cannot_pay_gives_back_what_it_holds() -> None:
    """Money is never created to honour a refund; the same rule cancel() has."""
    from test_tranches import layered

    pool = layered()
    written = pool.write(peril_key="earthquake",
                         subject={"location": "IST-KADIKOY", "radius_km": 50.0},
                         limit=100_000, term_days=365, holder="buyer", paid_now=100.0)
    written.metadata["financing_paid"] = pool.balance + 1_000.0
    back = pool.return_financing(written)
    assert back == pytest.approx(round(pool.balance + back, 2), abs=0.02)
    assert pool.balance >= -1e-6
    pool.check_ledger()
