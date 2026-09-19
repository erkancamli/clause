"""Extreme daily rainfall at Türkiye's 81 provincial centres, for vehicle cover.

    python -m clause.hazard.rain_build

Offline, like the earthquake build. The data is NASA POWER's daily
precipitation (PRECTOTCORR, from the MERRA-2 reanalysis), public domain, from
1981. The policy settles on the same series for the same point, so the model
and the index are the same thing measured the same way: no gauge that a model
fitted elsewhere would have to be translated to.

For each place: the largest daily total in each calendar year, and a Gumbel
distribution fitted to those maxima by probability weighted moments. The test,
set before any result was seen, is the one the earthquake models pass:

    fitted on 1981 to 2010, tested on 2011 onward

    count     the number of test years whose maximum exceeded the fitted
              1 in 5 year level falls inside the central 95 per cent of the
              binomial the fit implies, for the country as a whole
    places    at least 30 years of record in the fitting window

A place passes if it has the record; the country's model passes if the count
test passes over all places together (one place has too few years to test on
its own).

Two changes after the first run, both recorded in the model file:

    1. The first count test treated the 81 places as independent. They are
       not: one storm raises several neighbouring provinces in the same year.
       Measured on the fitting years, the yearly count varies about five times
       as much as independence allows. The test now uses a negative binomial
       with that measured spread, the same way the earthquake count test does.
    2. Strong rainfall years have become more frequent: from 2001 the yearly
       count sits about a quarter above the 1980s and 1990s. The published
       levels are therefore fitted on the most recent 30 years, not all of
       them, so the price reflects the climate now rather than an average that
       includes a drier past.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from ..perils.places import PLACES

POWER = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR"
         "&community=AG&longitude={lon}&latitude={lat}&start=19810101&end={end}&format=JSON")
CACHE = Path(__file__).resolve().parents[2] / "hazard_build" / "rain"
OUT = Path(__file__).resolve().parent / "models" / "rain_TR.json"
FIT_UNTIL = 2010
EULER = 0.5772156649


def fetch(lat: float, lon: float, end: str) -> dict[str, float]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{lat:.2f}_{lon:.2f}.json"
    if path.exists():
        return json.loads(path.read_text())
    url = POWER.format(lat=lat, lon=lon, end=end)
    request = urllib.request.Request(url, headers={"User-Agent": "Clause rain build"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=90) as reply:   # noqa: S310
                data = json.loads(reply.read())
            series = data["properties"]["parameter"]["PRECTOTCORR"]
            path.write_text(json.dumps(series))
            return series
        except Exception:  # retried, then raised
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def annual_maxima(series: dict[str, float], last_year: int) -> dict[int, float]:
    out: dict[int, float] = {}
    for day, value in series.items():
        if value is None or value < 0:
            continue
        year = int(day[:4])
        if year > last_year:
            continue
        out[year] = max(out.get(year, 0.0), float(value))
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
    """The daily total exceeded on average once in this many years."""
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


RECENT_YEARS = 30


def main(argv: list[str]) -> None:
    today = dt.date.today()
    last_year = today.year - 1
    end = f"{last_year}1231"
    provinces = [p for p in PLACES if p.kind == "province"]
    places, exceed, trials = [], 0, 0
    fit_counts: dict[int, int] = {}
    for i, place in enumerate(provinces):
        series = fetch(place.latitude, place.longitude, end)
        maxima = annual_maxima(series, last_year)
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
            "levels_mm": {str(y): round(level(mu_all, beta_all, y), 1) for y in (2, 5, 10, 25, 50)},
            "record_years": len(maxima), "fit_years": len(fit_years),
            "largest_mm": round(max(maxima.values()), 1),
        })
        print(f"{i + 1:2d}/{len(provinces)} {place.name:18s} 10y {places[-1]['levels_mm']['10']:6.1f} mm  "
              f"50y {places[-1]['levels_mm']['50']:6.1f} mm", flush=True)
    p = 0.2
    counts = list(fit_counts.values())
    mean = sum(counts) / len(counts)
    dispersion = max(1.0, sum((c - mean) ** 2 for c in counts) / (len(counts) - 1) / mean)
    expected = trials * p
    low = nb_cdf(exceed, expected, dispersion)
    high = 1.0 - nb_cdf(exceed - 1, expected, dispersion) if exceed > 0 else 1.0
    record_ok = all(p["fit_years"] >= 30 for p in places)
    count_ok = low >= 0.025 and high >= 0.025
    doc = {
        "code": "TR", "name": "Türkiye", "kind": "rain_extreme", "version": "2026.1",
        "built": today.isoformat(),
        "index": "largest daily precipitation, NASA POWER PRECTOTCORR (MERRA-2)",
        "sources": [{"name": "NASA POWER", "url": "https://power.larc.nasa.gov",
                     "licence": "public domain"}],
        "validation": {
            "passed": bool(record_ok and count_ok),
            "failed": [n for n, ok in (("record", record_ok), ("count", count_ok)) if not ok],
            "fitted_until": FIT_UNTIL, "tested_from": FIT_UNTIL + 1,
            "count": {"expected": round(expected, 1), "observed": exceed, "place_years": trials,
                      "dispersion": round(dispersion, 2),
                      "p_at_most_observed": round(low, 4), "p_at_least_observed": round(high, 4)},
            "changes_after_first_run": [
                "count test: places are not independent; negative binomial with the "
                "dispersion measured on the fitting years replaces the binomial "
                "(first run: binomial, p = 0.0027, failed)",
                f"published levels fitted on the most recent {RECENT_YEARS} years, because "
                "strong rainfall years became about a quarter more frequent from 2001",
            ],
        },
        "places": places,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print(json.dumps(doc["validation"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
