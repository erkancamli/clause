"""The things a person owns, written down once so cover is asked for in a click.

A home has a floor area, a building type, a year built and an address; a car
has a model year and a place it is kept; a field has an area and a crop. All
of it is asked for on every purchase, and all of it is the same the second
time. This book keeps each thing under a name the person gives it ("the
flat in Kadıköy", "the white Corolla"), so the purchase flow can be filled
from it, and someone with two cars picks which one.

Nothing here changes what is insured or what it costs. The protocol still
values the thing from its size on the day, the company still checks the
address, and a purchase carries its own declaration: an asset is a memory,
not a proof. Addresses are personal data; they are kept because the person
asked for them to be, shown only to their owner, and gone the moment they
remove the entry.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from .valuation import BUILDINGS, CROPS

KINDS = ("home", "vehicle", "field")
MAX_PER_ACCOUNT = 20


class AssetError(ValueError):
    """An entry this book refuses. Safe to show."""


@dataclass(slots=True)
class Asset:
    asset_id: str
    account: str
    kind: str
    label: str
    size: dict[str, Any]
    address: dict[str, str] | None
    latitude: float | None
    longitude: float | None
    place: str
    country: str
    created_at: float
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"asset_id": self.asset_id, "kind": self.kind, "label": self.label, "size": dict(self.size),
                "address": dict(self.address) if self.address else None,
                "latitude": self.latitude, "longitude": self.longitude, "place": self.place,
                "country": self.country, "created_at": self.created_at, "updated_at": self.updated_at or None}


def _year(value: Any, name: str, low: int = 1800) -> int:
    try:
        year = int(value)
    except (TypeError, ValueError) as error:
        raise AssetError(f"give the {name} as a year") from error
    if not low <= year <= 2100:
        raise AssetError(f"the {name} must be between {low} and 2100")
    return year


def _number(value: Any, name: str, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise AssetError(f"give the {name} as a number") from error
    if not low <= number <= high:
        raise AssetError(f"the {name} must be between {low:g} and {high:g}")
    return number


def clean_size(kind: str, size: dict[str, Any] | None) -> dict[str, Any]:
    size = size or {}
    if kind == "home":
        building = str(size.get("building") or "flat")
        if building not in BUILDINGS:
            raise AssetError("a flat, a house, or a shop or office")
        return {"kind": "home", "building": building,
                "area_m2": _number(size.get("area_m2"), "floor area", 10, 5000),
                "built": _year(size.get("built"), "year built")}
    if kind == "vehicle":
        out: dict[str, Any] = {"kind": "vehicle", "model_year": _year(size.get("model_year"), "model year", 1950)}
        for key in ("make", "model", "plate"):
            text = " ".join(str(size.get(key) or "").split())[:40]
            if text:
                out[key] = text
        return out
    if kind == "field":
        crop = str(size.get("crop") or "wheat")
        if crop not in CROPS:
            raise AssetError("a crop this protocol prices")
        return {"kind": "field", "crop": crop, "area_ha": _number(size.get("area_ha"), "area", 0.1, 10_000)}
    raise AssetError("a home, a car or a field")


class Assets:
    def __init__(self) -> None:
        self.assets: dict[str, Asset] = {}
        self.lock = threading.RLock()

    def save(self, account: str, body: dict[str, Any], *, clean_address: Any = None,
             now: float | None = None) -> Asset:
        """Create, or update when ``asset_id`` names one of the person's own."""
        now = time.time() if now is None else now
        kind = str(body.get("kind") or "")
        if kind not in KINDS:
            raise AssetError("a home, a car or a field")
        label = " ".join(str(body.get("label") or "").split())[:60]
        if len(label) < 2:
            raise AssetError("give it a name you will recognise")
        size = clean_size(kind, body.get("size"))
        address = clean_address(body.get("address")) if clean_address else body.get("address")
        if kind in ("home", "vehicle"):
            if not address or not address.get("street") or not address.get("city"):
                raise AssetError("the street and the city are needed: the insurer checks the address")
        else:
            address = None
        latitude = longitude = None
        if body.get("latitude") is not None and body.get("longitude") is not None:
            latitude = _number(body.get("latitude"), "latitude", -90, 90)
            longitude = _number(body.get("longitude"), "longitude", -180, 180)
        place = " ".join(str(body.get("place") or "").split())[:120]
        country = str(body.get("country") or "").upper()[:2]
        with self.lock:
            asset_id = str(body.get("asset_id") or "")
            if asset_id:
                item = self.assets.get(asset_id)
                if item is None or item.account != account:
                    raise AssetError("no such entry")
                item.kind, item.label, item.size, item.address = kind, label, size, address
                item.latitude, item.longitude, item.place, item.country = latitude, longitude, place, country
                item.updated_at = now
                return item
            mine = [a for a in self.assets.values() if a.account == account]
            if len(mine) >= MAX_PER_ACCOUNT:
                raise AssetError(f"at most {MAX_PER_ACCOUNT} entries; remove one first")
            item = Asset(asset_id="AST-" + secrets.token_hex(4).upper(), account=account, kind=kind, label=label,
                         size=size, address=address, latitude=latitude, longitude=longitude, place=place,
                         country=country, created_at=now)
            self.assets[item.asset_id] = item
        return item

    def mine(self, account: str) -> list[Asset]:
        return sorted((a for a in self.assets.values() if a.account == account),
                      key=lambda a: (KINDS.index(a.kind), a.created_at))

    def remove(self, account: str, asset_id: str) -> Asset:
        with self.lock:
            item = self.assets.get(asset_id)
            if item is None or item.account != account:
                raise AssetError("no such entry")
            del self.assets[asset_id]
        return item
