"""Daily extremes at Türkiye's 81 provincial centres, one build for two covers.

The car cover pays on the largest day of rain; the storm cover on the largest
day of wind. Both are the same shape of model: one NASA POWER daily series per
place, the largest value in each calendar year, a Gumbel distribution fitted
to those maxima by probability weighted moments, and the same test set before
any result is seen. So the shape is written once, here, and each cover names
its parameter, its unit and its file. ``rain_build`` and ``wind_build`` are
the two callers and carry what is specific to each.

Offline, like the earthquake build: the server reads the file the build wrote
and never fetches. The data is NASA POWER (MERRA-2), public domain, from 1981.
The policy settles on the same series for the same point, so the model and
the index are the same thing measured the same way.

The test, fixed before the first run and identical for both:

    fitted on 1981 to 2010, tested on 2011 onward

    count     the number of test years whose maximum exceeded the fitted
              1 in 5 year level falls inside the central 95 per cent of the
              distribution the fit implies, for the country as a whole,
              with the year to year dispersion measured on the fitting years
              (the 81 places are not independent: one storm raises several
              neighbouring provinces in the same year)
    places    at least 30 years of record in the fitting window

The published levels are fitted on the most recent 30 years, so the price
reflects the climate now rather than an average that includes an earlier one.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..perils.places import PLACES

POWER = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters={parameter}"
         "&community=AG&longitude={lon}&latitude={lat}&start=19810101&end={end}&format=JSON")
BUILD = Path(__file__).resolve().parents[2] / "hazard_build"
MODELS = Path(__file__).resolve().parent / "models"
FIT_UNTIL = 2010
RECENT_YEARS = 30
EULER = 0.5772156649


@dataclass(frozen=True)
class Spec:
    """What one cover's build asks NASA POWER for, and what it writes."""

    parameter: str                 # the NASA POWER daily parameter
    kind: str                      # rain_extreme, wind_extreme
    index: str                     # the index, in words, for the model file
    unit: str                      # mm, km/h
    cache: Path                    # where the fetched series are kept
    out: Path                      # the model file written
    scale: float = 1.0             # applied to every value: m/s to km/h is 3.6
    version: str = "2026.1"
    # Recorded in the model file when something was changed after a result
    # was seen; empty for a build whose first run passed as fixed.
    changes_after_first_run: tuple[str, ...] = ()
    user_agent: str = "Clause hazard build"

    @property
    def levels_key(self) -> str:
        return "levels_" + self.unit.replace("/", "")

    @property
    def largest_key(self) -> str:
        return "largest_" + self.unit.replace("/", "")


def fetch(spec: Spec, lat: float, lon: float, end: str) -> dict[str, float]:
    spec.cache.mkdir(parents=True, exist_ok=True)
    path = spec.cache / f"{lat:.2f}_{lon:.2f}.json"
    if path.exists():
        return json.loads(path.read_text())
    url = POWER.format(parameter=spec.parameter, lat=lat, lon=lon, end=end)
    request = urllib.request.Request(url, headers={"User-Agent": spec.user_agent})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=90) as reply:   # noqa: S310
                data = json.loads(reply.read())
            series = data["properties"]["parameter"][spec.parameter]
            path.write_text(json.dumps(series))
            return series
        except Exception:  # retried, then raised
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def annual_maxima(series: dict[str, float], last_year: int, *, scale: float = 1.0) -> dict[int, float]:
    out: dict[int, float] = {}
    for day, value in series.items():
        if value is None or value < 0:
            continue
        year = int(day[:4])
        if year > last_year:
            continue
        out[year] = max(out.get(year, 0.0), float(value) * scale)
    return out


def gumbel(maxima: list[float]) -> tuple[float, float]:
    """Location and scale by probability weighted moments (L moments)."""
    xs = sorted(maxima)
    n = len(xs)
    b0 = sum(xs) / n
    b1 = sum(i * x for i, x in enumerate(xs)) / (n * (n - 1))
    l2 = 2 * b1 - b0
    beta = l2 / math.log(2)
    mu = b0 - EULER * beta
    return mu, beta


def level(mu: float, beta: float, years: float) -> float:
    """The daily value exceeded on average once in this many years."""
    return mu - beta * math.log(-math.log(1.0 - 1.0 / years))


def nb_cdf(k: int, mean: float, dispersion: float) -> float:
    if dispersion <= 1.0001:
        term, total = math.exp(-mean), 0.0
        for i in range(k + 1):
            total += term
            term *= mean / (i + 1)
        return min(1.0, total)
    r = mean / (dispersion - 1.0)
    p = r / (r + mean)
    return min(1.0, sum(math.exp(math.lgamma(i + r) - math.lgamma(r) - math.lgamma(i + 1)
                                 + r * math.log(p) + i * math.log(1 - p)) for i in range(k + 1)))


def build(spec: Spec, *, sources: list[dict[str, Any]], code: str = "TR", name: str = "Türkiye",
          today: dt.date | None = None, echo: bool = True) -> dict[str, Any]:
    """Fetch, fit, test and write the model file. Returns what was written."""
    today = today or dt.date.today()
    last_year = today.year - 1
    end = f"{last_year}1231"
    provinces = [p for p in PLACES if p.kind == "province"]
    places, exceed, trials = [], 0, 0
    fit_counts: dict[int, int] = {}
    for i, place in enumerate(provinces):
        series = fetch(spec, place.latitude, place.longitude, end)
        maxima = annual_maxima(series, last_year, scale=spec.scale)
        fit_years = [y for y in maxima if y <= FIT_UNTIL]
        test_years = [y for y in maxima if y > FIT_UNTIL]
        mu, beta = gumbel([maxima[y] for y in fit_years])
        five = level(mu, beta, 5)
        exceed += sum(1 for y in test_years if maxima[y] > five)
        trials += len(test_years)
        for y in fit_years:
            fit_counts[y] = fit_counts.get(y, 0) + (1 if maxima[y] > five else 0)
        recent = [maxima[y] for y in maxima if y > last_year - RECENT_YEARS]
        mu_all, beta_all = gumbel(recent)
        places.append({
            "name": place.name, "latitude": place.latitude, "longitude": place.longitude,
            "gumbel": {"mu": round(mu_all, 3), "beta": round(beta_all, 3)},
            spec.levels_key: {str(y): round(level(mu_all, beta_all, y), 1) for y in (2, 5, 10, 25, 50)},
            "record_years": len(maxima), "fit_years": len(fit_years),
            spec.largest_key: round(max(maxima.values()), 1),
        })
        if echo:
            print(f"{i + 1:2d}/{len(provinces)} {place.name:18s} "
                  f"10y {places[-1][spec.levels_key]['10']:6.1f} {spec.unit}  "
                  f"50y {places[-1][spec.levels_key]['50']:6.1f} {spec.unit}", flush=True)
    p = 0.2
    counts = list(fit_counts.values())
    mean = sum(counts) / len(counts)
    dispersion = max(1.0, sum((c - mean) ** 2 for c in counts) / (len(counts) - 1) / mean)
    expected = trials * p
    low = nb_cdf(exceed, expected, dispersion)
    high = 1.0 - nb_cdf(exceed - 1, expected, dispersion) if exceed > 0 else 1.0
    record_ok = all(pl["fit_years"] >= 30 for pl in places)
    count_ok = low >= 0.025 and high >= 0.025
    doc = {
        "code": code, "name": name, "kind": spec.kind, "version": spec.version,
        "built": today.isoformat(),
        "index": spec.index,
        "unit": spec.unit,
        "sources": sources,
        "validation": {
            "passed": bool(record_ok and count_ok),
            "failed": [n for n, ok in (("record", record_ok), ("count", count_ok)) if not ok],
            "fitted_until": FIT_UNTIL, "tested_from": FIT_UNTIL + 1,
            "count": {"expected": round(expected, 1), "observed": exceed, "place_years": trials,
                      "dispersion": round(dispersion, 2),
                      "p_at_most_observed": round(low, 4), "p_at_least_observed": round(high, 4)},
            "changes_after_first_run": list(spec.changes_after_first_run),
        },
        "places": places,
    }
    spec.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    if echo:
        print(json.dumps(doc["validation"], indent=1))
    return doc
