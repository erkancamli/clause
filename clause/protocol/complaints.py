"""Complaints: raised on the policy, answered by the company on a clock,
and taken to the ombudsman with everything in one file when they are not.

A parametric policy pays on a reading, so most complaints are about the
reading, the timing or the money. The rules where the buyer lives give
the insurer a fixed time to answer (fifteen days in Türkiye, where the
Sigorta Tahkim Komisyonu then hears the dispute; eight weeks in the UK
before the Financial Ombudsman). This module keeps each complaint as a
thread on the policy with that deadline visible to both sides, and when
the deadline passes unanswered, or the answer does not settle it, it
assembles the application package: the policy's terms and contract hash,
every reading and settlement the chain recorded, the whole thread with
its timestamps, and where to take it. Nothing in the package is written
for the occasion; it is the record as it stood.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

DAY = 86400.0
SUBJECTS = ("settlement", "payment", "cover", "service", "other")
STATUSES = ("open", "answered", "closed", "escalated")


@dataclass(frozen=True, slots=True)
class Route:
    """Who hears the dispute where the buyer lives, and how long the
    insurer has to answer first."""
    answer_days: float
    body: str
    links: tuple[tuple[str, str], ...]
    note: str


ROUTES: dict[str, Route] = {
    "TR": Route(15, "Sigorta Tahkim Komisyonu", (
        ("Sigorta Tahkim Komisyonu: başvuru", "https://www.sigortatahkim.org/"),
        ("SEDDK'ya şikâyet, e-Devlet üzerinden", "https://www.turkiye.gov.tr/hm-sigortacilik-sikayet-basvuru-ve-takip"),
        ("CİMER", "https://www.cimer.gov.tr/"),
    ), "The insurer has fifteen days to answer in writing. After that, or if the answer does not settle it, "
       "the Sigorta Tahkim Komisyonu takes the application; the policy must carry the insurer's membership, "
       "which every licensed insurer in Türkiye holds."),
    "GB": Route(56, "Financial Ombudsman Service", (
        ("Financial Ombudsman Service", "https://www.financial-ombudsman.org.uk/"),
    ), "The insurer has eight weeks to give a final response. After that, or within six months of it, the "
       "Financial Ombudsman Service takes the complaint."),
}
DEFAULT_ROUTE = Route(15, "the insurance ombudsman where you live", (
    ("FIN-NET, the EU network of financial ombudsmen", "https://finance.ec.europa.eu/consumer-finance-and-payments/retail-financial-services/financial-dispute-resolution-network-fin-net_en"),
), "The insurer has fifteen days to answer under this protocol's own rule; the ombudsman where you live "
   "hears it after that, on its own terms.")


def route_for(country: str | None) -> Route:
    return ROUTES.get((country or "").upper(), DEFAULT_ROUTE)


class ComplaintError(ValueError):
    pass


@dataclass(slots=True)
class Complaint:
    complaint_id: str
    policy_id: str
    holder: str
    carrier_id: str
    country: str
    subject: str
    opened_at: float
    deadline_at: float
    status: str = "open"
    messages: list[dict[str, Any]] = field(default_factory=list)   # {who, text, at}
    answered_at: float | None = None
    closed_at: float | None = None
    escalated_at: float | None = None
    resolution: str = ""

    def days_left(self, now: float | None = None) -> float:
        now = time.time() if now is None else now
        return (self.deadline_at - now) / DAY

    def overdue(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return self.status == "open" and now > self.deadline_at

    def to_dict(self, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        return {"complaint_id": self.complaint_id, "policy_id": self.policy_id, "holder": self.holder,
                "carrier_id": self.carrier_id, "country": self.country, "subject": self.subject,
                "opened_at": self.opened_at, "deadline_at": self.deadline_at,
                "days_left": round(self.days_left(now), 1), "overdue": self.overdue(now),
                "status": self.status, "messages": list(self.messages), "answered_at": self.answered_at,
                "closed_at": self.closed_at, "escalated_at": self.escalated_at, "resolution": self.resolution,
                "can_escalate": self.status in ("answered",) or self.overdue(now)}


class Complaints:
    def __init__(self) -> None:
        self.complaints: dict[str, Complaint] = {}
        self.lock = threading.RLock()

    # -- raising and answering -------------------------------------------------

    def open(self, policy: Any, *, subject: str, text: str, now: float | None = None) -> Complaint:
        now = time.time() if now is None else now
        subject = (subject or "other").strip().lower()
        if subject not in SUBJECTS:
            raise ComplaintError("say what the complaint is about: " + ", ".join(SUBJECTS))
        text = (text or "").strip()
        if len(text) < 10:
            raise ComplaintError("say what happened, in at least a sentence")
        meta = policy.metadata or {}
        country = ((meta.get("interest") or {}).get("resident") or (meta.get("interest") or {}).get("country") or "").upper()
        with self.lock:
            for c in self.complaints.values():
                if c.policy_id == policy.policy_id and c.status in ("open", "answered"):
                    raise ComplaintError(f"a complaint on this policy is already open: {c.complaint_id}")
            route = route_for(country)
            complaint = Complaint(complaint_id="CMP-" + secrets.token_hex(5).upper(), policy_id=policy.policy_id,
                                  holder=policy.holder, carrier_id=str(meta.get("carrier") or ""), country=country,
                                  subject=subject, opened_at=now, deadline_at=now + route.answer_days * DAY,
                                  messages=[{"who": "holder", "text": text[:4000], "at": now}])
            self.complaints[complaint.complaint_id] = complaint
        return complaint

    def reply(self, complaint_id: str, *, who: str, text: str, now: float | None = None) -> Complaint:
        """A message on the thread. The company's first message is the
        answer the clock was waiting for."""
        now = time.time() if now is None else now
        text = (text or "").strip()
        if not text:
            raise ComplaintError("an empty message says nothing")
        if who not in ("holder", "company", "operator"):
            raise ComplaintError("who is writing?")
        with self.lock:
            c = self._get(complaint_id)
            if c.status in ("closed",):
                raise ComplaintError("this complaint is closed")
            c.messages.append({"who": who, "text": text[:4000], "at": now})
            if who == "company" and c.status == "open":
                c.status = "answered"
                c.answered_at = now
        return c

    def close(self, complaint_id: str, *, by: str, resolution: str, now: float | None = None) -> Complaint:
        now = time.time() if now is None else now
        with self.lock:
            c = self._get(complaint_id)
            c.status = "closed"
            c.closed_at = now
            c.resolution = (resolution or "").strip()[:1000]
            c.messages.append({"who": by, "text": "closed: " + c.resolution, "at": now})
        return c

    def escalate(self, complaint_id: str, *, now: float | None = None) -> Complaint:
        """The holder takes it to the ombudsman: allowed once the company
        has answered, or once its time to answer has run out."""
        now = time.time() if now is None else now
        with self.lock:
            c = self._get(complaint_id)
            if c.status == "closed":
                raise ComplaintError("this complaint is closed; open another if something is still wrong")
            if not (c.status == "answered" or c.overdue(now)):
                raise ComplaintError(f"the company has until {time.strftime('%Y-%m-%d', time.gmtime(c.deadline_at))} to answer; "
                                     "the ombudsman takes it after that")
            c.status = "escalated"
            c.escalated_at = now
            c.messages.append({"who": "holder", "text": "taken to " + route_for(c.country).body, "at": now})
        return c

    def _get(self, complaint_id: str) -> Complaint:
        c = self.complaints.get(complaint_id)
        if c is None:
            raise ComplaintError("no such complaint")
        return c

    # -- reading -----------------------------------------------------------------

    def get(self, complaint_id: str) -> Complaint | None:
        return self.complaints.get(complaint_id)

    def for_holder(self, holder: str) -> list[Complaint]:
        return sorted((c for c in self.complaints.values() if c.holder == holder), key=lambda c: -c.opened_at)

    def for_policy(self, policy_id: str) -> list[Complaint]:
        return sorted((c for c in self.complaints.values() if c.policy_id == policy_id), key=lambda c: -c.opened_at)

    def for_carrier(self, carrier_id: str) -> list[Complaint]:
        return sorted((c for c in self.complaints.values() if c.carrier_id == carrier_id),
                      key=lambda c: (c.status not in ("open",), c.deadline_at))

    def summary(self, rows: Iterable[Complaint], now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        rows = list(rows)
        open_ = [c for c in rows if c.status == "open"]
        return {"total": len(rows), "open": len(open_), "overdue": sum(1 for c in open_ if c.overdue(now)),
                "due_soon": sum(1 for c in open_ if 0 <= c.days_left(now) <= 3),
                "answered": sum(1 for c in rows if c.status == "answered"),
                "escalated": sum(1 for c in rows if c.status == "escalated"),
                "closed": sum(1 for c in rows if c.status == "closed")}

    # -- the package for the ombudsman ------------------------------------------------

    @staticmethod
    def package(complaint: Complaint, *, policy: dict[str, Any], contract_hash: str | None,
                lineage: dict[str, Any] | None, settlements: list[dict[str, Any]], carrier: dict[str, Any] | None,
                now: float | None = None) -> dict[str, Any]:
        """Everything the ombudsman's form asks for, as the record stands."""
        now = time.time() if now is None else now
        route = route_for(complaint.country)
        return {
            "prepared_at": now, "complaint": complaint.to_dict(now),
            "route": {"body": route.body, "answer_days": route.answer_days, "note": route.note,
                      "links": [{"name": n, "url": u} for n, u in route.links]},
            "policy": policy, "contract_hash": contract_hash, "insurer": carrier,
            "settlements": settlements, "readings": (lineage or {}).get("readings") or (lineage or {}).get("rounds"),
            "lineage": lineage,
        }

    @staticmethod
    def package_text(package: dict[str, Any]) -> str:
        """The same, as a document a person can attach."""
        c = package["complaint"]
        p = package["policy"] or {}
        when = lambda t: time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t)) if t else "-"
        lines = [
            "COMPLAINT FILE, prepared " + when(package["prepared_at"]),
            "",
            f"Complaint {c['complaint_id']} on policy {c['policy_id']}: {c['subject']}",
            f"Opened {when(c['opened_at'])}; the insurer's time to answer ran to {when(c['deadline_at'])}; status {c['status']}.",
            f"Insurer: {(package.get('insurer') or {}).get('name', c['carrier_id'])}",
            "",
            "THE POLICY",
            f"  Peril: {p.get('peril_key')}   Subject: {json.dumps(p.get('subject'), ensure_ascii=False)}",
            f"  Limit: {p.get('limit')}   Premium: {p.get('premium')}   Term: {when(p.get('starts_at'))} to {when(p.get('ends_at'))}",
            f"  Status: {p.get('status')}   Paid out: {p.get('payout')}   Predicate: {p.get('predicate')}",
            f"  Contract hash: {package.get('contract_hash') or '-'}",
            "",
            "SETTLEMENTS THE CHAIN RECORDED",
        ]
        for s in package.get("settlements") or []:
            lines.append(f"  {when(s.get('at'))}: {s.get('kind')} {s.get('amount')} on index {s.get('index_value')} ({s.get('summary', '')})")
        if not package.get("settlements"):
            lines.append("  none")
        lines += ["", "THE THREAD"]
        for m in c["messages"]:
            lines.append(f"  {when(m['at'])} {m['who']}: {m['text']}")
        lines += ["", "WHERE IT GOES", "  " + package["route"]["note"]]
        for link in package["route"]["links"]:
            lines.append(f"  {link['name']}: {link['url']}")
        return "\n".join(lines) + "\n"
