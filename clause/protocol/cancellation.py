"""Changing your mind after buying: when, and how much comes back.

Three rules, applied in this order, and the most generous that applies wins.

1. A mistake. Anything bought in the last hour can be cancelled for the whole
   premium, whatever it is and wherever the buyer lives. People press the
   wrong button; an hour costs the pool nothing.

2. The law where the buyer lives. Consumer law gives a cooling off period for
   insurance sold at a distance, with the whole premium back:

       EU and EEA   14 days   Distance Marketing Directive 2002/65/EC, as
                              each member state enacts it
       UK           14 days   FCA Handbook, ICOBS 7
       Türkiye      14 days   Law 6502 on consumer protection, and its
                              regulation on distance contracts for
                              financial services
       Japan         8 days   Insurance Business Act, article 309

   Each of these excludes short cover. In Europe, the UK and Türkiye cover of
   less than a month (travel cover is the usual case) has no cooling off
   period; in Japan cover of a year or less has none. Everywhere else this
   protocol gives 14 days on the same terms, as its own rule rather than any
   law's. A real policy follows its issuer's conditions, which may give more.

3. After that, cover that cannot be forecast can still be cancelled with the
   unexpired part of the premium back. An earthquake cannot be seen coming,
   so a buyer who leaves halfway through gets half back. Rain and flights
   can: a season that has been wet so far, or a flight already in the air,
   tells a buyer something the pool priced without knowing. Refunding those
   halfway through would let the buyers who have seen that the danger passed
   leave, and the ones who have not stay; the pool would be left holding only
   the bad risks. So cover on rain, rivers and flights ends when its term does.

Nothing can be cancelled once its index has been reached: the policy is
already settling, and cancelling it would be taking the payout back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

MISTAKE_SECONDS = 3600.0
DAY = 86400.0

EU_EEA = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "IS", "LI", "NO",
})

# Perils whose outcome cannot be seen coming during the term.
UNFORESEEABLE = frozenset({"earthquake"})


@dataclass(frozen=True, slots=True)
class CoolingOff:
    days: float
    short_cover_days: float      # cover this short or shorter has no cooling off
    law: str
    statutory: bool = True


def cooling_off_for(country: str | None) -> CoolingOff:
    code = (country or "").upper()
    if code in EU_EEA:
        return CoolingOff(14, 30, "the Distance Marketing Directive 2002/65/EC, as enacted where you live")
    if code == "GB":
        return CoolingOff(14, 30, "the FCA Handbook, ICOBS 7")
    if code == "TR":
        return CoolingOff(14, 30, "Law 6502 on consumer protection and its regulation on distance contracts for financial services")
    if code == "JP":
        return CoolingOff(8, 365, "the Insurance Business Act, article 309")
    return CoolingOff(14, 30, "this protocol's own rule, where no local one is modelled", statutory=False)


def assess(policy: Any, *, now: float | None = None) -> dict[str, Any]:
    """Whether this policy can be cancelled now, how much comes back, and why."""
    now = time.time() if now is None else now
    meta = policy.metadata or {}
    commission = float(meta.get("commission", 0.0))
    # Only what has been paid can come back: with an instalment plan that is
    # the instalments so far, less any commission already paid out of them.
    paid = policy.premium - float(meta.get("premium_owed", 0.0))
    refundable = max(0.0, paid - commission)
    resident = ((meta.get("interest") or {}).get("resident")
                or (meta.get("interest") or {}).get("country"))
    rule = cooling_off_for(resident)
    age = now - policy.bought_at
    term = max(0.0, policy.ends_at - policy.starts_at) or policy.term_days * DAY
    out: dict[str, Any] = {
        "policy_id": policy.policy_id, "premium": round(policy.premium, 2),
        "paid": round(paid, 2), "premium_owed": round(float(meta.get("premium_owed", 0.0)), 2),
        "cooling_off_days": rule.days, "law": rule.law, "statutory": rule.statutory,
        "mistake_until": policy.bought_at + MISTAKE_SECONDS,
    }

    if not policy.is_open:
        return {**out, "allowed": False, "refund": 0.0, "basis": "closed",
                "reason": f"this policy is already {policy.status.value}"}
    if meta.get("provisional"):
        return {**out, "allowed": False, "refund": 0.0, "basis": "settling",
                "reason": "the index has already been reached; this policy is settling"}

    if age <= MISTAKE_SECONDS:
        return {**out, "allowed": True, "refund": round(refundable, 2), "basis": "mistake",
                "until": policy.bought_at + MISTAKE_SECONDS,
                "reason": "bought less than an hour ago: all of it comes back"}
    if meta.get("bought_by") == "rider" and now <= float(meta.get("cancel_until", 0)):
        return {**out, "allowed": True, "refund": round(refundable, 2), "basis": "rider",
                "until": float(meta["cancel_until"]),
                "reason": "bought by Rider less than a day ago: all of it comes back"}
    if policy.term_days > rule.short_cover_days and age <= rule.days * DAY:
        return {**out, "allowed": True, "refund": round(refundable, 2), "basis": "cooling_off",
                "until": policy.bought_at + rule.days * DAY,
                "reason": f"inside the {rule.days:g} day cooling off period under {rule.law}: all of it comes back"}
    if policy.peril_key in UNFORESEEABLE:
        left = max(0.0, (policy.ends_at - now) / term) if term > 0 else 0.0
        used = policy.premium * (1.0 - left)
        # What was paid, less the cover already used; never below zero, and a
        # plan that is behind its usage has nothing to get back.
        refund = max(0.0, min(refundable, paid - used - commission))
        return {**out, "allowed": left > 0, "refund": round(refund, 2), "basis": "pro_rata",
                "reason": (f"the unexpired {left:.0%} of the term comes back: an earthquake cannot be "
                           f"seen coming, so leaving early tells the pool nothing")}
    return {**out, "allowed": False, "refund": 0.0, "basis": "none",
            "reason": ("cover on rain, on wind and on flights runs to the end of its term once the first "
                       "hour and any cooling off period have passed: a buyer can see how the "
                       "season, the weather or the flight is going, and refunds then would leave the pool "
                       "with only the risks that turned out badly")}
