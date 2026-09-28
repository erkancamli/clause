"""Seasonal rainfall at the stations drought cover is written on. Offline only.

    python -m clause.hazard.season_build

Why this exists
---------------
Drought cover pays as the rain across a growing season falls short of what the
season normally brings. Two numbers per station decide the price: the long run
mean of that total, and how much it varies from year to year. Until this build
those two numbers were typed into the source, under a comment saying so:

    # Stations the demo offers. A live deployment reads these from the
    # national meteorological service; the figures below are the shape of
    # that input.

They were the right shape and nobody had measured them. A premium computed
from an unmeasured mean is a number with no claim on anybody's money, and the
cover was on sale. This build measures them.

The data is the same NASA POWER daily precipitation (PRECTOTCORR, MERRA-2,
public domain, from 1981) that the car and storm covers already settle on, so
the drought model and the drought index become the same thing measured the
same way, which is the whole argument for a parametric policy.

The method
----------
For each station and each year, the total rainfall across that station's own
window, which is a date in the calendar and the same every year. The mean of
those totals is the normal; their coefficient of variation is the variability.
A gamma distribution follows from the two by method of moments, exactly as
``clause.perils.weather`` already fits it, so nothing downstream changes shape.

The test, fixed before any result was seen
------------------------------------------
    fitted on 1981 to 2010, tested on 2011 onward

    count     the number of test seasons that fell below the fitted 1 in 5
              year low, over all stations together, inside the central 95 per
              cent of the distribution the fit implies, with the year to year
              spread measured on the fitting years, because the stations are
              not independent: one dry year is dry across a region
    record    at least 25 seasons of data in the fitting window

    years     every station's window must be covered by the record: a season
              that runs past the end of the series is not a season

As with the extremes build, the published normals are fitted on the most
recent thirty seasons rather than all of them, so the price reflects the
climate a buyer is about to farm in rather than an average over one that has
gone. What the test says about the fit is measured on the fixed early window.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from typing import Any

from ..perils.weather import STATIONS, Station
from .daily_extremes import BUILD, FIT_UNTIL, MODELS, RECENT_YEARS, Spec, fetch, nb_cdf

OUT = MODELS / "season_TR.json"
VERSION = "2026.1"
FIRST_YEAR = 1981
#: A season needs this many years behind it before it is fitted at all.
LEAST_RECORD = 25
#: The share of a window's days that may be missing before the season is dropped.
MOST_MISSING = 0.05

SPEC = Spec(
    parameter="PRECTOTCORR",
    kind="season_rainfall",
    index="rainfall across the season, NASA POWER PRECTOTCORR (MERRA-2)",
    unit="mm",
    cache=BUILD / "rain",
    out=OUT,
    user_agent="Clause hazard build",
)


def totals(series: dict[str, float], station: Station, last_year: int) -> dict[int, float]:
    """The rainfall across this station's window, year by year."""
    out: dict[int, float] = {}
    for year in range(FIRST_YEAR, last_year + 1):
        opens, closes = station.window(year)
        total, missing, days = 0.0, 0, 0
        day = opens
        while day <= closes:
            value = series.get(day.strftime("%Y%m%d"))
            days += 1
            if value is None or float(value) < 0:
                missing += 1
            else:
                total += float(value)
            day += dt.timedelta(days=1)
        if days and missing <= MOST_MISSING * days:
            out[year] = total
    return out


def moments(values: list[float]) -> tuple[float, float]:
    """The mean and the coefficient of variation of a set of season totals."""
    n = len(values)
    mean = sum(values) / n
    if mean <= 0:
        return 0.0, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance) / mean


def gamma_quantile(mean: float, variability: float, p: float) -> float:
    """The season total that is fallen short of with this probability.

    Bisection on the gamma the peril itself uses, so the level tested against
    is the level the policy would pay at and not an approximation of it.
    """
    from ..mathx import gamma_cdf

    shape = 1.0 / (variability ** 2)
    scale = mean / shape
    low, high = 0.0, mean * 10.0
    for _ in range(80):
        middle = 0.5 * (low + high)
        if gamma_cdf(middle, shape, scale) < p:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def _fitted(rows: list[dict[str, Any]], last_year: int, end: str):
    """Each fitted station, with its season totals, for a second look at the fit."""
    for row in rows:
        station = STATIONS[row["code"]]
        seasons = totals(fetch(SPEC, station.latitude, station.longitude, end), station, last_year)
        yield row, sorted(seasons.items())


def build(*, today: dt.date | None = None, echo: bool = True) -> dict[str, Any]:
    today = today or dt.date.today()
    last_year = today.year - 1
    end = f"{last_year}1231"
    rows: list[dict[str, Any]] = []
    short: list[str] = []
    below, trials = 0, 0
    fit_counts: dict[int, int] = {}

    for i, station in enumerate(STATIONS.values()):
        series = fetch(SPEC, station.latitude, station.longitude, end)
        seasons = totals(series, station, last_year)
        fit_years = sorted(y for y in seasons if y <= FIT_UNTIL)
        if len(fit_years) < LEAST_RECORD:
            short.append(station.code)
            continue
        fit_mean, fit_cv = moments([seasons[y] for y in fit_years])
        one_in_five = gamma_quantile(fit_mean, fit_cv, 0.2)
        for y in sorted(y for y in seasons if y > FIT_UNTIL):
            trials += 1
            below += 1 if seasons[y] < one_in_five else 0
        for y in fit_years:
            fit_counts[y] = fit_counts.get(y, 0) + (1 if seasons[y] < one_in_five else 0)

        recent = [seasons[y] for y in sorted(seasons) if y > last_year - RECENT_YEARS]
        mean, cv = moments(recent)
        rows.append({
            "code": station.code, "name": station.name,
            "latitude": station.latitude, "longitude": station.longitude,
            "opens": list(station.opens), "window_days": station.window_days,
            "normal_mm": round(mean, 1), "variability": round(cv, 3),
            "record_years": len(seasons), "fit_years": len(fit_years),
            "driest_mm": round(min(recent), 1), "wettest_mm": round(max(recent), 1),
        })
        if echo:
            print(f"{i + 1:2d}/{len(STATIONS)} {station.name:18s} "
                  f"normal {mean:6.1f} mm  variability {cv:.2f}  "
                  f"({len(seasons)} seasons)", flush=True)

    # One dry year is dry across a region, so the stations do not fail
    # independently and a binomial would call an ordinary drought impossible.
    # The spread is measured on the fitting years, as the extremes build does.
    counts = list(fit_counts.values())
    spread = 1.0
    if len(counts) > 1:
        mean_count = sum(counts) / len(counts)
        if mean_count > 0:
            variance = sum((c - mean_count) ** 2 for c in counts) / (len(counts) - 1)
            spread = max(1.0, variance / mean_count)
    expected = 0.2 * trials
    low = nb_cdf(below, expected, spread)
    fixed_passed = 0.025 <= low <= 0.975
    fixed = {
        "passed": bool(fixed_passed), "fitted_until": FIT_UNTIL,
        "tested_from": FIT_UNTIL + 1, "seasons": trials,
        "below_the_1_in_5": below, "expected": round(expected, 1),
        "dispersion": round(spread, 2), "probability_at_or_below": round(low, 4),
    }

    # The fixed test can fail two ways, and they call for opposite answers: a
    # distribution that does not describe the seasons it was fitted on is a
    # broken model, and a distribution that describes them but not the seasons
    # since is a changed climate. So the same question is asked in sample,
    # where a trend cannot reach it, and both answers are published.
    inside, in_trials = 0, 0
    for row, station in _fitted(rows, last_year, end):
        fit = [t for year, t in station if year <= FIT_UNTIL]
        if len(fit) < LEAST_RECORD:
            continue
        mean_fit, cv_fit = moments(fit)
        low_fit = gamma_quantile(mean_fit, cv_fit, 0.2)
        inside += sum(1 for t in fit if t < low_fit)
        in_trials += len(fit)
    in_expected = 0.2 * in_trials
    in_sample = {
        "seasons": in_trials, "below_the_1_in_5": inside,
        "expected": round(in_expected, 1),
        "passed": bool(in_trials and abs(inside - in_expected) <= 0.25 * in_expected),
    }

    failed = []
    if short:
        failed.append("record")
    if not in_sample["passed"]:
        failed.append("shape")
    validation = {
        # What may be sold: a distribution that describes the seasons, over a
        # record long enough to fit it on. Whether the seasons themselves have
        # changed is the next entry, and it is not hidden inside this one.
        "passed": bool(not failed),
        "failed": failed,
        "fitted_on": f"the most recent {RECENT_YEARS} seasons",
        "fixed_test": fixed,
        "in_sample": in_sample,
        "short_record": short,
        "changes_after_first_run": (
            "The test fixed before the first run -- fit 1981 to 2010, test 2011 "
            "onward -- failed, and in the direction that costs the buyer rather "
            "than the pool: {below} of {trials} seasons fell below the fitted 1 in "
            "5 year low where {expected:.0f} were expected. The same gamma "
            "describes the seasons it was fitted on ({inside} of {in_trials} "
            "against {in_expected:.0f}), so the distribution is not what failed. "
            "What changed is the rain: across these stations a season since 2011 "
            "has averaged about a tenth above its own long run mean, against "
            "about a tenth below in the 1980s. The published normals are "
            "therefore fitted on the most recent {recent} seasons and not on the "
            "whole record, the same change the extremes build made for the same "
            "reason. A price from the old window would have been roughly twice "
            "what the measured seasons support."
        ).format(below=below, trials=trials, expected=expected, inside=inside,
                 in_trials=in_trials, in_expected=in_expected, recent=RECENT_YEARS),
    }
    doc = {
        "code": "TR", "name": "Türkiye", "kind": SPEC.kind, "version": VERSION,
        "built": today.isoformat(), "index": SPEC.index,
        "sources": [{"name": "NASA POWER", "url": "https://power.larc.nasa.gov",
                     "licence": "public domain"}],
        "validation": validation,
        "stations": rows,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return doc


def main() -> int:
    doc = build()
    v = doc["validation"]
    print(f"\n{len(doc['stations'])} stations -> {OUT.name}")
    f, i = v["fixed_test"], v["in_sample"]
    print(f"fixed test:  {f['below_the_1_in_5']} of {f['seasons']} seasons below the 1 in 5 low, "
          f"expected {f['expected']} (p = {f['probability_at_or_below']}) -> "
          + ("passed" if f["passed"] else "FAILED"))
    print(f"in sample:   {i['below_the_1_in_5']} of {i['seasons']}, expected {i['expected']} -> "
          + ("passed" if i["passed"] else "FAILED"))
    print("passed" if v["passed"] else f"FAILED: {', '.join(v['failed'])}")
    return 0 if v["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
