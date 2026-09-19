"""A signed, limited permission for Rider to buy cover on someone's behalf.

Rider could only ever prepare a purchase and leave the signing to the person,
because a model that holds a key is one persuasive paragraph from spending it.
A mandate changes what Rider may do without changing who decides the limits.

The person signs, on their own device, the exact terms of the permission:

    the most any one policy may cost
    the most all of them together may cost
    the largest cover any one policy may carry
    which perils
    until when

The protocol keeps the signed terms and gives the browser a token for them.
Rider presents the token with each purchase, and every purchase is checked
against the terms here, in code, after the model has had its say. The model
can be talked into asking for anything; it cannot be talked past this file.

Two more fences sit around it. Rider's purchase path goes through a Latch,
Rialo's policy proxy, which holds the key the purchase endpoint needs and
applies its own filters (the operator's daily cap, rate limit, allowed
endpoint) before that key is ever used. And every policy Rider buys can be
cancelled by its holder for a full refund within a day of purchase, as long
as its index has not already been reached.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

MAX_DAYS = 90
COOLING_OFF_HOURS = 24
# Without an identity statement, a mandate cannot authorise cover above the
# level that needs one; the person would have to present it first.
UNVERIFIED_LIMIT = 10_000.0
TOKEN_PREFIX = "rm_"


class MandateError(ValueError):
    """A purchase or a mandate this module refuses. Safe to show."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(slots=True)
class Mandate:
    mandate_id: str
    account: str
    token_hash: str
    max_premium_per_policy: float
    max_premium_total: float
    max_limit_per_policy: float
    perils: tuple[str, ...]
    country: str
    expires_at: float
    created_at: float
    claims: tuple[str, ...] = ()
    claims_expire_at: float | None = None
    spent: float = 0.0
    bought: list[str] = field(default_factory=list)
    revoked_at: float | None = None

    def live(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return self.revoked_at is None and now < self.expires_at

    def remaining(self) -> float:
        return max(0.0, self.max_premium_total - self.spent)

    def terms(self) -> dict[str, Any]:
        """What the person signed, exactly."""
        return {
            "max_premium_per_policy": self.max_premium_per_policy,
            "max_premium_total": self.max_premium_total,
            "max_limit_per_policy": self.max_limit_per_policy,
            "perils": ",".join(self.perils),
            "days": round((self.expires_at - self.created_at) / 86400.0),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "max_premium_per_policy": self.max_premium_per_policy,
            "max_premium_total": self.max_premium_total,
            "max_limit_per_policy": self.max_limit_per_policy,
            "perils": list(self.perils), "country": self.country,
            "expires_at": self.expires_at, "created_at": self.created_at,
            "spent": round(self.spent, 2), "remaining": round(self.remaining(), 2),
            "bought": list(self.bought), "live": self.live(),
            "revoked_at": self.revoked_at, "cooling_off_hours": COOLING_OFF_HOURS,
        }


def parse_terms(body: dict[str, Any], known_perils: set[str]) -> dict[str, Any]:
    """The terms as the person signs them, checked and normalised."""
    try:
        per = float(body["max_premium_per_policy"])
        total = float(body["max_premium_total"])
        limit = float(body["max_limit_per_policy"])
        days = int(body["days"])
    except (KeyError, TypeError, ValueError) as error:
        raise MandateError("a mandate names a price per policy, a total, a largest cover and a number of days") from error
    perils = [p for p in str(body.get("perils", "")).split(",") if p]
    if not perils or any(p not in known_perils for p in perils):
        raise MandateError("name the covers Rider may buy")
    if not (0 < per <= total <= 100_000):
        raise MandateError("the price per policy must be positive and no more than the total")
    if not (100 <= limit <= 1_000_000):
        raise MandateError("the largest cover must be between 100 and 1,000,000")
    if not (1 <= days <= MAX_DAYS):
        raise MandateError(f"a mandate lasts between 1 and {MAX_DAYS} days")
    return {"max_premium_per_policy": per, "max_premium_total": total,
            "max_limit_per_policy": limit, "perils": ",".join(sorted(set(perils))), "days": float(days)}


class Mandates:
    def __init__(self) -> None:
        self.mandates: dict[str, Mandate] = {}
        self.lock = threading.RLock()

    def create(self, account: str, terms: dict[str, Any], *, country: str,
               claims: tuple[str, ...] = (), claims_expire_at: float | None = None,
               now: float | None = None) -> tuple[Mandate, str]:
        now = time.time() if now is None else now
        if terms["max_limit_per_policy"] > UNVERIFIED_LIMIT and not any(
                c.startswith("identity") for c in claims):
            raise MandateError(
                f"cover above {UNVERIFIED_LIMIT:,.0f} needs an identity statement; "
                "present one, or keep Rider's largest cover at or below that")
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        mandate = Mandate(
            mandate_id="MND-" + secrets.token_hex(4).upper(), account=account,
            token_hash=_hash(token),
            max_premium_per_policy=terms["max_premium_per_policy"],
            max_premium_total=terms["max_premium_total"],
            max_limit_per_policy=terms["max_limit_per_policy"],
            perils=tuple(terms["perils"].split(",")), country=country.upper()[:2],
            expires_at=now + terms["days"] * 86400.0, created_at=now,
            claims=tuple(claims), claims_expire_at=claims_expire_at,
        )
        with self.lock:
            # One live mandate per account: a new one replaces the old.
            for old in self.mandates.values():
                if old.account == account and old.revoked_at is None:
                    old.revoked_at = now
            self.mandates[mandate.mandate_id] = mandate
        return mandate, token

    def authenticate(self, token: str | None, *, now: float | None = None) -> Mandate:
        if not token or not token.startswith(TOKEN_PREFIX):
            raise MandateError("no mandate was presented")
        digest = _hash(token)
        for mandate in self.mandates.values():
            if hmac.compare_digest(mandate.token_hash, digest):
                if not mandate.live(now):
                    raise MandateError("that mandate has ended or was revoked")
                return mandate
        raise MandateError("that mandate is not recognised")

    def current(self, account: str) -> Mandate | None:
        live = [m for m in self.mandates.values() if m.account == account and m.live()]
        return max(live, key=lambda m: m.created_at) if live else None

    def revoke(self, account: str, *, now: float | None = None) -> int:
        now = time.time() if now is None else now
        n = 0
        with self.lock:
            for mandate in self.mandates.values():
                if mandate.account == account and mandate.revoked_at is None:
                    mandate.revoked_at = now
                    n += 1
        return n

    def check(self, mandate: Mandate, *, peril: str, limit: float,
              now: float | None = None) -> float:
        """Whether this purchase fits; returns the most it may cost."""
        now = time.time() if now is None else now
        if not mandate.live(now):
            raise MandateError("that mandate has ended or was revoked")
        if peril not in mandate.perils:
            raise MandateError("the mandate does not let Rider buy that cover")
        if limit > mandate.max_limit_per_policy + 1e-9:
            raise MandateError(
                f"the mandate lets Rider buy cover up to {mandate.max_limit_per_policy:,.0f}")
        if mandate.claims_expire_at is not None and now > mandate.claims_expire_at:
            raise MandateError("the statements this mandate relied on have expired; sign a new one")
        ceiling = min(mandate.max_premium_per_policy, mandate.remaining())
        if ceiling <= 0:
            raise MandateError("the mandate's total has been spent")
        return ceiling

    def record(self, mandate: Mandate, policy: Any) -> None:
        """Count what the purchase cost the person: premium and issuing fee."""
        with self.lock:
            mandate.spent += policy.premium + float((policy.metadata or {}).get("fee_paid", 0.0))
            mandate.bought.append(policy.policy_id)

    def release(self, mandate_id: str, amount: float) -> None:
        """A cancelled purchase gives its price back to the mandate."""
        with self.lock:
            mandate = self.mandates.get(mandate_id)
            if mandate is not None:
                mandate.spent = max(0.0, mandate.spent - amount)
