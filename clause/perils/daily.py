"""One country's daily extremes, read at runtime. Shared by two covers.

The car cover pays on the largest day of rain and the storm cover on the
largest day of wind. Both are the same shape of model, built by
``clause.hazard.daily_extremes`` into one file per country, and both ask the
same two questions of it: which country's models may be sold, and which of
their places is nearest to an address.

Which may be sold is the country's own backtest, exactly as the earthquake
models are gated. A country whose model failed is not offered, and the file
says which test it failed and by how much, so the refusal is answerable rather
than a shrug.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .geo import distance_km

MODELS_DIR = Path(__file__).resolve().parents[1] / "hazard" / "models"
#: How far an address may be from a fitted place and still be priced by it. A
#: daily total from a reanalysis is an area average over tens of kilometres
#: already, so this is the scale the figures are honest at.
MAX_DISTANCE_KM = 60.0


@lru_cache(maxsize=4)
def models(stem: str) -> dict[str, dict[str, Any]]:
    """Every country's model for one kind of daily extreme, by country code."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(MODELS_DIR.glob(f"{stem}_*.json")):
        code = path.stem.split("_", 1)[1]
        if len(code) != 2:
            continue
        out[code] = json.loads(path.read_text(encoding="utf-8"))
    return out


def passed(stem: str) -> frozenset[str]:
    """The countries whose model for this kind passed its own backtest."""
    return frozenset(code for code, doc in models(stem).items()
                     if doc.get("validation", {}).get("passed"))


@lru_cache(maxsize=8192)
def nearest(stem: str, latitude: float, longitude: float
            ) -> tuple[dict[str, Any] | None, float]:
    """The nearest fitted place in any country that may be sold, and how far.

    Only the countries whose models passed are searched: a place from a country
    that failed its backtest is not a fallback, it is the wrong answer written
    confidently, which is the thing this whole layer exists to avoid.
    """
    best: dict[str, Any] | None = None
    best_km = float("inf")
    for code in sorted(passed(stem)):
        for place in models(stem)[code].get("places", []):
            km = distance_km((latitude, longitude), (place["latitude"], place["longitude"]))
            if km < best_km:
                best, best_km = dict(place, country=code), km
    return best, best_km


def reload() -> None:
    """Forget what was read, for a build that has just rewritten it."""
    models.cache_clear()
    nearest.cache_clear()
