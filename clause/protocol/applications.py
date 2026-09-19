"""Applications: cover asked for, waiting for the insurer's own checks.

A buyer used to fetch a signed statement ("not on a sanctions list", "identity
checked") from a verifier in the same breath as buying, and the page then
said the check had been done. In this build that verifier is a demonstration
one that signs for anybody, so the page was saying something that had not
happened. And in insurance the company that issues the policy is the one that
has to be satisfied: it screens the buyer against sanctions lists and, above
a certain size, checks who they are, before it puts its name on anything.

So a purchase through the site is an application. The buyer signs the terms
at the price they were shown, and the premium is held, not taken. The issuing
company sees the application, does its checks and approves or rejects it,
recording who decided and what they checked. Approval writes the policy at
the price the buyer agreed to; rejection returns the premium in full. An
application nobody decides within three days lapses and is refunded the
same way, so money is never held without an end.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

DECIDE_WITHIN = 3 * 86400.0


class ApplicationError(ValueError):
    """An application this module refuses to act on. Safe to show."""


@dataclass(slots=True)
class Application:
    app_id: str
    holder: str
    peril: str
    subject: dict[str, Any]
    limit: float
    term_days: float
    declared: dict[str, Any]
    size: dict[str, Any] | None
    value_at_risk: float
    settlement: str
    premium: float
    carrier_id: str | None
    checks: list[str]
    created_at: float
    fee: float = 0.0
    subject_text: str = ""
    contract: str = ""
    contract_hash: str = ""
    address: dict[str, str] | None = None
    plan: dict[str, Any] | None = None
    status: str = "pending"        # pending | deciding | approved | rejected | withdrawn | lapsed
    decided_at: float | None = None
    decided_by: str = ""
    note: str = ""
    checked: list[str] = field(default_factory=list)
    policy_id: str | None = None
    # What was actually held at creation, and whether it has left escrow.
    # Recomputing the amount later from fee and plan would refund a different
    # figure if those rules changed in between; and a flag makes the refund
    # idempotent, so two decisions racing cannot return the money twice.
    held: float = 0.0
    released: bool = False
    # Made by a standing instruction rather than by hand, when set.
    instruction_id: str = ""

    @property
    def open(self) -> bool:
        return self.status == "pending"

    @property
    def first_payment(self) -> float:
        """What is held now: everything, or the first instalment."""
        if self.held > 0:
            return round(self.held, 2)
        return round(self.plan["amount"], 2) if self.plan else round(self.premium + self.fee, 2)

    def release(self) -> float:
        """The held amount, once; zero if it has already left escrow."""
        if self.released:
            return 0.0
        self.released = True
        return self.first_payment

    def to_dict(self, *, private: bool = False) -> dict[str, Any]:
        out = {
            "app_id": self.app_id, "peril": self.peril, "subject": dict(self.subject),
            "subject_text": self.subject_text, "limit": round(self.limit, 2),
            "term_days": self.term_days, "premium": round(self.premium, 2),
            "fee": round(self.fee, 2), "total": round(self.premium + self.fee, 2),
            "carrier_id": self.carrier_id, "checks": list(self.checks),
            "created_at": self.created_at, "decide_by": self.created_at + DECIDE_WITHIN,
            "status": self.status, "decided_at": self.decided_at,
            "decided_by": self.decided_by, "note": self.note,
            "checked": list(self.checked), "policy_id": self.policy_id,
            "contract_hash": self.contract_hash, "first_payment": self.first_payment,
            "plan": {k: v for k, v in (self.plan or {}).items() if k != "paid"} or None,
            "what": self.declared.get("what", ""), "country": self.declared.get("country", ""),
            "instruction": self.instruction_id or None,
        }
        if private:
            out["holder"] = self.holder
            out["address"] = self.address
            out["value_at_risk"] = round(self.value_at_risk, 2)
            out["size"] = self.size
        return out


class Applications:
    def __init__(self) -> None:
        self.applications: dict[str, Application] = {}
        self.lock = threading.RLock()

    def create(self, **fields: Any) -> Application:
        app = Application(app_id="APP-" + secrets.token_hex(5).upper(),
                          created_at=time.time(), **fields)
        app.held = app.first_payment
        with self.lock:
            self.applications[app.app_id] = app
        return app

    def begin_decision(self, app: Application) -> None:
        """Claim an open application for a decision, so two reviewers (or a
        reviewer and a withdrawal) cannot both act on it."""
        with self.lock:
            if not app.open:
                raise ApplicationError(f"that application is already {app.status}")
            app.status = "deciding"

    def reopen(self, app: Application) -> None:
        with self.lock:
            if app.status == "deciding":
                app.status = "pending"

    def require(self, app_id: str) -> Application:
        app = self.applications.get(app_id)
        if app is None:
            raise ApplicationError("no such application")
        return app

    def mine(self, holder: str) -> list[Application]:
        return sorted((a for a in self.applications.values() if a.holder == holder),
                      key=lambda a: -a.created_at)

    def for_carriers(self, carrier_ids: set[str] | None) -> list[Application]:
        rows = [a for a in self.applications.values()
                if carrier_ids is None or a.carrier_id in carrier_ids]
        return sorted(rows, key=lambda a: (not a.open, -a.created_at))

    def close(self, app: Application, status: str, *, by: str, note: str = "",
              checked: list[str] | None = None, policy_id: str | None = None,
              now: float | None = None) -> Application:
        with self.lock:
            deciding = app.status == "deciding" and status in ("approved", "rejected")
            if not app.open and not deciding:
                raise ApplicationError("a reviewer is deciding that application right now"
                                       if app.status == "deciding" else
                                       f"that application is already {app.status}")
            app.status = status
            app.decided_at = time.time() if now is None else now
            app.decided_by = by[:80]
            app.note = note[:400]
            app.checked = list(checked or [])
            app.policy_id = policy_id
        return app

    def overdue(self, now: float | None = None) -> list[Application]:
        now = time.time() if now is None else now
        return [a for a in self.applications.values()
                if a.open and now - a.created_at > DECIDE_WITHIN]
