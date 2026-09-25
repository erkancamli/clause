"""The three bordereaux an insurer's delegated-authority desk expects, in
the shape it expects them: what was written, what was paid, and whether
the money adds up.

A fee statement is an accountant's view: every movement, in order. A
bordereau is the underwriter's and the reinsurer's: one line per risk
written in the month with its dates, limit, premium and the shares taken
out of it (the risk or premium bordereau); one line per claim with the
date of loss, the index that triggered it and what was paid (the claims
or paid bordereau); and a monthly reconciliation that puts the two beside
the fee ledger and says whether they agree, and by how much they do not.
The field logic follows Lloyd's Coverholder Reporting Standards; the
names are plain.

Nothing here is computed after the fact from rates that may have changed:
each line is read off the policy, the settlement and the fee entry as
they were recorded.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any, Iterable

from . import desk
from .fees import month_of

RISK_COLUMNS = ("reference", "insured", "peril", "subject", "province", "country", "inception", "expiry",
                "limit", "gross_premium", "tax", "tax_basis", "fronting_fee", "fee_paid", "platform_fee", "platform_fee_paid",
                "net_fee_to_carrier", "instalments", "status", "bound_at")
CLAIMS_COLUMNS = ("reference", "kind", "date_of_loss", "index_value", "unit", "paid", "premium_returned",
                  "status", "note")
RECON_COLUMNS = ("item", "amount")


#: Premium taxes a carrier owes on cover this protocol writes, by country and
#: branch. The bordereau booked a hardcoded zero in this column for every
#: policy in every country, which reads as a figure somebody computed.
#:
#: Türkiye: the fire insurance tax under the Municipal Revenues Law 2464,
#: articles 40 to 44, is ten per cent of the premium on fire cover for
#: buildings and their contents inside a municipality. This protocol's own
#: branch table puts earthquake and storm in Yangın ve Doğal Afetler, the fire
#: branch, so on its own reading of where these policies sit the tax applies.
#:
#: Whether it reaches an index policy specifically is a question for the
#: carrier's tax advice and not for this file, and the bordereau says so in
#: the note beside the figure. Reporting it and being told it does not apply
#: costs a correction; reporting zero and being wrong costs the tax plus
#: interest, and the carrier is the one who owes it.
PREMIUM_TAX: dict[str, dict[str, tuple[float, str]]] = {
    "TR": {
        "earthquake": (0.10, "Yangın Sigortası Vergisi, Law 2464 arts. 40-44, "
                             "on the fire branch this policy is written in"),
        "storm": (0.10, "Yangın Sigortası Vergisi, Law 2464 arts. 40-44, "
                        "on the fire branch this policy is written in"),
    },
}


def premium_tax(country: str, peril_key: str, premium: float) -> tuple[float, str]:
    """What is owed on this premium, and under what. Zero where nothing is."""
    rate, basis = PREMIUM_TAX.get((country or "").upper(), {}).get(
        peril_key, (0.0, ""))
    return round(premium * rate, 2), basis


def _iso(at: float | None) -> str:
    return dt.datetime.fromtimestamp(at, dt.timezone.utc).isoformat(timespec="seconds") if at else ""


def risk_bordereau(policies: Iterable[Any], *, carrier_id: str | None, month: str,
                   names: dict[str, str] | None = None, private: bool = False) -> dict[str, Any]:
    """One line per policy bound in the month on this carrier's paper (every
    carrier's when carrier_id is None)."""
    rows = []
    for p in policies:
        meta = p.metadata or {}
        if carrier_id and meta.get("carrier") != carrier_id:
            continue
        if not meta.get("carrier") or month_of(p.bought_at) != month:
            continue
        base = desk.row_of(p, names=names, private=private)
        fee_paid = round(float(meta.get("fee_paid", meta.get("fronting_fee", 0.0)) or 0.0), 2)
        platform_paid = round(float(meta.get("platform_fee_paid", 0.0) or 0.0), 2)
        _tax, _basis = premium_tax(base["country"], p.peril_key, p.premium)
        rows.append({
            "reference": p.policy_id,
            "insured": base["address"] if private and base.get("address") else base["holder"],
            "peril": p.peril_key, "subject": base["subject"], "province": base["province"], "country": base["country"],
            "inception": _iso(p.starts_at), "expiry": _iso(p.ends_at),
            "limit": round(p.limit, 2), "gross_premium": round(p.premium, 2),
            "tax": _tax, "tax_basis": _basis,
            "fronting_fee": round(float(meta.get("fronting_fee", 0.0) or 0.0), 2), "fee_paid": fee_paid,
            "platform_fee": round(float(meta.get("platform_fee", 0.0) or 0.0), 2), "platform_fee_paid": platform_paid,
            "net_fee_to_carrier": round(fee_paid - platform_paid, 2),
            "instalments": int((meta.get("plan") or {}).get("count", 1) or 1),
            "status": p.status.value, "bound_at": _iso(p.bought_at),
            "carrier_id": meta.get("carrier"), "carrier": base.get("carrier"),
        })
    rows.sort(key=lambda r: r["bound_at"])
    totals = {k: round(sum(r[k] for r in rows), 2) for k in
              ("limit", "gross_premium", "tax", "fronting_fee", "fee_paid", "platform_fee", "platform_fee_paid", "net_fee_to_carrier")}
    return {"kind": "risk", "month": month, "carrier_id": carrier_id, "rows": rows, "count": len(rows), "totals": totals}


def claims_bordereau(policies: Iterable[Any], settlements: Iterable[Any], *, carrier_id: str | None,
                     month: str) -> dict[str, Any]:
    """One line per settlement that paid in the month, and one per premium
    returned on cancellation, on this carrier's paper."""
    by_id = {p.policy_id: p for p in policies}
    rows = []
    for s in settlements:
        p = by_id.get(s.policy_id)
        if p is None:
            continue
        meta = p.metadata or {}
        if carrier_id and meta.get("carrier") != carrier_id:
            continue
        if not meta.get("carrier") or month_of(s.at) != month or s.kind != "paid":
            continue
        rows.append({"reference": p.policy_id, "kind": "claim", "date_of_loss": _iso(s.at),
                     "index_value": s.index_value, "unit": p.peril.unit_for(p.subject) if hasattr(p.peril, "unit_for") else "",
                     "paid": round(s.amount, 2), "premium_returned": 0.0, "status": "paid",
                     "note": s.summary, "carrier_id": meta.get("carrier")})
    for p in by_id.values():
        meta = p.metadata or {}
        note = meta.get("withdrawal") or {}
        if carrier_id and meta.get("carrier") != carrier_id:
            continue
        if not meta.get("carrier") or not note or month_of(float(note.get("notified_at", 0))) != month:
            continue
        rows.append({"reference": p.policy_id, "kind": "premium_returned", "date_of_loss": _iso(note.get("notified_at")),
                     "index_value": None, "unit": "", "paid": 0.0, "premium_returned": round(float(note.get("refund", 0.0)), 2),
                     "status": note.get("basis", ""), "note": "returned on cancellation", "carrier_id": meta.get("carrier")})
    rows.sort(key=lambda r: r["date_of_loss"])
    return {"kind": "claims", "month": month, "carrier_id": carrier_id, "rows": rows, "count": len(rows),
            "totals": {"paid": round(sum(r["paid"] for r in rows), 2),
                       "premium_returned": round(sum(r["premium_returned"] for r in rows), 2),
                       "claims": sum(1 for r in rows if r["kind"] == "claim")}}


def reconciliation(risk: dict[str, Any], claims: dict[str, Any], statement: dict[str, Any] | None) -> dict[str, Any]:
    """The month's three sources beside each other. The fee ledger is the
    money that moved; the risk bordereau is the cover bound; they differ by
    what instalment plans paid in other months, and the difference is
    shown rather than hidden."""
    st = statement or {}
    fees_ledger = round(float(st.get("fronting_fees", 0.0)) - float(st.get("fronting_fees_returned", 0.0)), 2)
    platform_ledger = round(float(st.get("platform_fees", 0.0)) - float(st.get("platform_fees_returned", 0.0)), 2)
    net_ledger = round(float(st.get("net_to_company", 0.0)), 2)
    fees_bound = risk["totals"]["fee_paid"]
    platform_bound = risk["totals"]["platform_fee_paid"]
    net_bound = risk["totals"]["net_fee_to_carrier"]
    difference = round(net_ledger - net_bound, 2)
    items = [
        ("policies_bound", risk["count"]),
        ("gross_premiums_bound", risk["totals"]["gross_premium"]),
        ("limits_bound", risk["totals"]["limit"]),
        ("fronting_fees_on_bound_policies", fees_bound),
        ("platform_fees_on_bound_policies", platform_bound),
        ("net_fees_on_bound_policies", net_bound),
        ("fronting_fees_in_ledger_net_of_returns", fees_ledger),
        ("platform_fees_in_ledger_net_of_returns", platform_ledger),
        ("net_to_carrier_in_ledger", net_ledger),
        ("difference_ledger_less_bound", difference),
        ("claims_paid", claims["totals"]["paid"]),
        ("claims_count", claims["totals"]["claims"]),
        ("premiums_returned", claims["totals"]["premium_returned"]),
    ]
    return {"kind": "reconciliation", "month": risk["month"], "carrier_id": risk["carrier_id"],
            "items": [{"item": k, "amount": v} for k, v in items],
            "reconciled": abs(difference) < 0.005,
            "note": ("The ledger and the bound policies agree to the cent." if abs(difference) < 0.005 else
                     "The ledger and the bound policies differ: instalment parts paid in other months, fees returned on "
                     "policies bound in other months, or a policy bound this month whose fee is still owed. Each such "
                     "policy is on the risk bordereau with its fee paid to date.")}


def to_csv(book: dict[str, Any]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    if book["kind"] == "reconciliation":
        w.writerow(RECON_COLUMNS)
        for row in book["items"]:
            w.writerow([row["item"], row["amount"]])
        w.writerow([]); w.writerow(["reconciled", book["reconciled"]]); w.writerow(["note", book["note"]])
        return out.getvalue()
    cols = RISK_COLUMNS if book["kind"] == "risk" else CLAIMS_COLUMNS
    w.writerow(cols + ("carrier_id",))
    for r in book["rows"]:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in cols] + [r.get("carrier_id", "")])
    w.writerow([])
    for k, v in book["totals"].items():
        w.writerow([k, v])
    return out.getvalue()
