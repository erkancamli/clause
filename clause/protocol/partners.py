"""Companies that sell Clause cover inside their own product.

A travel site that adds flight delay cover at checkout, an estate agent that
offers earthquake cover with a lease, an agricultural cooperative that covers
its members' fields: each is a partner. They reach the protocol with an API
key, bind cover for their customers, pay the premium from their own address,
and are told by webhook when a policy settles.

What stays the same
-------------------
Every rule a direct buyer meets, a partner's customer meets too: the carrier
licence where the risk is, the value at risk worked out from the size, the
pool's capital rules, the price struck at bind time. A partner cannot write
cover the protocol would refuse to a person.

What is different
-----------------
The partner pays, and the partner screened the customer. The partner agreement
makes the partner responsible for sanctions screening, which is the only check
this protocol accepts on a partner's word, and only for cover small enough not
to need an identity check (10,000 in the unit of account). Above that the
customer's own signed statements are needed, exactly as for a direct buyer.

The cover, and every payout, belongs to the customer, never to the partner:
the holder is the customer's address, or, for a customer who has none, an
address made for that one policy whose payouts go straight to the bank
account or mobile wallet the partner named for them.

Keys
----
A key is shown once, when the partner is created or the key is rotated, and
only its hash is kept. Webhooks are signed with a separate secret so a
partner can tell a real settlement notice from a forged one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

# The most a partner may keep of a premium, and it is also capped at the
# premium's own expense load: distribution is paid for out of what the
# pricing already charges for it, never out of the capital's return.
MAX_COMMISSION = 0.20
# Cover a partner may bind on its own screening alone.
PARTNER_SCREENED_LIMIT = 10_000.0

KEY_PREFIX = "ck_live_"


class PartnerError(ValueError):
    """A partner request this module refuses. The message is safe to show."""


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def partner_address(partner_id: str) -> str:
    from .address import from_material
    return from_material(f"partner:{partner_id}".encode())


def beneficiary_address(partner_id: str, external_ref: str) -> str:
    """An address for one customer who has none: nobody holds a key for it,
    so nothing can be spent from it, and its payouts are routed onward."""
    from .address import from_material
    return from_material(f"beneficiary:{partner_id}:{external_ref}".encode())


@dataclass(slots=True)
class Partner:
    partner_id: str
    name: str
    account: str
    key_hash: str
    key_hint: str
    webhook_secret: str
    commission: float = 0.0
    perils: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    webhook_url: str = ""
    status: str = "active"
    created_at: float = 0.0
    created_by: str = ""
    sold: int = 0
    premium_total: float = 0.0
    commission_total: float = 0.0
    refs: dict[str, str] = field(default_factory=dict)   # external_ref -> policy_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "partner_id": self.partner_id, "name": self.name, "account": self.account,
            "key_hint": self.key_hint, "commission": self.commission,
            "perils": list(self.perils), "countries": list(self.countries),
            "webhook_url": self.webhook_url, "status": self.status,
            "created_at": self.created_at, "sold": self.sold,
            "premium_total": round(self.premium_total, 2),
            "commission_total": round(self.commission_total, 2),
            "screened_limit": PARTNER_SCREENED_LIMIT,
        }


class Partners:
    def __init__(self, *, fetcher: Callable[..., Any] | None = None,
                 background: bool = False) -> None:
        # In a server a webhook is sent on its own thread: settlement notices
        # are raised while the chain holds the lock on every movement of value.
        self.background = background
        self.partners: dict[str, Partner] = {}
        self.lock = threading.RLock()
        self.fetcher = fetcher or self._post
        # Webhook deliveries, newest last. Kept in memory: a delivery that is
        # lost in a restart is re-sent by asking, since every policy can be
        # read back through the API at any time.
        self.outbox: deque[dict[str, Any]] = deque(maxlen=2000)

    # -- keys --------------------------------------------------------------

    def create(self, *, name: str, commission: float, perils: list[str], countries: list[str],
               webhook_url: str = "", created_by: str = "operator",
               now: float | None = None) -> tuple[Partner, str]:
        name = " ".join(str(name).split())[:80]
        if len(name) < 2:
            raise PartnerError("give the partner's name")
        if not 0.0 <= float(commission) <= MAX_COMMISSION:
            raise PartnerError(f"commission is between 0 and {MAX_COMMISSION:.0%}")
        if webhook_url and not webhook_url.startswith("https://"):
            raise PartnerError("a webhook address must be https")
        partner_id = "PTR-" + secrets.token_hex(4).upper()
        key = KEY_PREFIX + secrets.token_urlsafe(30)
        partner = Partner(
            partner_id=partner_id, name=name, account=partner_address(partner_id),
            key_hash=_hash(key), key_hint=key[-4:], webhook_secret="whsec_" + secrets.token_urlsafe(24),
            commission=round(float(commission), 4),
            perils=tuple(sorted({str(p) for p in perils}))[:8],
            countries=tuple(sorted({str(c).upper()[:2] for c in countries}))[:64],
            webhook_url=webhook_url[:300], created_at=time.time() if now is None else now,
            created_by=created_by[:80],
        )
        with self.lock:
            self.partners[partner_id] = partner
        return partner, key

    def rotate(self, partner_id: str) -> tuple[Partner, str]:
        with self.lock:
            partner = self.require(partner_id)
            key = KEY_PREFIX + secrets.token_urlsafe(30)
            partner.key_hash, partner.key_hint = _hash(key), key[-4:]
        return partner, key

    def require(self, partner_id: str) -> Partner:
        partner = self.partners.get(partner_id)
        if partner is None:
            raise PartnerError("no such partner")
        return partner

    def authenticate(self, key: str | None) -> Partner:
        if not key or not key.startswith(KEY_PREFIX):
            raise PartnerError("a partner key is required")
        digest = _hash(key)
        for partner in self.partners.values():
            if hmac.compare_digest(partner.key_hash, digest):
                if partner.status != "active":
                    raise PartnerError("this partner is suspended")
                return partner
        raise PartnerError("that key is not recognised")

    # -- selling -----------------------------------------------------------

    def allows(self, partner: Partner, peril: str, country: str) -> None:
        if partner.perils and peril not in partner.perils:
            raise PartnerError("this partner is not set up to sell that cover")
        if partner.countries and country.upper() not in partner.countries:
            raise PartnerError("this partner is not set up to sell in that country")

    @staticmethod
    def commission_on(partner: Partner, premium: float, expense_load: float) -> float:
        return round(min(partner.commission * premium, max(0.0, expense_load)), 6)

    def record(self, partner: Partner, external_ref: str, policy: Any, commission: float) -> None:
        with self.lock:
            partner.refs[external_ref] = policy.policy_id
            partner.sold += 1
            partner.premium_total += policy.premium
            partner.commission_total += commission

    # -- webhooks ----------------------------------------------------------

    @staticmethod
    def sign(secret: str, timestamp: str, body: bytes) -> str:
        return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()

    def _post(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        request = urllib.request.Request(url, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(request, timeout=10) as reply:  # noqa: S310
            return reply.status

    def notify(self, partner: Partner, event: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        """Queue one event for a partner and try it once."""
        now = time.time() if now is None else now
        delivery = {"id": "EVT-" + secrets.token_hex(5).upper(), "partner_id": partner.partner_id,
                    "event": event, "created_at": now, "attempts": 0, "delivered": False,
                    "last_error": ""}
        self.outbox.append(delivery)
        if self.background:
            threading.Thread(target=self._deliver, args=(delivery, now), daemon=True).start()
        else:
            self._deliver(delivery, now)
        return delivery

    def _deliver(self, delivery: dict[str, Any], now: float) -> None:
        partner = self.partners.get(delivery["partner_id"])
        if partner is None or not partner.webhook_url or delivery["delivered"]:
            return
        body = json.dumps({"id": delivery["id"], **delivery["event"]}, separators=(",", ":")).encode()
        stamp = str(int(now))
        delivery["attempts"] += 1
        try:
            status = self.fetcher(partner.webhook_url, body, {
                "content-type": "application/json",
                "x-clause-timestamp": stamp,
                "x-clause-signature": self.sign(partner.webhook_secret, stamp, body),
            })
            if 200 <= int(status) < 300:
                delivery["delivered"] = True
                delivery["last_error"] = ""
            else:
                delivery["last_error"] = f"answered {status}"
        except Exception as error:  # retried later
            delivery["last_error"] = str(error)[:160]

    def retry(self, *, now: float | None = None, max_attempts: int = 8) -> int:
        now = time.time() if now is None else now
        done = 0
        for delivery in list(self.outbox):
            if not delivery["delivered"] and delivery["attempts"] < max_attempts:
                # Back off: 1, 2, 4, 8 minutes... from when it was made.
                due = delivery["created_at"] + 60 * (2 ** (delivery["attempts"] - 1))
                if now >= due:
                    self._deliver(delivery, now)
                    done += delivery["delivered"]
        return done

    def deliveries(self, partner_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = [d for d in self.outbox if d["partner_id"] == partner_id]
        return list(reversed(rows))[:limit]
