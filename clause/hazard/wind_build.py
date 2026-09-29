"""Extreme daily wind at Türkiye's 81 provincial centres, for storm cover.

    python -m clause.hazard.wind_build

Offline, like the rain and earthquake builds. The data is NASA POWER's daily
maximum wind speed at ten metres (WS10M_MAX, from the MERRA-2 reanalysis),
public domain, from 1981, converted to km/h because that is the unit the
national service's warnings and a buyer's weather app both use. The policy
settles on the same series for the same point, so the model and the index are
the same thing measured the same way.

What this figure is, and is not. A reanalysis gives the strongest hour's mean
wind over a grid cell of about fifty kilometres, not the gust a station on a
ridge or a coast records: gusts run half as much again above it, and more in
a squall. The thresholds are set on the same series, so a place's 1 in 25
year day is its 1 in 25 year day in this series, whatever a gauge would have
shown, and the basis risk the peril states says so.

The method and the test are those of ``daily_extremes``, fixed before the
first run: fitted on 1981 to 2010, tested on 2011 onward, the count of test
years above each place's 1 in 5 year level judged against the fit with the
year to year dispersion measured on the fitting years, at least 30 years of
record everywhere, and the published levels fitted on the most recent 30
years. Nothing here was changed after a result was seen; if the first run
fails its test, the failure is written in the model file and the peril
refuses to price anywhere until a change is made and recorded.
"""

from __future__ import annotations

import sys

from .daily_extremes import BUILD, MODELS, Spec, build

# m/s to km/h.
KMH = 3.6

SPEC = Spec(
    parameter="WS10M_MAX",
    kind="wind_extreme",
    index="largest daily maximum wind speed at 10 m, NASA POWER WS10M_MAX (MERRA-2), in km/h",
    unit="km/h",
    cache=BUILD / "wind",
    out=MODELS / "wind_TR.json",
    scale=KMH,
    stem="wind",
    user_agent="Clause wind build",
)

SOURCES = [{"name": "NASA POWER", "url": "https://power.larc.nasa.gov", "licence": "public domain"}]

#: The countries the place index covers, which is where this can be fitted.
EVERY_COUNTRY = ("CL", "GR", "ID", "IT", "JP", "MX", "NZ", "PH", "TR", "TW", "US")


def main(argv: list[str]) -> None:
    """Build one country's model per code given, or Türkiye's when none is.

        python -m clause.hazard.wind_build
        python -m clause.hazard.wind_build JP US MX
        python -m clause.hazard.wind_build --all
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
