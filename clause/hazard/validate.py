"""Testing a model on years it never saw. Offline, with the build.

A model is fitted on the catalogue up to the end of 2010 and then asked about
2011 onward. It is published for sale only if it passes all of these:

    Enough record   at least 30 mainshocks of magnitude 5 or more in the years
                    it was fitted on. Below that the rate is a guess.

    Count test      the number of mainshocks of magnitude 5 or more in the test
                    years falls inside the central 95 per cent of what the model
                    forecast. Earthquake counts vary more from year to year than
                    a Poisson process allows, so the interval is a negative
                    binomial whose spread is measured from the fitted years
                    themselves rather than assumed.

    Where           the test years' mainshocks land where the model said they
                    would more than a flat map would: positive information gain
                    per event against a uniform rate over the region.

    What it prices  for circles of 50 km around the country's cities, the
                    events of magnitude 5.5 or more that actually happened in
                    the test years are between half and double what the model
                    expected. This is the figure a premium is made of, so it is
                    tested directly.

Every number is written into the model file, pass or fail. A failed country is
not hidden: its card says which test it failed and by how much.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

import numpy as np

from .build import CACHE, REFERENCE_MAGNITUDE, fit
from .model import HazardModel, haversine_km
from .regions import Region
from .sources import fetch_places

FIT_UNTIL = 2010
MIN_MAINSHOCKS = 30
SITE_RADIUS_KM = 50.0
SITE_MAGNITUDE = 5.5
MAX_SITES = 300
RATIO_BOUNDS = (0.5, 2.0)


def _nb_cdf(k: int, mean: float, dispersion: float) -> float:
    """P(X <= k) for a negative binomial with this mean and variance ratio."""
    if mean <= 0:
        return 1.0
    if dispersion <= 1.0001:
        # Poisson
        term, total = math.exp(-mean), 0.0
        for i in range(k + 1):
            total += term
            term *= mean / (i + 1)
        return min(1.0, total)
    r = mean / (dispersion - 1.0)
    p = r / (r + mean)
    total = 0.0
    for i in range(k + 1):
        total += math.exp(math.lgamma(i + r) - math.lgamma(r) - math.lgamma(i + 1)
                          + r * math.log(p) + i * math.log(1 - p))
    return min(1.0, total)


def _in_outline(model: HazardModel, lat: float, lon: float) -> bool:
    return model.contains(lat, lon)


def backtest(region: Region, events: list[dict], outline) -> dict[str, Any]:
    fitted = fit(region, events, until=FIT_UNTIL)
    mainshock = fitted["mainshock"]
    doc = {"code": region.code, "name": region.name, "grid": fitted["grid"],
           "b_value": fitted["b_value"], "max_magnitude": fitted["max_magnitude"],
           "outline": outline, "method": {"reference_magnitude": REFERENCE_MAGNITUDE},
           "box": {"south": region.south, "north": region.north, "west": region.west, "east": region.east}}
    model = HazardModel(doc, rates=fitted["rates"].ravel().tolist())

    start_test = dt.datetime(FIT_UNTIL + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    last = max((e["time"] for e in events), default=start_test)
    years_test = max(0.5, (last - start_test) / (365.25 * 86400))

    main = [e for e, keep in zip(events, mainshock) if keep]
    test = [e for e in main if e["time"] >= start_test]
    test5 = [e for e in test if e["magnitude"] >= REFERENCE_MAGNITUDE]

    # Count test, with the spread measured from the fitted years.
    fit_counts: dict[int, int] = {}
    for e in main:
        if e["time"] < start_test and e["magnitude"] >= REFERENCE_MAGNITUDE:
            year = dt.datetime.fromtimestamp(e["time"], dt.timezone.utc).year
            fit_counts[year] = fit_counts.get(year, 0) + 1
    years = list(range(1973, FIT_UNTIL + 1))
    series = np.array([fit_counts.get(y, 0) for y in years], dtype=float)
    dispersion = float(max(1.0, series.var(ddof=1) / series.mean())) if series.mean() > 0 else 1.0
    forecast = fitted["total_rate_m5"] * years_test
    observed = len(test5)
    low_tail = _nb_cdf(observed, forecast, dispersion)
    high_tail = 1.0 - (_nb_cdf(observed - 1, forecast, dispersion) if observed > 0 else 0.0)
    count_ok = low_tail >= 0.025 and high_tail >= 0.025

    # Where: information gain against a flat map of the same total.
    rates = fitted["rates"]
    mean_rate = float(rates.mean())
    gains = []
    for e in test5:
        r = int(round((e["latitude"] - region.south) / fitted["grid"]["step"]))
        c = int(round((e["longitude"] - region.west) / fitted["grid"]["step"]))
        if 0 <= r < rates.shape[0] and 0 <= c < rates.shape[1]:
            gains.append(math.log(max(1e-12, float(rates[r, c])) / mean_rate))
    gain = float(np.mean(gains)) if gains else 0.0
    where_ok = gain > 0

    # What it prices: circles around the country's cities.
    rows, _ = fetch_places(CACHE)
    sites = sorted(((float(r[4]), float(r[5]), int(r[14] or 0), r[1]) for r in rows
                    if len(r) > 14 and r[8] == region.code), key=lambda s: -s[2])[:MAX_SITES]
    sites = [s for s in sites if model.contains(s[0], s[1])]
    test55 = [e for e in test if e["magnitude"] >= SITE_MAGNITUDE]
    expected = observed_sites = 0.0
    for lat, lon, _, _ in sites:
        expected += model.rate_within(lat, lon, SITE_RADIUS_KM, SITE_MAGNITUDE) * years_test
        observed_sites += sum(1 for e in test55
                              if abs(e["latitude"] - lat) < 1.0
                              and haversine_km(lat, lon, e["latitude"], e["longitude"]) <= SITE_RADIUS_KM)
    ratio = (observed_sites / expected) if expected > 0 else float("nan")
    sites_ok = bool(sites) and RATIO_BOUNDS[0] <= ratio <= RATIO_BOUNDS[1]

    record_ok = fitted["stats"]["mainshocks_m5"] >= MIN_MAINSHOCKS
    passed = bool(record_ok and count_ok and where_ok and sites_ok)
    failures = [name for name, ok in (("record", record_ok), ("count", count_ok),
                                      ("where", where_ok), ("sites", sites_ok)) if not ok]
    return {
        "passed": passed,
        "failed": failures,
        "fitted_until": FIT_UNTIL,
        "tested_from": FIT_UNTIL + 1,
        "test_years": round(years_test, 2),
        "record": {"mainshocks_m5_in_fit": fitted["stats"]["mainshocks_m5"], "needed": MIN_MAINSHOCKS},
        "count": {"forecast": round(forecast, 1), "observed": observed,
                  "dispersion": round(dispersion, 2),
                  "p_at_most_observed": round(low_tail, 4), "p_at_least_observed": round(high_tail, 4)},
        "where": {"information_gain_per_event": round(gain, 3), "events": len(gains)},
        "sites": {"cities": len(sites), "radius_km": SITE_RADIUS_KM, "magnitude": SITE_MAGNITUDE,
                  "expected": round(expected, 2), "observed": int(observed_sites),
                  "observed_over_expected": round(ratio, 3) if ratio == ratio else None,
                  "bounds": list(RATIO_BOUNDS)},
    }


def crosscheck_turkey(region: Region, fitted: dict) -> dict[str, Any]:
    """The same catalogue method, set against the fault model Türkiye is priced by.

    Türkiye keeps its fault model, which knows things a smoothed catalogue does
    not, such as the unruptured stretch under the Sea of Marmara. This records
    how far the two disagree at the named places, so the difference is visible
    rather than assumed small.
    """
    from ..perils import EARTHQUAKE
    from ..perils.quake import LOCATIONS

    doc = {"code": "TR", "name": region.name, "grid": fitted["grid"], "b_value": fitted["b_value"],
           "max_magnitude": fitted["max_magnitude"], "outline": [],
           "method": {"reference_magnitude": REFERENCE_MAGNITUDE},
           "box": {"south": region.south, "north": region.north, "west": region.west, "east": region.east}}
    grid = HazardModel(doc, rates=fitted["rates"].ravel().tolist())
    rows = []
    for code, place in LOCATIONS.items():
        subject = EARTHQUAKE.validate_subject({"latitude": place.latitude, "longitude": place.longitude,
                                               "radius_km": SITE_RADIUS_KM})
        faults = EARTHQUAKE.exceedance(subject, 365.25)(SITE_MAGNITUDE)
        catalogue = grid.exceedance(place.latitude, place.longitude, SITE_RADIUS_KM, 1.0)(SITE_MAGNITUDE)
        rows.append({"place": place.name, "fault_model": round(faults, 5),
                     "catalogue_model": round(catalogue, 5),
                     "ratio": round(catalogue / faults, 3) if faults > 0 else None})
    ratios = sorted(r["ratio"] for r in rows if r["ratio"])
    return {
        "what": f"one year probability of magnitude {SITE_MAGNITUDE} or more within {SITE_RADIUS_KM:g} km",
        "places": rows,
        "median_catalogue_over_fault": ratios[len(ratios) // 2] if ratios else None,
    }
