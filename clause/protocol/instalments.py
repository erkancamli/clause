"""Paying the premium in parts, where the market does.

Whether a premium can be paid in instalments is a fact about where the buyer
lives. In Türkiye annual policies are routinely paid in monthly card
instalments and DASK itself is; in Germany, Spain, France and Italy insurers
offer half yearly, quarterly and monthly payment with a surcharge; in the UK
monthly payment is a credit agreement with interest; in Japan monthly
payment is common. Where nothing of the kind is usual, the premium is paid
at once, and this module says so rather than inventing an option.

How it works here
-----------------
The pool is paid the whole premium the day the policy is written, because
the risk is on its book from that day. The unpaid part is a debt the
policyholder owes the pool, taken from their address on each due date. A
missed instalment has a grace period; after it the policy ends and what was
paid is kept up to the cover already used. Anything still owed when a payout
is made is deducted from the payout, which is how every insurer treats it.
The surcharge, where there is one, is the market's usual and is shown before
the plan is chosen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIN_TERM_DAYS = 90.0
GRACE_DAYS = 15.0


@dataclass(frozen=True, slots=True)
class Plan:
    count: int
    surcharge: float      # share of premium added for paying in parts
    label: str


# By country: the instalment counts on offer and the surcharge each carries.
OFFERS: dict[str, tuple[Plan, ...]] = {
    "TR": (Plan(1, 0.0, "all at once"), Plan(3, 0.0, "3 monthly instalments"),
           Plan(6, 0.0, "6 monthly instalments"), Plan(12, 0.0, "12 monthly instalments")),
    "DE": (Plan(1, 0.0, "all at once"), Plan(2, 0.03, "half yearly"), Plan(4, 0.05, "quarterly"),
           Plan(12, 0.05, "monthly")),
    "AT": (Plan(1, 0.0, "all at once"), Plan(2, 0.03, "half yearly"), Plan(4, 0.05, "quarterly")),
    "ES": (Plan(1, 0.0, "all at once"), Plan(2, 0.03, "half yearly"), Plan(4, 0.05, "quarterly")),
    "FR": (Plan(1, 0.0, "all at once"), Plan(2, 0.02, "half yearly"), Plan(4, 0.04, "quarterly"),
           Plan(12, 0.05, "monthly")),
    "IT": (Plan(1, 0.0, "all at once"), Plan(2, 0.03, "half yearly"), Plan(4, 0.05, "quarterly")),
    "GB": (Plan(1, 0.0, "all at once"), Plan(12, 0.08, "monthly, as a credit agreement")),
    "JP": (Plan(1, 0.0, "all at once"), Plan(12, 0.05, "monthly")),
    "US": (Plan(1, 0.0, "all at once"), Plan(4, 0.0, "quarterly"), Plan(12, 0.0, "monthly")),
    "MX": (Plan(1, 0.0, "all at once"), Plan(12, 0.06, "monthly")),
}
DEFAULT: tuple[Plan, ...] = (Plan(1, 0.0, "all at once"),)


def offers_for(country: str | None, term_days: float) -> list[dict[str, Any]]:
    plans = OFFERS.get((country or "").upper(), DEFAULT)
    if term_days < MIN_TERM_DAYS:
        plans = plans[:1]
    return [{"count": p.count, "surcharge": p.surcharge, "label": p.label} for p in plans]


def _parts(total: float, count: int) -> list[float]:
    """Split a sum into ``count`` cents-exact parts, the last absorbing the rounding."""
    each = round(total / count, 2)
    parts = [each] * (count - 1)
    parts.append(round(total - each * (count - 1), 2))
    return parts


def build(country: str | None, term_days: float, count: int, premium: float, fee: float,
          *, starts_at: float) -> dict[str, Any] | None:
    """The schedule for a chosen plan, or None for paying at once.

    Each instalment is made of three parts, kept separately because they go
    to three places: the pool's premium, the issuing company's fee, and the
    surcharge the plan carries, which is the pool's income for carrying the
    debt. The parts add up to the instalment to the cent, and the
    instalments add up to the total to the cent.
    """
    count = int(count or 1)
    if count <= 1:
        return None
    plan = next((p for p in OFFERS.get((country or "").upper(), DEFAULT) if p.count == count), None)
    if plan is None or term_days < MIN_TERM_DAYS:
        raise ValueError("that instalment plan is not offered where you live, or for cover this short")
    premium, fee = round(premium, 2), round(fee, 2)
    surcharge = round((premium + fee) * plan.surcharge, 2)
    total = round(premium + fee + surcharge, 2)
    premium_parts, fee_parts, extra_parts = _parts(premium, count), _parts(fee, count), _parts(surcharge, count)
    amounts = [round(a + b + c, 2) for a, b, c in zip(premium_parts, fee_parts, extra_parts)]
    every = term_days / count
    due = [round(starts_at + i * every * 86400.0, 0) for i in range(count)]
    return {
        "count": count, "surcharge": plan.surcharge, "label": plan.label,
        "total": total, "amount": amounts[0], "amounts": amounts,
        "premium_parts": premium_parts, "fee_parts": fee_parts, "extra_parts": extra_parts,
        "surcharge_total": surcharge,
        "every_days": round(every, 1), "grace_days": GRACE_DAYS, "due": due,
        "paid": [False] * count, "paid_total": 0.0,
    }


def rescheduled(plan: dict[str, Any], *, starts_at: float) -> dict[str, Any]:
    """The same plan with its dates counted from ``starts_at`` (approval)."""
    out = dict(plan)
    every = float(plan["every_days"])
    out["due"] = [round(starts_at + i * every * 86400.0, 0) for i in range(int(plan["count"]))]
    out["paid"] = list(plan["paid"])
    return out


def part(plan: dict[str, Any], key: str, i: int) -> float:
    """One part of instalment ``i``; plans saved before parts existed fall back."""
    parts = plan.get(key)
    if parts:
        return float(parts[i])
    if key == "premium_parts":
        return float(plan["amount"])
    return 0.0


def outstanding(plan: dict[str, Any] | None) -> float:
    if not plan:
        return 0.0
    return round(plan["total"] - plan["paid_total"], 2)


def due_now(plan: dict[str, Any], now: float) -> list[int]:
    return [i for i, (d, p) in enumerate(zip(plan["due"], plan["paid"])) if not p and d <= now]


def overdue(plan: dict[str, Any], now: float) -> bool:
    return any(not p and now > d + GRACE_DAYS * 86400.0 for d, p in zip(plan["due"], plan["paid"]))
