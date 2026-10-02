"""The drought figures the page prints, against the figures that settle.

This was the worst of the audit's findings for a buyer. site/app/10-model.js
carried a copy of ``_DEFINED`` in clause/perils/weather.py -- which that file's
own comment calls "what the build starts from and what it overwrites".
``_stations()`` then replaces every normal and every variability with the
measured figures in clause/hazard/models/season_TR.json, and the protocol
prices and settles on those. The page never re-read them, and there is no API
that serves them the way /api/storm and /api/vehicle serve theirs.

Measured before the fix: all 58 stations disagreed on the normal, 57 of 58 on
the variability, by 0.6 to 58.4 per cent. The drought curve is shares of the
normal, so the error goes straight into every millimetre the page prints. At
Samsun:

    the page said   "pays below 214.4 mm"      (0.8 x 268.0)
    the contract    "at or below 135.36 mm"    (0.8 x 169.2)

and for 27 of the 58 stations the page named a trigger *easier* to reach than
the predicate, which is a payout promised and refused.

scripts/season_table.py writes the table from the model. This holds them
together.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from clause.perils.weather import STATIONS

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "site" / "app" / "10-model.js"
#: The shares of the normal the drought curve pays at, so the figures below are
#: the ones a buyer actually reads rather than the raw normal.
SHARES = (0.8, 0.6, 0.4)


def on_the_page() -> dict[str, dict]:
    js = MODEL.read_text(encoding="utf-8")
    at = js.index("var STATIONS=") + len("var STATIONS=")
    return json.loads(js[at:js.index("};", at) + 1])


def test_the_page_knows_the_same_stations() -> None:
    assert set(on_the_page()) == set(STATIONS)


def test_every_normal_and_every_variability_is_the_models_own() -> None:
    page = on_the_page()
    wrong = []
    for code, station in STATIONS.items():
        row = page[code]
        if abs(row["normal"] - station.normal_mm) > 5e-5:
            wrong.append(f"{code} normal {row['normal']} vs {station.normal_mm}")
        if abs(row["cv"] - station.variability) > 5e-5:
            wrong.append(f"{code} cv {row['cv']} vs {station.variability}")
    assert not wrong, "\n".join(wrong[:10])


def test_every_threshold_a_buyer_reads_is_the_one_that_settles() -> None:
    """The figures themselves, at the levels the ladder prints, because that is
    what a buyer compares against the rain."""
    page = on_the_page()
    for code, station in STATIONS.items():
        for share in SHARES:
            said = round(page[code]["normal"] * share, 2)
            settles = round(station.normal_mm * share, 2)
            assert abs(said - settles) < 0.01, (
                f"{code}: the page says {said} mm at {share:.0%} of normal, "
                f"the contract {settles} mm")


def test_the_labels_and_the_windows_match_too() -> None:
    page = on_the_page()
    for code, station in STATIONS.items():
        row = page[code]
        assert row["name"] == station.name
        assert row["season"] == station.season
        assert tuple(row["opens"]) == tuple(station.opens)
        assert row["window"] == int(station.window_days)
        assert abs(row["lat"] - station.latitude) < 5e-5
        assert abs(row["lon"] - station.longitude) < 5e-5


def test_the_writer_has_nothing_left_to_write() -> None:
    """Run the generator: if it changes the page, the page was stale."""
    before = MODEL.read_text(encoding="utf-8")
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "season_table.py")],
                          capture_output=True, text=True, cwd=ROOT,
                          env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"})
    assert done.returncode == 0, done.stderr
    assert MODEL.read_text(encoding="utf-8") == before, (
        "scripts/season_table.py rewrote the page, so it was out of date")
