"""The company's desk: its policies found, filtered, sorted, grouped and
exported, the way an underwriter works a book.

A company that writes a few hundred policies needs to find one by its
number or its street, see which ones end in the next thirty days so the
buyer can be offered a renewal, and see where its exposure sits, province
by province. None of that needs new data: every policy carries its place,
its dates and its status. This module reads them.

Province is worked out from where the cover stands: the nearest place in
the country list for a coordinate (a district's province, or the province
itself), the station's region for drought, and nothing for a flight.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import time
import unicodedata
from typing import Any, Iterable

from ..perils.geo import distance_km
from ..perils.places import PLACES
from ..perils.weather import STATIONS

SORTS = ("bought_at", "ends_at", "limit", "premium", "policy_id", "status")
DEFAULT_DUE_DAYS = 30.0


def nearest_province(latitude: float, longitude: float) -> str:
    """The province of the nearest listed place, within 150 km; a district
    is listed as "Province, District"."""
    best, best_km = None, float("inf")
    for place in PLACES:
        km = distance_km((latitude, longitude), (place.latitude, place.longitude))
        if km < best_km:
            best, best_km = place, km
    if best is None or best_km > 150.0:
        return ""
    return best.name.split(",")[0].strip()


def province_of(policy: Any) -> str:
    subject = policy.subject or {}
    if "latitude" in subject and "longitude" in subject:
        try:
            return nearest_province(float(subject["latitude"]), float(subject["longitude"]))
        except (TypeError, ValueError):
            return ""
    station = STATIONS.get(str(subject.get("station", "")))
    if station is not None:
        return nearest_province(station.latitude, station.longitude)
    return ""


def row_of(policy: Any, *, names: dict[str, str] | None = None, now: float | None = None,
           private: bool = False) -> dict[str, Any]:
    """One policy as the desk lists it. The buyer is a shortened address
    unless the desk is the company's own, which sees the address it was
    given for the ownership check."""
    from .wallet import shorten
    now = time.time() if now is None else now
    meta = policy.metadata or {}
    days_left = (policy.ends_at - now) / 86400.0
    address = meta.get("address") or ((meta.get("interest") or {}).get("address"))
    return {
        "policy_id": policy.policy_id, "peril": policy.peril_key,
        "subject": policy.peril.describe_subject(policy.subject),
        "place": policy.subject.get("place") or policy.subject.get("station") or policy.subject.get("route")
                 or (f"{policy.subject['origin']}-{policy.subject['destination']}"
                     if policy.subject.get("origin") else "") or "",
        "province": province_of(policy),
        "country": ((meta.get("compliance") or {}).get("country") or (meta.get("interest") or {}).get("country") or ""),
        "limit": round(policy.limit, 2), "premium": round(policy.premium, 2),
        "status": policy.status.value, "payout": round(policy.payout, 2),
        "bought_at": policy.bought_at, "starts_at": policy.starts_at, "ends_at": policy.ends_at,
        "days_left": round(days_left, 1) if policy.is_open else None,
        "renewal_due": bool(policy.is_open and 0 <= days_left <= DEFAULT_DUE_DAYS),
        "holder": shorten(policy.holder),
        "carrier_id": meta.get("carrier"), "carrier": (names or {}).get(meta.get("carrier", ""), None),
        "address": ", ".join(str(address.get(k, "")) for k in ("street", "number", "flat", "postcode", "city")
                             if address.get(k)) if (private and isinstance(address, dict)) else None,
    }


def fold(text: str) -> str:
    """Searchable text: no case, no diacritics, so "istanbul" finds İstanbul
    and "kadikoy" finds Kadıköy, whichever keyboard the underwriter has."""
    text = str(text or "").replace("İ", "i").replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def matches(row: dict[str, Any], q: str) -> bool:
    if not q:
        return True
    hay = " ".join(str(row.get(k) or "") for k in
                   ("policy_id", "subject", "place", "province", "holder", "peril", "status", "address", "carrier"))
    return fold(q) in fold(hay)


def select(policies: Iterable[Any], *, q: str = "", status: str = "", peril: str = "", province: str = "",
           due_within: float | None = None, sort: str = "bought_at", descending: bool = True,
           names: dict[str, str] | None = None, now: float | None = None,
           private: bool = False) -> list[dict[str, Any]]:
    now = time.time() if now is None else now
    rows = [row_of(p, names=names, now=now, private=private) for p in policies]
    if status:
        wanted = {s.strip() for s in status.split(",") if s.strip()}
        if "open" in wanted:
            wanted |= {"active"}
        rows = [r for r in rows if r["status"] in wanted]
    if peril:
        rows = [r for r in rows if r["peril"] == peril]
    if province:
        rows = [r for r in rows if fold(r["province"]) == fold(province)]
    if due_within is not None:
        rows = [r for r in rows if r["days_left"] is not None and 0 <= r["days_left"] <= due_within]
    if q:
        rows = [r for r in rows if matches(r, q)]
    key = sort if sort in SORTS else "bought_at"
    rows.sort(key=lambda r: (r.get(key) is None, r.get(key) or 0), reverse=descending)
    return rows


def by_province(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Open cover grouped by province: how many, how much, what premium."""
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["status"] != "active":
            continue
        g = groups.setdefault(r["province"] or "", {"province": r["province"] or "", "policies": 0,
                                                       "in_force": 0.0, "premiums": 0.0, "perils": {}})
        g["policies"] += 1
        g["in_force"] += r["limit"]
        g["premiums"] += r["premium"]
        g["perils"][r["peril"]] = g["perils"].get(r["peril"], 0) + 1
    out = sorted(groups.values(), key=lambda g: (-g["in_force"], g["province"]))
    for g in out:
        g["in_force"] = round(g["in_force"], 2)
        g["premiums"] = round(g["premiums"], 2)
    return out


def summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    open_ = [r for r in rows if r["status"] == "active"]
    due = [r for r in open_ if r["renewal_due"]]
    return {"policies": len(rows), "open": len(open_), "in_force": round(sum(r["limit"] for r in open_), 2),
            "renewals_due": len(due), "renewals_in_force": round(sum(r["limit"] for r in due), 2),
            "provinces": len({r["province"] for r in open_ if r["province"]})}


def to_csv(rows: Iterable[dict[str, Any]]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    cols = ("policy_id", "peril", "subject", "province", "country", "status", "limit", "premium", "payout",
            "bought_at", "starts_at", "ends_at", "days_left", "renewal_due", "holder", "carrier", "address")
    w.writerow(cols)
    for r in rows:
        line = []
        for c in cols:
            v = r.get(c)
            if c in ("bought_at", "starts_at", "ends_at") and v:
                v = dt.datetime.fromtimestamp(v, dt.timezone.utc).isoformat(timespec="seconds")
            line.append("" if v is None else v)
        w.writerow(line)
    return out.getvalue()
