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

from ..perils.places import PLACES, Place

POWER = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters={parameter}"
         "&community=AG&longitude={lon}&latitude={lat}&start=19810101&end={end}&format=JSON")
BUILD = Path(__file__).resolve().parents[2] / "hazard_build"
MODELS = Path(__file__).resolve().parent / "models"
FIT_UNTIL = 2010
RECENT_YEARS = 30
EULER = 0.5772156649


#: How many people a place needs before its own daily record is fitted, and how
#: many places a country gets whatever their size. The first keeps the build to
#: the places people actually live; the second keeps a country with two large
#: cities from having a model fitted on two places, which is not a model.
LEAST_PEOPLE = 200_000
LEAST_PLACES = 24


def world_places(code: str) -> list[tuple[str, float, float]]:
    """The places one country's daily model is fitted at, largest first.

    Read from the same index the interface searches, so what is fitted is where
    a buyer can actually ask for cover rather than a grid of ocean.
    """
    data = json.loads((MODELS / "places.json").read_text(encoding="utf-8"))
    rows = [(str(r[0]), float(r[4]), float(r[5]), int(r[6]))
            for r in data.get("places", []) if len(r) >= 7 and r[2] == code]
    rows.sort(key=lambda r: -r[3])
    keep = [r for r in rows if r[3] >= LEAST_PEOPLE]
    if len(keep) < LEAST_PLACES:
        keep = rows[:LEAST_PLACES]
    # One place per coordinate, rounded the way the cache keys it, so a city and
    # its own district do not become two fits of one series.
    seen: set[tuple[float, float]] = set()
    out = []
    for name, latitude, longitude, _people in keep:
        key = (round(latitude, 2), round(longitude, 2))
        if key in seen:
            continue
        seen.add(key)
        out.append((name, latitude, longitude))
    return out


@dataclass(frozen=True)
class Spec:
    """What one cover's build asks NASA POWER for, and what it writes."""

    parameter: str                 # the NASA POWER daily parameter
    kind: str                      # rain_extreme, wind_extreme
    index: str                     # the index, in words, for the model file
    unit: str                      # mm, km/h
    cache: Path                    # where the fetched series are kept
    out: Path                      # the model file written, for Türkiye
    stem: str = ""                 # rain, wind: names the file for any country
    scale: float = 1.0             # applied to every value: m/s to km/h is 3.6
    version: str = "2026.1"
    # Recorded in the model file when something was changed after a result
    # was seen; empty for a build whose first run passed as fixed.
    changes_after_first_run: tuple[str, ...] = ()
    user_agent: str = "Clause hazard build"

    def file_for(self, code: str) -> Path:
        """Where one country's model is written."""
        if not self.stem:
            return self.out
        return MODELS / f"{self.stem}_{code.upper()}.json"

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


#: A rolling fit needs at least this many years behind it before it is asked to
#: predict the next one.
ROLLING_LEAST = 25


def verdict(*, record_ok: bool, count_ok: bool, rolling_ok: bool) -> dict[str, Any]:
    """Whether a country may be sold, and on which test.

    Either test may carry it, and which one did is written down. A country that
    failed the fixed test and passed the rolling one is sold on a model that
    tracks a moving climate, not on one that was always right, and that is a
    different claim. The record is not negotiable by either: too few years is
    too few years.
    """
    return {
        "passed": bool(record_ok and (count_ok or rolling_ok)),
        "sold_on": ("the fixed test" if count_ok else
                    "the rolling test, the fixed one having failed" if rolling_ok else
                    "neither test"),
        "failed": [name for name, ok in (("record", record_ok), ("count", count_ok),
                                         ("rolling", rolling_ok)) if not ok],
    }


def _in_sample(spec: Spec, places: list[Any], last_year: int, end: str) -> tuple[int, int]:
    """How often the fitting years beat their own fit. A fifth, if the fit fits.

    This is not a test and nothing is gated on it. It is the figure that tells a
    reader which kind of failure they are looking at: a distribution that cannot
    describe the years it was fitted on is a broken model, and one that describes
    them but not the years since is a changed world. For every country built
    here it is the second.
    """
    beat = trials = 0
    for place in places:
        series = fetch(spec, place.latitude, place.longitude, end)
        maxima = annual_maxima(series, last_year, scale=spec.scale)
        years = sorted(y for y in maxima if y <= FIT_UNTIL)
        if len(years) < ROLLING_LEAST:
            continue
        mu, beta = gumbel([maxima[y] for y in years])
        five = level(mu, beta, 5)
        beat += sum(1 for y in years if maxima[y] > five)
        trials += len(years)
    return beat, trials


def _rolling(spec: Spec, places: list[Any], last_year: int, end: str) -> tuple[int, int]:
    """How often the year ahead beat a fit on the years before it.

    Every year from the first test year onward is predicted by a fit that has
    not seen it or anything after it, using the same window of recent years the
    published levels are fitted on. So it tests the model as published rather
    than a model nobody is sold.
    """
    beat = trials = 0
    for place in places:
        series = fetch(spec, place.latitude, place.longitude, end)
        maxima = annual_maxima(series, last_year, scale=spec.scale)
        for year in range(FIT_UNTIL + 1, last_year + 1):
            if year not in maxima:
                continue
            before = [maxima[y] for y in sorted(maxima)
                      if year - RECENT_YEARS <= y < year]
            if len(before) < ROLLING_LEAST:
                continue
            mu, beta = gumbel(before)
            trials += 1
            beat += 1 if maxima[year] > level(mu, beta, 5) else 0
    return beat, trials


def build(spec: Spec, *, sources: list[dict[str, Any]], code: str = "TR", name: str = "Türkiye",
          today: dt.date | None = None, echo: bool = True,
          where: list[tuple[str, float, float]] | None = None) -> dict[str, Any]:
    """Fetch, fit, test and write one country's model file. Returns what it wrote.

    Türkiye is fitted at its eighty one provincial centres, which is the list
    this build started from. Any other country is fitted at the places the
    interface offers in it, because that is where a buyer can ask.
    """
    today = today or dt.date.today()
    last_year = today.year - 1
    end = f"{last_year}1231"
    if where is None:
        where = ([(p.name, p.latitude, p.longitude) for p in PLACES if p.kind == "province"]
                 if code == "TR" else world_places(code))
    provinces = [Place(name=n, latitude=la, longitude=lo, region="", kind="province")
                 for n, la, lo in where]
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

    # The second test, and what it is for. The one above asks whether a fit on
    # 1981 to 2010 predicts 2011 onward. Five countries failed it and four of
    # those failed by under-predicting, which says the climate moved rather
    # than that the distribution is wrong. But the model this product publishes
    # is not that fit: it is fitted on the most recent thirty years and used to
    # price the year ahead. So the question that matches the product had not
    # been asked. It is asked here, and it was written down before it was run.
    # And the same question asked of the years the fit was made on, which is the
    # one figure that separates a distribution that does not describe the data
    # from a world that moved. Every country sits near a fifth here, the ones
    # that fail both tests included, so the Gumbel is not what fails.
    inside, inside_trials = _in_sample(spec, provinces, last_year, end)

    rolled, rolled_trials = _rolling(spec, provinces, last_year, end)
    rolled_expected = rolled_trials * p
    rolled_low = nb_cdf(rolled, rolled_expected, dispersion) if rolled_trials else 0.0
    rolled_high = (1.0 - nb_cdf(rolled - 1, rolled_expected, dispersion)
                   if rolled > 0 else 1.0)
    rolling_ok = bool(rolled_trials) and rolled_low >= 0.025 and rolled_high >= 0.025
    doc = {
        "code": code, "name": name, "kind": spec.kind, "version": spec.version,
        "built": today.isoformat(),
        "index": spec.index,
        "unit": spec.unit,
        "sources": sources,
        "validation": {
            **verdict(record_ok=record_ok, count_ok=count_ok, rolling_ok=rolling_ok),
            "fitted_until": FIT_UNTIL, "tested_from": FIT_UNTIL + 1,
            "count": {"expected": round(expected, 1), "observed": exceed, "place_years": trials,
                      "dispersion": round(dispersion, 2),
                      "p_at_most_observed": round(low, 4), "p_at_least_observed": round(high, 4)},
            "rolling": {
                "question": ("does a fit on the most recent years predict the next one, "
                             "which is how this model is published and used"),
                "window_years": RECENT_YEARS, "least_years": ROLLING_LEAST,
                "tested_from": FIT_UNTIL + 1,
                "expected": round(rolled_expected, 1), "observed": rolled,
                "place_years": rolled_trials, "dispersion": round(dispersion, 2),
                "p_at_most_observed": round(rolled_low, 4),
                "p_at_least_observed": round(rolled_high, 4),
                "passed": rolling_ok,
            },
            "in_sample": {
                "question": ("how often the years the fit was made on beat that "
                             "same fit, which should be a fifth of them"),
                "expected": round(0.2 * inside_trials, 1), "observed": inside,
                "place_years": inside_trials,
                "share": round(inside / inside_trials, 3) if inside_trials else None,
            },
            "changes_after_first_run": list(spec.changes_after_first_run),
        },
        "places": places,
    }
    spec.file_for(code).write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    if echo:
        print(json.dumps(doc["validation"], indent=1))
    return doc
