"""Letting a company in: what the operator checks, where, and the record.

A company registers with a name, a licence number and some documents. None
of that is proof; the work that turns a registration into a company that
may write is the operator's, and it has a shape. This module gives it one:
a checklist per company, each item saying what to confirm, at which public
register, and what the company's own documents contribute; each item
recorded when done, with who, when, where they looked and what they saw.
Activation needs every required item confirmed. A year on, the checklist
is due again, because licences lapse, companies are sold and sanctions
lists change.

Two automatic checks feed the list (the LEI record and control of the
domain, from ``kyb``); everything else is a person reading a register the
protocol cannot read for them. Documents the company uploads are shown
beside the item they support and never taken as proof on their own: a PDF
can be edited, a register cannot.
"""

from __future__ import annotations

import time
from typing import Any

from . import kyb

REVERIFY_AFTER_DAYS = 365.0
DUE_SOON_DAYS = 30.0

# The classes of business a licence has to name, by country, for each peril
# this protocol writes. Where the supervisor licenses by branch the reviewer
# confirms the branch, not just that a licence exists.
BRANCHES: dict[str, dict[str, str]] = {
    "TR": {
        "earthquake": "Yangın ve Doğal Afetler",
        "storm": "Yangın ve Doğal Afetler",
        "vehicle_flood": "Kara Araçları",
        "drought": "Genel Zararlar (tarım ürünleri; Türkiye'de devlet destekli kuraklık teminatı TARSİM havuzu üzerinden yazılır)",
        "flight_delay": "Finansal Kayıplar",
    },
}

EXTRA_LINKS: dict[str, list[tuple[str, str]]] = {
    "TR": [
        ("MERSİS, Merkezi Sicil Kayıt Sistemi (tüzel kişilik, yetkililer)", "https://mersis.ticaret.gov.tr/"),
        ("Türkiye Ticaret Sicili Gazetesi (kuruluş, imza yetkileri)", "https://www.ticaretsicil.gov.tr/"),
        ("SEDDK, sigortacılık sektörü duyuru ve kararları", "https://www.seddk.gov.tr/"),
        ("Türkiye Sigorta Birliği, üye şirketler", "https://www.tsb.org.tr/"),
    ],
}

SANCTIONS_LINKS = [
    ("UN Security Council consolidated list", "https://www.un.org/securitycouncil/content/un-sc-consolidated-list"),
    ("EU sanctions map", "https://www.sanctionsmap.eu/"),
    ("OFAC sanctions list search", "https://sanctionssearch.ofac.treas.gov/"),
    ("MASAK, malvarlığı dondurma kararları (Türkiye)", "https://masak.hmb.gov.tr/"),
]

EVIDENCE_KINDS = (
    "licence_certificate", "register_extract", "authorisation_letter", "trade_registry_gazette",
    "signature_circular", "membership_proof", "solvency_report", "data_agreement", "other",
)


def _links(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"name": n, "url": u} for n, u in pairs]


def checklist_for(carrier: Any) -> list[dict[str, Any]]:
    """The items for this company, with what is known about each."""
    domicile = (getattr(carrier, "domicile", "") or "").upper()
    role = getattr(getattr(carrier, "role", None), "value", str(getattr(carrier, "role", "")))
    verification = getattr(carrier, "verification", None) or {}
    perils = sorted(set(getattr(carrier, "appetite", None).perils) if getattr(carrier, "appetite", None) else set())
    licences = list(getattr(carrier, "licences", ()) or ())
    evidence = list(getattr(carrier, "evidence", []) or [])
    branches = BRANCHES.get(domicile, {})
    needed = sorted({branches[p] for p in perils if p in branches})
    registers = kyb.register_links(domicile, reference=licences[0].reference if licences else "",
                                   name=getattr(carrier, "name", ""), lei=getattr(carrier, "lei", ""))
    lei = verification.get("lei") or {}
    domain = verification.get("domain") or {}

    items: list[dict[str, Any]] = [
        {"key": "entity", "required": True,
         "title": "The legal entity exists and is this company",
         "what": ("The registered name, status and country on the official record match the registration. "
                  "Automatic where an LEI was given; otherwise the trade register."),
         "where": (_links(EXTRA_LINKS.get(domicile, [])[:2]) + ([{"name": "GLEIF, the LEI record",
                    "url": f"https://search.gleif.org/#/record/{lei.get('lei')}"}] if lei.get("lei") else [])),
         "evidence": ["register_extract", "trade_registry_gazette"],
         "auto": {"ok": lei.get("ok"), "summary": lei.get("summary", "")} if lei else None},
        {"key": "domain", "required": True,
         "title": "Whoever registered controls the company's domain",
         "what": ("The proof file on the company's own website names the registering address. Automatic. "
                  "With no domain, a letter of authorisation on the company's paper stands in."),
         "where": [],
         "evidence": ["authorisation_letter"],
         "auto": {"ok": domain.get("ok"), "summary": domain.get("summary", "")} if domain else None},
        {"key": "licence", "required": role == "carrier",
         "title": "The licence is held, in force, and covers these classes",
         "what": ("Every reference on the record is at the supervisor's own register, held by this company, in force, "
                  + (f"and authorised for: {'; '.join(needed)}." if needed else "and for the classes the perils need.")),
         "where": registers,
         "evidence": ["licence_certificate"],
         "auto": None,
         "branches": needed},
        {"key": "signatory", "required": True,
         "title": "The person registering may bind the company",
         "what": ("The trade register's authorised signatories, a signature circular or a letter of authorisation "
                  "name the person who registered, and the contact given reaches the company."),
         "where": _links(EXTRA_LINKS.get(domicile, [])[:2]),
         "evidence": ["signature_circular", "authorisation_letter", "trade_registry_gazette"],
         "auto": None},
        {"key": "sanctions", "required": True,
         "title": "Not sanctioned: the company, its controllers, its directors",
         "what": "Screened against the UN, EU and OFAC lists and the domestic asset freeze list, on the day.",
         "where": _links(SANCTIONS_LINKS),
         "evidence": [],
         "auto": None},
        {"key": "enforcement", "required": True,
         "title": "No live suspension, penalty or run-off at the supervisor",
         "what": "The supervisor's announcements and decisions, and the register's status field, show nothing open.",
         "where": registers[:1] + _links(EXTRA_LINKS.get(domicile, [])[2:3]),
         "evidence": [],
         "auto": None},
    ]
    if domicile == "TR" and role == "carrier":
        items.append({"key": "membership", "required": True,
                      "title": "Member of Türkiye Sigorta Birliği",
                      "what": "Every licensed insurer in Türkiye is a member; the member list names it.",
                      "where": _links(EXTRA_LINKS["TR"][3:4]),
                      "evidence": ["membership_proof"],
                      "auto": None})
    items += [
        {"key": "solvency", "required": False,
         "title": "Financially sound: the last published solvency figures",
         "what": "The latest solvency ratio or audited accounts, as published by the company or the supervisor.",
         "where": registers[:1],
         "evidence": ["solvency_report"],
         "auto": None},
        {"key": "data_agreement", "required": False,
         "title": "A data processing agreement is in place",
         "what": "The company receives buyers' addresses and documents; the agreement that governs that is signed.",
         "where": [],
         "evidence": ["data_agreement"],
         "auto": None},
    ]
    state = getattr(carrier, "vetting", None) or {}
    for item in items:
        item["documents"] = [{"n": e.get("n"), "kind": e.get("kind"), "filename": e.get("filename", "")}
                             for e in evidence if e.get("kind") in item["evidence"]]
        item["state"] = dict(state.get(item["key"], {})) or None
        auto_ok = bool(item["auto"] and item["auto"].get("ok"))
        manual = item["state"] or {}
        item["done"] = bool(manual.get("ok")) or (auto_ok and manual.get("ok") is not False)
        item["settled"] = item["done"] or manual.get("ok") is False or manual.get("ok") is None and bool(manual)
    return items


def missing(carrier: Any) -> list[str]:
    """Required items not yet confirmed."""
    return [i["key"] for i in checklist_for(carrier) if i["required"] and not i["done"]]


def record(carrier: Any, *, key: str, ok: bool | None, source: str, note: str, by: str,
           now: float | None = None) -> dict[str, Any]:
    keys = {i["key"] for i in checklist_for(carrier)}
    if key not in keys:
        raise ValueError(f"no such check: {key}")
    entry = {"ok": ok, "source": (source or "").strip()[:300], "note": (note or "").strip()[:400],
             "by": (by or "operator").strip()[:80], "at": time.time() if now is None else now}
    if getattr(carrier, "vetting", None) is None:
        carrier.vetting = {}
    carrier.vetting[key] = entry
    return entry


def due(carrier: Any, now: float | None = None) -> dict[str, Any]:
    """Whether this company's checks are due again, and its licences soon out."""
    now = time.time() if now is None else now
    review_at = getattr(carrier, "review_due_at", None)
    soon = [l for l in (getattr(carrier, "licences", ()) or ()) if l.expiring()]
    lapsed = [l for l in (getattr(carrier, "licences", ()) or ()) if not l.live(now=now)]
    return {
        "review_due_at": review_at,
        "review_overdue": bool(review_at and review_at <= now),
        "review_due_soon": bool(review_at and now < review_at <= now + DUE_SOON_DAYS * 86400),
        "licences_expiring": [l.reference for l in soon],
        "licences_lapsed": [l.reference for l in lapsed],
    }


def summary(carrier: Any) -> dict[str, Any]:
    items = checklist_for(carrier)
    return {"items": items, "missing": [i["key"] for i in items if i["required"] and not i["done"]],
            "required": sum(1 for i in items if i["required"]),
            "done": sum(1 for i in items if i["done"]), **due(carrier)}
