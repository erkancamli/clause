"""What the platform gives back, and the three things it must never do.

Each test here names a way a loyalty programme attached to insurance goes
wrong. The first two are regulatory: a scheme that moves the premium is a
rebate, and a scheme paid by the insurer is an inducement. The third is
plainer: a programme that can promise more than it holds is a lie told slowly.
"""

from __future__ import annotations

import time

import pytest

from clause.protocol.rewards import (CONTINUITY_GRACE, Rewards, held_days,
                                     multiplier_for)


class Fake:
    """A policy, as this module reads one."""

    def __init__(self, holder, policy_id, limit, starts_at, ends_at,
                 settled_at=None, status="active"):
        self.holder, self.policy_id, self.limit = holder, policy_id, limit
        self.starts_at, self.ends_at, self.settled_at = starts_at, ends_at, settled_at
        self.status = status

    @property
    def is_open(self):
        return self.status == "active"


class Status:
    ACTIVE, PAID, LAPSED = "active", "paid", "lapsed"


@pytest.fixture(autouse=True)
def terminal(monkeypatch):
    """The real TERMINAL is a set of enum members; these policies use strings."""
    import clause.protocol.policy as policy_module
    monkeypatch.setattr(policy_module, "TERMINAL", {"paid", "lapsed", "expired", "cancelled"})


YEAR = 365.25 * 86400.0


def test_a_year_of_cover_earns_a_year_and_a_day_earns_a_day() -> None:
    """Held, not bought. The whole of the duration rule is in this test."""
    now = 1_800_000_000.0
    rewards = Rewards()
    whole = Fake("a", "CLS-1", 100_000, now - YEAR, now, settled_at=now, status=Status.LAPSED)
    assert rewards.earned(whole, 0, now=now) == pytest.approx(80.0, abs=0.05)

    # bought for a year, cancelled on the second day
    cut = Fake("a", "CLS-2", 100_000, now - 2 * 86400, now + YEAR - 2 * 86400,
               settled_at=now, status="cancelled")
    assert rewards.earned(cut, 0, now=now) == pytest.approx(80.0 * 2 / 365.25, abs=0.01)


def test_a_policy_stops_earning_when_it_settles() -> None:
    """A cover that paid in its first week did not go on earning for the rest
    of the year, and a term that ended does not keep running."""
    now = 1_800_000_000.0
    early = Fake("a", "CLS-3", 100_000, now - YEAR, now - YEAR + 7 * 86400,
                 settled_at=now - YEAR + 7 * 86400, status=Status.PAID)
    assert held_days(early, now) == pytest.approx(7.0, abs=0.01)


def test_renewing_without_a_gap_raises_the_multiplier_and_a_gap_resets_it() -> None:
    now = 1_800_000_000.0
    rewards = Rewards()
    first = Fake("a", "CLS-1", 50_000, now - 3 * YEAR, now - 2 * YEAR,
                 settled_at=now - 2 * YEAR, status=Status.LAPSED)
    second = Fake("a", "CLS-2", 50_000, now - 2 * YEAR + 86400, now - YEAR,
                  settled_at=now - YEAR, status=Status.LAPSED)
    third = Fake("a", "CLS-3", 50_000, now - YEAR + 86400, now)
    book = [first, second, third]

    assert rewards.streak_of(book, first) == 0
    assert rewards.streak_of(book, second) == 1
    assert rewards.streak_of(book, third) == 2
    assert multiplier_for(2) > multiplier_for(0)

    # the same third policy, bought two months after the second ended
    late = Fake("a", "CLS-4", 50_000, now - YEAR + CONTINUITY_GRACE + 86400, now)
    assert rewards.streak_of([first, second, late], late) == 0


def test_the_programme_cannot_give_back_more_than_the_platform_earned() -> None:
    """The budget is a share of the platform's own net fee income. An award
    beyond it is credited as far as the budget reaches, and the shortfall is
    recorded rather than quietly dropped."""

    class Fees:
        def platform_totals(self):
            return {"net": 20.0}          # the platform earned twenty

    now = 1_800_000_000.0
    rewards = Rewards(Fees(), budget_share=0.5)   # so ten may be given back
    big = Fake("a", "CLS-1", 1_000_000, now - YEAR, now, settled_at=now, status=Status.LAPSED)

    made = rewards.sweep([big], now=now)
    assert len(made) == 1
    assert made[0].points == pytest.approx(10.0)
    assert made[0].short > 0
    assert rewards.credited() == pytest.approx(10.0)
    assert rewards.room() == 0.0

    # and nothing more is credited once it is spent
    more = Fake("a", "CLS-2", 1_000_000, now - YEAR, now, settled_at=now, status=Status.LAPSED)
    rewards.sweep([big, more], now=now)
    assert rewards.credited() == pytest.approx(10.0)


def test_nothing_is_credited_while_a_policy_is_still_running() -> None:
    """What a running policy will have earned is not yet a fact: it can be
    cancelled tomorrow. It is shown as earning, not as a balance."""
    now = 1_800_000_000.0
    rewards = Rewards()
    live = Fake("a", "CLS-1", 100_000, now - YEAR / 2, now + YEAR / 2)

    assert rewards.sweep([live], now=now) == []
    mine = rewards.mine("a", [live], now=now)
    assert mine["balance"] == 0.0
    assert mine["earning"] > 0
    assert mine["running"][0]["policy_id"] == "CLS-1"


def test_crediting_twice_does_not_pay_twice() -> None:
    now = 1_800_000_000.0
    rewards = Rewards()
    done = Fake("a", "CLS-1", 100_000, now - YEAR, now, settled_at=now, status=Status.LAPSED)
    rewards.sweep([done], now=now)
    first = rewards.credited()
    rewards.sweep([done], now=now)
    rewards.sweep([done], now=now)
    assert rewards.credited() == first


def test_an_award_keeps_the_rate_it_was_earned_under() -> None:
    """What was earned was earned under the rule in force at the time. A rate
    changed next year does not reach back into last year's awards."""
    now = 1_800_000_000.0
    rewards = Rewards(rate=0.001)
    done = Fake("a", "CLS-1", 100_000, now - YEAR, now, settled_at=now, status=Status.LAPSED)
    award = rewards.sweep([done], now=now)[0]
    rewards.rate = 0.002
    assert award.rate == 0.001
    assert rewards.awards[award.award_id].points == award.points
