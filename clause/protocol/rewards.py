"""What the platform gives back for cover held, and where it comes from.

A programme that pays people to buy insurance is an inducement, and in most
places a regulated one. This is deliberately not that. Three rules keep it on
the right side of the line, and each is enforced here rather than promised in
a footnote.

**It is not a discount on the premium.** The price on the screen is the pool's
price and stays so, because that price is an actuarial statement about risk and
a loyalty scheme has no business moving it. Nothing in this module can reduce
what is charged.

**It is not the insurer's money.** The platform takes its fee from the issuing
company, out of that company's fronting fee, and never from the buyer
(``fees.py``). What is given back comes out of that fee and nothing else, so an
award costs the insurer nothing and the pool nothing.

**It cannot promise more than the platform has earned.** The budget is a share
of the platform's own net fee income, and an award that would exceed it is
credited only as far as the budget reaches, with the shortfall recorded. A
rewards programme that can run out of money without saying so is a lie told
slowly.

What is rewarded is cover **held**, not cover bought:

    points = limit x (days in force / 365.25) x rate x continuity

so a year of cover earns a year's worth, and a policy cancelled on its second
day earns two days. That is the whole of the duration rule the name suggests:
there is no bonus for buying a longer term, only for holding one, and nothing
is credited until the term has actually run.

Continuity is the renewal rule. Each unbroken term raises the multiplier a
step, and a gap longer than the renewal grace in ``instructions.py`` puts it
back to the beginning; the two use the same grace so the page cannot say a
policy was renewed while this says it was not.

The unit is RIALO. On this build the chain is simulated and so is the balance:
it is an accrual in the protocol's own books, it is not a token anyone holds,
and the interface says so in the same words it uses for test networks. When
there is a token and a rail to pay it on, what is credited here is what is
owed; until then this is an account of that, and nothing more.
"""

from __future__ import annotations

import datetime as dt
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

# RIALO per unit of limit, per year of cover held. A hundred thousand of cover
# carried for a full year earns eighty.
RATE_PER_YEAR = 0.0008

# Each unbroken term is worth more than the last, up to a ceiling: a scheme
# that keeps climbing forever prices the oldest customer's loyalty at a number
# nobody chose.
CONTINUITY_STEPS = (1.00, 1.15, 1.30, 1.50)

# The same grace the renewal instruction uses, so the two cannot disagree about
# whether cover was continuous.
from .instructions import RENEW_GRACE as CONTINUITY_GRACE  # noqa: E402

# What share of the platform's net fee income the programme may give back.
BUDGET_SHARE = 0.5

YEAR = 365.25 * 86400.0


@dataclass(slots=True)
class Award:
    """One policy's accrual, with the figures it was worked out from.

    The rate is stored rather than looked up later: what was earned was earned
    under the rule in force at the time, and a rate changed next year does not
    reach back.
    """

    award_id: str
    holder: str
    policy_id: str
    points: float
    limit: float
    days: float
    rate: float
    streak: int
    multiplier: float
    short: float          # what the budget could not cover
    at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "award_id": self.award_id, "policy_id": self.policy_id,
            "points": round(self.points, 4), "limit": round(self.limit, 2),
            "days": round(self.days, 2), "rate": self.rate, "streak": self.streak,
            "multiplier": self.multiplier, "short": round(self.short, 4), "at": self.at,
            "month": dt.datetime.fromtimestamp(self.at, dt.timezone.utc).strftime("%Y-%m"),
        }


def held_days(policy: Any, now: float | None = None) -> float:
    """How long this policy was actually in force, in days.

    From the day cover started to the day it ended, or to today if it is still
    running. Never past its own term: a policy that settled in its first week
    did not go on earning for the rest of the year.
    """
    now = time.time() if now is None else now
    started = float(policy.starts_at)
    ended = policy.settled_at if policy.settled_at else min(now, float(policy.ends_at))
    return max(0.0, (min(float(ended), float(policy.ends_at)) - started) / 86400.0)


def multiplier_for(streak: int) -> float:
    return CONTINUITY_STEPS[min(streak, len(CONTINUITY_STEPS) - 1)]


class Rewards:
    """The ledger of what has been given back, and the rule that produced it."""

    def __init__(self, fees: Any = None, *, rate: float = RATE_PER_YEAR,
                 budget_share: float = BUDGET_SHARE) -> None:
        self.fees = fees
        self.rate = rate
        self.budget_share = budget_share
        self.awards: dict[str, Award] = {}
        self.lock = threading.RLock()

    # -- the rule ----------------------------------------------------------

    def streak_of(self, policies: Iterable[Any], policy: Any) -> int:
        """How many unbroken terms this holder had before this one.

        Cover counts as unbroken when the next policy starts within the
        renewal grace of the last one ending. A gap wider than that is a new
        beginning, which is what "renewed" has to mean if it means anything.
        """
        mine = sorted(
            (p for p in policies
             if p.holder == policy.holder and float(p.starts_at) < float(policy.starts_at)),
            key=lambda p: float(p.starts_at),
        )
        streak, previous_end = 0, None
        for earlier in mine:
            ended = float(earlier.settled_at or earlier.ends_at)
            if previous_end is not None and float(earlier.starts_at) - previous_end > CONTINUITY_GRACE:
                streak = 0
            streak += 1
            previous_end = ended
        if previous_end is None:
            return 0
        if float(policy.starts_at) - previous_end > CONTINUITY_GRACE:
            return 0
        return streak

    def earned(self, policy: Any, streak: int, *, now: float | None = None) -> float:
        """What a policy has earned so far, before the budget is applied."""
        days = held_days(policy, now)
        return float(policy.limit) * (days / 365.25) * self.rate * multiplier_for(streak)

    # -- the budget --------------------------------------------------------

    def budget(self) -> float:
        """What the platform has earned that the programme may give back."""
        if self.fees is None:
            return float("inf")
        return max(0.0, float(self.fees.platform_totals()["net"]) * self.budget_share)

    def credited(self) -> float:
        with self.lock:
            return round(sum(a.points for a in self.awards.values()), 4)

    def room(self) -> float:
        budget = self.budget()
        return budget if budget == float("inf") else max(0.0, budget - self.credited())

    # -- crediting ---------------------------------------------------------

    def sweep(self, policies: Iterable[Any], *, now: float | None = None) -> list[Award]:
        """Credit every policy that has ended and has not been credited.

        Idempotent by policy: run it as often as you like. Nothing is credited
        while a policy is still running, because what it will have earned is
        not yet a fact.
        """
        from .policy import TERMINAL

        now = time.time() if now is None else now
        made: list[Award] = []
        with self.lock:
            done = {a.policy_id for a in self.awards.values()}
            ended = [p for p in policies if p.status in TERMINAL and p.policy_id not in done]
            ended.sort(key=lambda p: float(p.settled_at or p.ends_at))
            for policy in ended:
                streak = self.streak_of(policies, policy)
                want = self.earned(policy, streak, now=now)
                if want <= 0:
                    continue
                room = self.room()
                points = want if room == float("inf") else min(want, room)
                award = Award(
                    award_id="RWD-" + secrets.token_hex(4).upper(),
                    holder=policy.holder, policy_id=policy.policy_id,
                    points=points, limit=float(policy.limit),
                    days=held_days(policy, now), rate=self.rate, streak=streak,
                    multiplier=multiplier_for(streak), short=max(0.0, want - points),
                    at=float(policy.settled_at or policy.ends_at or now),
                )
                self.awards[award.award_id] = award
                made.append(award)
        return made

    # -- reading -----------------------------------------------------------

    def of(self, holder: str) -> list[Award]:
        with self.lock:
            return sorted((a for a in self.awards.values() if a.holder == holder),
                          key=lambda a: -a.at)

    def mine(self, holder: str, policies: Iterable[Any], *,
             now: float | None = None) -> dict[str, Any]:
        """One holder's account: what is credited, what is still earning.

        The two are kept apart on purpose. What a running policy has earned so
        far is a figure that can still fall — the policy can be cancelled — so
        it is shown as earning rather than as a balance.
        """
        now = time.time() if now is None else now
        policies = list(policies)
        awards = self.of(holder)
        running = []
        earning = 0.0
        for policy in policies:
            if policy.holder != holder or not policy.is_open:
                continue
            streak = self.streak_of(policies, policy)
            so_far = self.earned(policy, streak, now=now)
            earning += so_far
            running.append({
                "policy_id": policy.policy_id, "limit": round(float(policy.limit), 2),
                "days": round(held_days(policy, now), 2), "streak": streak,
                "multiplier": multiplier_for(streak), "points": round(so_far, 4),
            })
        mine_all = [p for p in policies if p.holder == holder]
        best = max((self.streak_of(policies, p) for p in mine_all), default=0)
        return {
            "unit": "RIALO",
            "balance": round(sum(a.points for a in awards), 4),
            "earning": round(earning, 4),
            "streak": best,
            "multiplier": multiplier_for(best),
            "next_multiplier": multiplier_for(best + 1),
            "rate": self.rate,
            "steps": list(CONTINUITY_STEPS),
            "grace_days": round(CONTINUITY_GRACE / 86400.0),
            "running": running,
            "awards": [a.to_dict() for a in awards[:40]],
        }

    def totals(self) -> dict[str, Any]:
        with self.lock:
            short = round(sum(a.short for a in self.awards.values()), 4)
            holders = {a.holder for a in self.awards.values()}
        budget = self.budget()
        return {
            "unit": "RIALO", "rate": self.rate, "budget_share": self.budget_share,
            "budget": None if budget == float("inf") else round(budget, 2),
            "credited": self.credited(), "awards": len(self.awards),
            "holders": len(holders), "not_covered_by_budget": short,
        }
