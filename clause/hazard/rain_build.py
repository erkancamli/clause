"""Extreme daily rainfall at Türkiye's 81 provincial centres, for vehicle cover.

    python -m clause.hazard.rain_build

Offline, like the earthquake build. The data is NASA POWER's daily
precipitation (PRECTOTCORR, from the MERRA-2 reanalysis), public domain, from
1981. The policy settles on the same series for the same point, so the model
and the index are the same thing measured the same way: no gauge that a model
fitted elsewhere would have to be translated to.

The method and the test are those of ``daily_extremes``, which this build
shares with the storm cover's: for each place, the largest daily total in
each calendar year, and a Gumbel distribution fitted to those maxima by
probability weighted moments. The test, set before any result was seen, is
the one the earthquake models pass:

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

import sys

from .daily_extremes import BUILD, FIT_UNTIL, MODELS, RECENT_YEARS, Spec, build

# Kept by name for anything that imported them from here.
CACHE = BUILD / "rain"
OUT = MODELS / "rain_TR.json"

SPEC = Spec(
    parameter="PRECTOTCORR",
    kind="rain_extreme",
    index="largest daily precipitation, NASA POWER PRECTOTCORR (MERRA-2)",
    unit="mm",
    cache=CACHE,
    out=OUT,
    changes_after_first_run=(
        "count test: places are not independent; negative binomial with the "
        "dispersion measured on the fitting years replaces the binomial "
        "(first run: binomial, p = 0.0027, failed)",
        f"published levels fitted on the most recent {RECENT_YEARS} years, because "
        "strong rainfall years became about a quarter more frequent from 2001",
    ),
    stem="rain",
    user_agent="Clause rain build",
)

SOURCES = [{"name": "NASA POWER", "url": "https://power.larc.nasa.gov", "licence": "public domain"}]

#: The countries the place index covers, which is where this can be fitted.
EVERY_COUNTRY = ("CL", "GR", "ID", "IT", "JP", "MX", "NZ", "PH", "TR", "TW", "US")

__all__ = ["CACHE", "FIT_UNTIL", "OUT", "SPEC", "main"]


def main(argv: list[str]) -> None:
    """Build one country's model per code given, or Türkiye's when none is.

        python -m clause.hazard.rain_build
        python -m clause.hazard.rain_build JP US MX
        python -m clause.hazard.rain_build --all
    """
    from ..countries import NAMES
    from .daily_extremes import world_places

    codes = [a.upper() for a in argv if not a.startswith("-")]
    if "--all" in argv:
        codes = ["TR"] + sorted(c for c in EVERY_COUNTRY if c != "TR")
    for code in codes or ["TR"]:
        name = NAMES.get(code, code)
        where = None if code == "TR" else world_places(code)
        if where is not None and len(where) < 2:
            print(f"{code}: no places to fit on", file=sys.stderr)
            continue
        print(f"\n== {code} {name} ==", flush=True)
        doc = build(SPEC, sources=SOURCES, code=code, name=name, where=where)
        v = doc["validation"]
        print(f"{code}: {len(doc['places'])} places -> {SPEC.file_for(code).name}  "
              + ("passed" if v["passed"] else "FAILED: " + ", ".join(v["failed"])), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
