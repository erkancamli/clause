"""Cancelling after buying, on the terms the buyer's law and the peril allow."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from clause.protocol.cancellation import assess, cooling_off_for
from clause.protocol.policy import PolicyStatus

DAY = 86400.0


def policy(peril="earthquake", term=365, age_days=0.0, resident="TR", **meta):
    now = time.time()
    return SimpleNamespace(
        policy_id="CLS-X", premium=1000.0, term_days=term, peril_key=peril,
        bought_at=now - age_days * DAY, starts_at=now - age_days * DAY,
        ends_at=now - age_days * DAY + term * DAY, is_open=True, status=PolicyStatus.ACTIVE,
        # As every policy the page sells: the contract read and accepted, so
        # the buyer was informed and the statutory clock, not the year, runs.
        metadata={"interest": {"resident": resident}, "contract_hash": "accepted", **meta})


def test_a_mistake_is_undone_in_full_whatever_it_was() -> None:
    for peril, term in (("flight_delay", 2), ("drought", 150), ("earthquake", 365)):
        out = assess(policy(peril, term, age_days=0.01))
        assert out["allowed"] and out["refund"] == 1000 and out["basis"] == "mistake"


def test_the_cooling_off_period_follows_the_buyers_law() -> None:
    assert assess(policy(age_days=10, resident="TR"))["basis"] == "cooling_off"
    assert assess(policy(age_days=10, resident="DE"))["basis"] == "cooling_off"
    japan = assess(policy(age_days=10, resident="JP", term=400))
    assert japan["basis"] != "cooling_off", "eight days in Japan"
    assert cooling_off_for("JP").days == 8
    assert not cooling_off_for("KE").statutory


def test_short_cover_has_no_cooling_off_and_rain_and_flights_end_with_their_term() -> None:
    assert assess(policy("flight_delay", 2, age_days=0.5))["allowed"] is False
    assert assess(policy("drought", 150, age_days=40))["allowed"] is False


def test_earthquake_cover_can_be_left_for_the_unexpired_part() -> None:
    out = assess(policy("earthquake", 365, age_days=182.5))
    assert out["basis"] == "pro_rata" and 480 < out["refund"] < 520


def test_nothing_comes_back_once_the_index_is_reached() -> None:
    out = assess(policy(age_days=0.01, provisional={"since_block": 1}))
    assert out["allowed"] is False and out["basis"] == "settling"


def test_a_commission_already_paid_is_not_refunded_twice() -> None:
    assert assess(policy(age_days=0.01, commission=100.0))["refund"] == 900


def test_a_partners_commission_is_not_refunded_half_way_through_either() -> None:
    """Section 5 of the contract: "A commission paid to a partner who sold
    this policy is not returned on cancellation."

    The test above takes the one hour mistake branch, where the commission is
    netted off a different line, so the pro rata branch -- the one the
    sentence is about, where a buyer leaves half way through -- had nothing
    asking about it. Measured by dropping the term from that line: the
    partner's commission came back out of the pool on any pro rata
    cancellation where the cover used exceeds it, and 63 tests across six
    files passed.

    Half of a 365 day term on a 1,000 premium: 500 of cover used, so 500
    would come back, less the 100 the partner was already paid.
    """
    out = assess(policy("earthquake", 365, age_days=182.5, commission=100.0))
    assert out["basis"] == "pro_rata"
    assert 380 < out["refund"] < 420, out["refund"]

    without = assess(policy("earthquake", 365, age_days=182.5))
    assert without["refund"] - out["refund"] == pytest.approx(100.0, abs=0.01), (
        "the commission is not being kept out of the refund")
