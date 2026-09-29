"""Reading a built model and asking it the one question a policy asks.

Standard library only: this runs on the protocol's server, which never needs
numpy, the catalogue or the network to price a policy. It reads the files the
build wrote and nothing else.

The question: how often is there an earthquake of at least this magnitude with
its epicentre inside this circle? The answer is the sum of the grid cells whose
centres the circle contains, each cell's rate of magnitude 5 and above scaled
down the truncated Gutenberg and Richter curve to the magnitude asked about.
"""

from __future__ import annotations

import base64
import json
import math
from array import array
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable

MODELS_DIR = Path(__file__).resolve().parent / "models"
EARTH_KM = 6371.0
# A policy address on the coast can sit a little outside a simplified outline.
COAST_TOLERANCE_KM = 12.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


class HazardModel:
    """One country's gridded earthquake rates, and what they imply for a circle."""

    def __init__(self, doc: dict[str, Any], rates: Iterable[float] | None = None) -> None:
        self.doc = doc
        self.code: str = doc["code"]
        # The region's key and the country's are the same for every region but
        # Alaska and Hawaii, which are their own fits inside the United States.
        # Everything that means "whose law and licence" reads country;
        # everything that means "which grid and which file" reads code.
        self.country: str = str(doc.get("country") or doc["code"])
        self.name: str = doc["name"]
        self.version: str = doc.get("version", "")
        grid = doc["grid"]
        self.south, self.west = float(grid["south"]), float(grid["west"])
        self.step = float(grid["step"])
        self.rows, self.cols = int(grid["rows"]), int(grid["cols"])
        if rates is None:
            self.rates = array("f")
            self.rates.frombytes(base64.b64decode(grid["rates_f32_b64"]))
        else:
            self.rates = array("f", rates)
        if len(self.rates) != self.rows * self.cols:
            raise ValueError(f"{self.code}: grid holds {len(self.rates)} cells, expected {self.rows * self.cols}")
        self.b_value = float(doc["b_value"])
        self.max_magnitude = float(doc["max_magnitude"])
        self.reference = float(doc.get("method", {}).get("reference_magnitude", 5.0))
        self.outline: list[list[list[float]]] = doc.get("outline", [])
        box = doc.get("box") or {}
        self.box = (box.get("south", self.south), box.get("north", self.south + self.step * (self.rows - 1)),
                    box.get("west", self.west), box.get("east", self.west + self.step * (self.cols - 1)))
        self.validation: dict[str, Any] = doc.get("validation", {})
        self.sources: list[dict[str, str]] = doc.get("sources", [])
        self._cache: dict[tuple[float, float, float], float] = {}
        self._where: dict[tuple[float, float], bool] = {}

    # -- where ------------------------------------------------------------

    @property
    def passed(self) -> bool:
        return bool(self.validation.get("passed"))

    def in_box(self, latitude: float, longitude: float) -> bool:
        s, n, w, e = self.box
        return s <= latitude <= n and w <= longitude <= e

    def contains(self, latitude: float, longitude: float) -> bool:
        """Whether a point is on this country's land, or just off its coast."""
        if not self.in_box(latitude, longitude):
            return False
        # The same policy asks this on every block the chain produces, so the
        # answer is kept, at a resolution of about a metre.
        key = (round(latitude, 5), round(longitude, 5))
        known = self._where.get(key)
        if known is not None:
            return known
        answer = self._contains(latitude, longitude)
        if len(self._where) > 8192:
            self._where.clear()
        self._where[key] = answer
        return answer

    def _contains(self, latitude: float, longitude: float) -> bool:
        for ring in self.outline:
            if _inside(ring, longitude, latitude):
                return True
        # Just off the coast is measured to the coast, not to the corners of it.
        # These outlines are simplified, so two vertices can be a hundred
        # kilometres apart along a straight stretch of shore, and a point a
        # kilometre outside the middle of that stretch is far from both. Niigata
        # fell out of Japan that way: a city of eight hundred thousand that this
        # product offered and could not price, because the nearest corner of the
        # polygon was too far even though the edge was right there.
        for ring in self.outline:
            for i in range(len(ring)):
                x1, y1 = ring[i - 1]
                x2, y2 = ring[i]
                if min(y1, y2) - 0.3 > latitude or max(y1, y2) + 0.3 < latitude:
                    continue
                if _to_segment_km(latitude, longitude, y1, x1, y2, x2) <= COAST_TOLERANCE_KM:
                    return True
        return False

    # -- how often --------------------------------------------------------

    def rate_reference_within(self, latitude: float, longitude: float, radius_km: float) -> float:
        """Annual rate of mainshocks of the reference magnitude or more in the circle."""
        key = (round(latitude, 4), round(longitude, 4), float(radius_km))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        dlat = radius_km / 111.195
        dlon = radius_km / max(1e-6, 111.195 * math.cos(math.radians(latitude)))
        r0 = max(0, int(math.floor((latitude - dlat - self.south) / self.step)))
        r1 = min(self.rows - 1, int(math.ceil((latitude + dlat - self.south) / self.step)))
        c0 = max(0, int(math.floor((longitude - dlon - self.west) / self.step)))
        c1 = min(self.cols - 1, int(math.ceil((longitude + dlon - self.west) / self.step)))
        total = 0.0
        for r in range(r0, r1 + 1):
            cell_lat = self.south + r * self.step
            base = r * self.cols
            for c in range(c0, c1 + 1):
                cell_lon = self.west + c * self.step
                if haversine_km(latitude, longitude, cell_lat, cell_lon) <= radius_km:
                    total += self.rates[base + c]
        if len(self._cache) > 4096:
            self._cache.clear()
        self._cache[key] = total
        return total

    def share_at_or_above(self, magnitude: float) -> float:
        """Fraction of reference events that reach a magnitude: truncated G and R."""
        if magnitude >= self.max_magnitude:
            return 0.0
        if magnitude <= self.reference:
            return 1.0
        b = self.b_value
        top = 10 ** (-b * (self.max_magnitude - self.reference))
        here = 10 ** (-b * (magnitude - self.reference))
        return max(0.0, (here - top) / (1.0 - top))

    def rate_within(self, latitude: float, longitude: float, radius_km: float, magnitude: float) -> float:
        return self.rate_reference_within(latitude, longitude, radius_km) * self.share_at_or_above(magnitude)

    def exceedance(self, latitude: float, longitude: float, radius_km: float,
                   years: float) -> Callable[[float], float]:
        base = self.rate_reference_within(latitude, longitude, radius_km)

        def probability(magnitude: float) -> float:
            return 1.0 - math.exp(-base * self.share_at_or_above(magnitude) * years)

        return probability

    # -- the published record ----------------------------------------------

    def card(self) -> dict[str, Any]:
        """What a buyer, an insurer or a regulator can read about this model."""
        doc = self.doc
        return {
            "country": self.country, "region": self.code,
            "name": self.name, "version": self.version,
            "built": doc.get("built"), "method": doc.get("method"),
            "b_value": self.b_value, "completeness": doc.get("completeness"),
            "max_magnitude": self.max_magnitude, "rate_m5_per_year": doc.get("total_rate_m5"),
            "record": doc.get("stats"), "validation": self.validation,
            "sources": self.sources, "crosscheck": doc.get("crosscheck"),
            "passed": self.passed,
        }


def _to_segment_km(latitude: float, longitude: float,
                   lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """How far a point is from a piece of coastline, in kilometres.

    Flat earth over the length of one simplified edge, with longitude squeezed
    by the latitude, which is accurate to well under the tolerance it is
    compared against.
    """
    scale = math.cos(math.radians(latitude))
    px, py = (longitude - lon1) * scale, latitude - lat1
    qx, qy = (lon2 - lon1) * scale, lat2 - lat1
    length = qx * qx + qy * qy
    along = 0.0 if length <= 0 else max(0.0, min(1.0, (px * qx + py * qy) / length))
    dx, dy = px - along * qx, py - along * qy
    return 111.195 * math.sqrt(dx * dx + dy * dy)


def _inside(ring: list[list[float]], x: float, y: float) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def models() -> dict[str, HazardModel]:
    """Every model the build has written, passed or not, by country code."""
    out: dict[str, HazardModel] = {}
    if not MODELS_DIR.exists():
        return out
    for path in sorted(MODELS_DIR.glob("*.json")):
        if path.stem == "places" or len(path.stem) != 2:
            continue
        out[path.stem] = HazardModel(json.loads(path.read_text(encoding="utf-8")))
    return out


def load_models() -> dict[str, HazardModel]:
    models.cache_clear()
    return models()


def priced_countries() -> frozenset[str]:
    """Countries whose model passed its backtest. Only these are sold."""
    return frozenset(m.country for m in models().values() if m.passed)


def model_for(latitude: float, longitude: float, *, include_turkey: bool = False) -> HazardModel | None:
    """The passed model whose country this point is in, if there is one.

    Türkiye is excluded unless asked for: it is priced by the fault model in
    ``clause.perils.geo``, and its grid model exists as the cross check.
    """
    for code, model in models().items():
        if code == "TR" and not include_turkey:
            continue
        if model.passed and model.contains(latitude, longitude):
            return model
    return None


def model_at(latitude: float, longitude: float, *, include_turkey: bool = False
             ) -> HazardModel | None:
    """The model whose country this point is in, whether or not it passed.

    A model that failed its own backtest cannot set the level of the hazard,
    and it is still the only thing that knows which earthquakes happen where:
    the magnitudes, the distances, and which neighbours one event shakes at the
    same moment. Where a national authority publishes the level, that is worth
    having on its own, so it is reachable separately from ``model_for``, which
    remains the question "may this country's own figure price a policy".
    """
    for code, model in models().items():
        if code == "TR" and not include_turkey:
            continue
        if model.contains(latitude, longitude):
            return model
    return None


def published_countries() -> frozenset[str]:
    """Countries a national authority's own hazard curves are held for."""
    from .published import curves

    return frozenset(row["country"] for row in curves())


@lru_cache(maxsize=1)
def places() -> dict[str, Any]:
    path = MODELS_DIR / "places.json"
    if not path.exists():
        return {"attribution": "", "places": []}
    return json.loads(path.read_text(encoding="utf-8"))
