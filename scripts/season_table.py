"""Write the drought season table into the page from the model that settles.

site/app/10-model.js carried a hand-kept copy of ``_DEFINED`` in
clause/perils/weather.py, which is what the build *starts* from. ``_stations()``
then overwrites every normal and every variability with the measured figures in
clause/hazard/models/season_TR.json, and the protocol prices and settles on
those. The page never learned. Measured before this script existed: all 58
stations disagreed on the normal, 57 of 58 on the variability, up to 58 per
cent out, and for 27 of the 58 the page named a trigger easier to reach than
the contract would honour -- a payout promised that the predicate refuses.

Run it after the season model changes:

    .venv/bin/python scripts/season_table.py

tests/test_site_season_table.py fails if the two ever part company again, so
nobody has to remember to.
"""

from __future__ import annotations

import re
from pathlib import Path

from clause.perils.weather import STATIONS

PAGE = Path(__file__).resolve().parent.parent / "site" / "app" / "10-model.js"
MARK = "var STATIONS="


def number(value: float) -> str:
    """As the page's own literals are written: no trailing zero it can lose."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def table() -> str:
    rows = []
    for code, station in STATIONS.items():
        rows.append(
            '"%s":{"name":"%s","lat":%s,"lon":%s,"season":"%s","opens":[%d,%d],'
            '"window":%d,"normal":%s,"cv":%s}'
            % (code, station.name, number(station.latitude), number(station.longitude),
               station.season, station.opens[0], station.opens[1],
               int(station.window_days), number(station.normal_mm),
               number(station.variability))
        )
    return MARK + "{" + ",".join(rows) + "};"


def main() -> int:
    source = PAGE.read_text(encoding="utf-8")
    at = source.index(MARK)
    end = source.index("};", at) + 2
    written = source[:at] + table() + source[end:]
    if written == source:
        print("the page already carries the model's own season table")
        return 0
    PAGE.write_text(written, encoding="utf-8")
    print(f"wrote {len(STATIONS)} stations into {PAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
