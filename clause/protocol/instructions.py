"""Standing instructions: cover bought later, on terms signed now.

Rider's mandate lets a model buy within limits when a person asks it to. An
instruction is the other way round: nobody asks, the protocol acts by itself
when a condition the person set comes true. Two kinds, both in Latch's
spirit of "a permission with its terms written on it":

    renew   keep this policy in force: when it is a day from its end, buy
            the same cover again for another term, as long as the price is
            at or under the cap I signed
    buy     buy this cover from a date onwards: the day my home is ten
            years old, the day my car passes the age I named, or simply a
            date

The person signs the whole purchase in advance: peril, subject, cover, term,
what is at risk, the company, the most it may cost, until when the
instruction stands. When it runs it goes through exactly the path a purchase
by hand goes through: a home or a car is applied for and the issuing company
still decides; a harvest is bought outright. The money is the balance at the
address at that moment; if it is not there, the instruction waits a day and
tries again, and says so.

Every attempt is recorded on the instruction, so "why was this not renewed"
has an answer: the price was over the cap, the balance was short, the
company refused. The person sees the list and can cancel at any time. An
instruction stands for at most ten years and is spent when it has bought
what it was for.
"""

from __future__ import annotations

import datetime as _dt
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

KINDS = ("renew", "buy")
MAX_DAYS = 3650                  # ten years: "when my home is ten years old" has to fit
RENEW_LEAD = 86400.0             # act a day before the policy ends
RENEW_GRACE = 30 * 86400.0       # a policy that ended longer ago than this is not renewed
RETRY_AFTER = 86400.0            # a failed attempt is tried again a day later
MAX_LIVE_PER_ACCOUNT = 12


class InstructionError(ValueError):
    """An instruction this module refuses. Safe to show."""


@dataclass(slots=True)
class Instruction:
    instruction_id: str
    account: str
    kind: str
    peril: str
    subject: dict[str, Any]
    limit: float
    term_days: float
    declared: dict[str, Any]         # the interest declaration, as the person made it
    size: dict[str, Any] | None
    value_at_risk: float
    settlement: str
    carrier_id: str | None
    address: dict[str, str] | None   # of the home, or where the car is kept
    max_premium: float               # the most one purchase may cost
    instalments: int
    expires_at: float
    created_at: float
    policy_id: str = ""              # renew: the policy being followed
    from_at: float | None = None     # buy: not before this moment
    condition: dict[str, Any] = field(default_factory=dict)   # what "when" means, for the person
    status: str = "live"             # live | waiting | done | cancelled | expired
    next_at: float = 0.0             # earliest next attempt
    application_id: str = ""         # waiting: the application the company is deciding
    bought: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    # The statements checked when the instruction was signed, and when they
    # run out: what a purchase would otherwise ask the person for.
    claims: tuple[str, ...] = ()
    claims_expire_at: float | None = None

    @property
    def open(self) -> bool:
        return self.status in ("live", "waiting")

    def terms(self) -> dict[str, Any]:
        """What the person signed, exactly."""
        out: dict[str, Any] = {
            "kind": self.kind, "peril": self.peril, "subject": self.subject, "limit": self.limit,
            "term_days": self.term_days, "max_premium": self.max_premium,
            "days": round((self.expires_at - self.created_at) / 86400.0),
        }
        if self.kind == "renew":
            out["policy_id"] = self.policy_id
        else:
            out["from_at"] = float(self.from_at or 0.0)
        if self.carrier_id:
            out["carrier_id"] = self.carrier_id
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction_id": self.instruction_id, "kind": self.kind, "peril": self.peril,
            "subject": dict(self.subject), "limit": self.limit, "term_days": self.term_days,
            "max_premium": self.max_premium, "instalments": self.instalments,
            "carrier_id": self.carrier_id, "policy_id": self.policy_id or None,
            "from_at": self.from_at, "condition": dict(self.condition), "status": self.status,
            "next_at": self.next_at or None, "application_id": self.application_id or None,
            "expires_at": self.expires_at, "created_at": self.created_at,
            "bought": list(self.bought), "attempts": list(self.attempts[-12:]), "note": self.note,
            "claims": list(self.claims), "claims_expire_at": self.claims_expire_at,
        }


def year_start(year: int) -> float:
    return _dt.datetime(year, 1, 1, tzinfo=_dt.timezone.utc).timestamp()


def from_condition(body: dict[str, Any], size: dict[str, Any] | None, *, now: float) -> tuple[float, dict[str, Any]]:
    """When a buy instruction becomes due, from what the person said.

        {"when": "date", "at": <timestamp>}
        {"when": "age", "years": N}      the home (built) or the car
                                         (model_year) reaching N years

    The age is counted the way the valuation counts it: from the first day
    of the year the thing reaches that age."""
    when = str(body.get("when") or "date")
    if when == "date":
        try:
            at = float(body.get("at") or 0.0)
        except (TypeError, ValueError) as error:
            raise InstructionError("say the date") from error
        if not now - 86400 <= at <= now + MAX_DAYS * 86400:
            raise InstructionError(f"a date within the next {MAX_DAYS // 365} years")
        return at, {"when": "date", "at": at}
    if when == "age":
        try:
            years = int(body.get("years") or 0)
        except (TypeError, ValueError) as error:
            raise InstructionError("say the age in years") from error
        if not 1 <= years <= 60:
            raise InstructionError("an age between 1 and 60 years")
        born = None
        if size:
            born = size.get("built") or size.get("model_year")
        if not born:
            raise InstructionError("the year it was built, or the model year, is needed to count its age")
        at = year_start(int(born) + years)
        if at > now + MAX_DAYS * 86400:
            raise InstructionError(f"that is more than {MAX_DAYS // 365} years away; an instruction stands for at most that")
        what = "home" if size and "built" in size else "car"
        return max(at, now), {"when": "age", "what": what, "born": int(born), "years": years, "year": int(born) + years}
    raise InstructionError("say when: a date, or an age")


class Instructions:
    def __init__(self) -> None:
        self.instructions: dict[str, Instruction] = {}
        self.lock = threading.RLock()

    # -- giving one --------------------------------------------------------

    def create(self, account: str, *, kind: str, peril: str, subject: dict[str, Any], limit: float,
               term_days: float, declared: dict[str, Any], size: dict[str, Any] | None,
               value_at_risk: float, settlement: str, carrier_id: str | None,
               address: dict[str, str] | None, max_premium: float, instalments: int, days: int,
               policy_id: str = "", condition: dict[str, Any] | None = None,
               claims: tuple[str, ...] = (), claims_expire_at: float | None = None,
               now: float | None = None) -> Instruction:
        now = time.time() if now is None else now
        if kind not in KINDS:
            raise InstructionError("an instruction renews a policy or buys cover from a date")
        if not (0 < max_premium <= 100_000):
            raise InstructionError("name the most one purchase may cost")
        if not (1 <= days <= MAX_DAYS):
            raise InstructionError(f"an instruction stands between 1 and {MAX_DAYS} days")
        from_at, words = None, {"when": "renew"}
        if kind == "renew":
            if not policy_id:
                raise InstructionError("say which policy to keep in force")
        else:
            from_at, words = from_condition(condition or {}, size, now=now)
        with self.lock:
            live = [i for i in self.instructions.values() if i.account == account and i.open]
            if len(live) >= MAX_LIVE_PER_ACCOUNT:
                raise InstructionError(f"at most {MAX_LIVE_PER_ACCOUNT} instructions may stand at once")
            if kind == "renew":
                for other in live:
                    if other.kind == "renew" and other.policy_id == policy_id:
                        raise InstructionError("that policy already has a renewal instruction")
            item = Instruction(
                instruction_id="INS-" + secrets.token_hex(4).upper(), account=account, kind=kind,
                peril=peril, subject=dict(subject), limit=float(limit), term_days=float(term_days),
                declared=dict(declared), size=dict(size) if size else None,
                value_at_risk=float(value_at_risk), settlement=settlement, carrier_id=carrier_id,
                address=dict(address) if address else None, max_premium=round(float(max_premium), 2),
                instalments=max(1, int(instalments)), expires_at=now + days * 86400.0, created_at=now,
                policy_id=policy_id, from_at=from_at, condition=words, next_at=from_at or 0.0,
                claims=tuple(claims), claims_expire_at=claims_expire_at,
            )
            self.instructions[item.instruction_id] = item
        return item

    def mine(self, account: str) -> list[Instruction]:
        return sorted((i for i in self.instructions.values() if i.account == account),
                      key=lambda i: -i.created_at)

    def cancel(self, account: str, instruction_id: str, *, now: float | None = None) -> Instruction:
        now = time.time() if now is None else now
        with self.lock:
            item = self.instructions.get(instruction_id)
            if item is None or item.account != account:
                raise InstructionError("no such instruction")
            if not item.open:
                raise InstructionError(f"that instruction is already {item.status}")
            item.status = "cancelled"
            item.attempts.append({"at": now, "outcome": "cancelled"})
        return item

    def following(self, policy_id: str) -> Instruction | None:
        return next((i for i in self.instructions.values()
                     if i.kind == "renew" and i.open and i.policy_id == policy_id), None)

    # -- running -----------------------------------------------------------

    def due(self, policies: dict[str, Any], *, now: float | None = None) -> list[Instruction]:
        """The instructions whose moment has come. Expires the ones past
        their date and drops a renewal whose policy was cancelled."""
        now = time.time() if now is None else now
        out = []
        with self.lock:
            for item in self.instructions.values():
                if item.status != "live":
                    continue
                if now > item.expires_at:
                    item.status = "expired"
                    item.attempts.append({"at": now, "outcome": "expired"})
                    continue
                if item.next_at > now:
                    continue
                if item.kind == "buy":
                    if item.from_at is not None and now >= item.from_at:
                        out.append(item)
                    continue
                policy = policies.get(item.policy_id)
                if policy is None:
                    item.status = "cancelled"
                    item.note = "the policy it followed is gone"
                    item.attempts.append({"at": now, "outcome": "cancelled", "note": item.note})
                    continue
                status = getattr(policy.status, "value", policy.status)
                if status == "cancelled":
                    item.status = "cancelled"
                    item.note = "the policy was cancelled by its holder"
                    item.attempts.append({"at": now, "outcome": "cancelled", "note": item.note})
                    continue
                ends_at = float(policy.ends_at)
                if now < ends_at - RENEW_LEAD:
                    continue
                if now > ends_at + RENEW_GRACE:
                    item.status = "expired"
                    item.note = "the policy ended more than a month ago"
                    item.attempts.append({"at": now, "outcome": "expired", "note": item.note})
                    continue
                out.append(item)
        return out

    def record(self, item: Instruction, outcome: str, *, note: str = "", policy_id: str = "",
               application_id: str = "", now: float | None = None) -> None:
        """What one attempt did.

            bought      a policy was written; a renewal now follows it
            applied     an application is with the company; wait for it
            declined    the company refused the application; the person is told
            waiting     nothing bought this time (price over the cap, short balance,
                        a refusal); tried again after RETRY_AFTER
        """
        now = time.time() if now is None else now
        with self.lock:
            entry: dict[str, Any] = {"at": now, "outcome": outcome}
            if note:
                entry["note"] = note[:200]
            if policy_id:
                entry["policy_id"] = policy_id
            if application_id:
                entry["application_id"] = application_id
            item.attempts.append(entry)
            item.note = note[:200]
            if outcome == "bought":
                item.bought.append(policy_id)
                item.application_id = ""
                if item.kind == "renew":
                    item.policy_id = policy_id
                    item.status = "live"
                    item.next_at = 0.0
                else:
                    item.status = "done"
            elif outcome == "applied":
                item.application_id = application_id
                item.status = "waiting"
            elif outcome == "declined":
                item.application_id = ""
                item.status = "done" if item.kind == "buy" else "live"
                # A renewal the company refused is not tried again on the same
                # policy: it would only be refused again.
                if item.kind == "renew":
                    item.status = "cancelled"
            else:
                item.status = "live"
                item.next_at = now + RETRY_AFTER

    def waiting_on(self) -> list[Instruction]:
        return [i for i in self.instructions.values() if i.status == "waiting" and i.application_id]

    def settle_waiting(self, applications: dict[str, Any], *, now: float | None = None) -> int:
        """Applications the instructions made that the company has decided."""
        n = 0
        for item in self.waiting_on():
            app_ = applications.get(item.application_id)
            if app_ is None:
                self.record(item, "declined", note="the application is gone", now=now)
                n += 1
                continue
            status = getattr(app_, "status", "")
            if status == "approved":
                self.record(item, "bought", policy_id=str(getattr(app_, "policy_id", "") or ""),
                            note="approved by the company", now=now)
                n += 1
            elif status in ("rejected", "withdrawn", "lapsed"):
                self.record(item, "declined", note=str(getattr(app_, "note", "") or "refused by the company"),
                            now=now)
                n += 1
        return n
