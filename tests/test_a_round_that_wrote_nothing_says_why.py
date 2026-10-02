"""A reading round that wrote nothing is the ordinary case, and says so.

On the live deployment the sources block of /api/health read:

    "measuring": true, "rounds": 8, "references_last_round": 5,
    "readings_written": 0, "failing": {}

Which is correct, and unreadable. Every measured reference was asked, every
agency answered, and none of them had anything larger than the figure already
standing: no earthquake in the circle, no rain over the total. That is a
working oracle on a quiet day. It is also, to the character, what a feed that
has silently stopped measuring would report, and the difference mattered
enough last time to be worth three findings and a release.

The reasons were never missing. They were written to the log, at INFO, on a
machine whose log is not something anybody reading a health check can open.
So the round now repeats back what it found, bounded, because the number of
measured references grows with the book.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from clause.api.app import LAST_ROUND_NOTES, create_app, round_notes
from clause.api.security import Settings
from clause.oracle.feed import Attestation, Feed

QUIET = "nothing larger than the 0 already standing"
QUAKE = ("earthquake.usgs.gov/fdsnws/event/1/query"
         "?lat=37.29&lon=37.04&radius_km=100")


def test_a_quiet_round_is_reported_as_a_round_that_found_nothing() -> None:
    notes = round_notes([
        Attestation(QUAKE, "max_magnitude", False, QUIET),
        Attestation("archive-api.open-meteo.com/v1/archive?index=season"
                    "&station=TR-KONYA&lat=37.87&lon=32.48",
                    "rainfall_mm", True, "three agencies agreed", value=118.4),
    ])

    assert notes[0] == {"reference": QUAKE, "written": False, "why": QUIET}
    assert notes[1]["written"] is True
    assert notes[1]["why"] == "three agencies agreed"


def test_the_round_the_check_repeats_back_is_bounded() -> None:
    """A health check is not a log, and the measured book grows."""
    many = [Attestation(f"source-{n}", "max_magnitude", False, QUIET)
            for n in range(LAST_ROUND_NOTES * 3)]

    assert len(round_notes(many)) == LAST_ROUND_NOTES


def test_the_health_check_carries_the_last_round() -> None:
    app = create_app(trials=50, seed=11, run_chain=False, seed_book=False,
                     settings=Settings(faucet=True))
    with TestClient(app) as client:
        # What the reading loop leaves behind after a round in which every
        # agency answered and none of them had anything new.
        app.state.feed = Feed()
        app.state.measuring = {
            "rounds": 8, "last_at": time.time(), "asked": 1, "wrote": 0,
            "last_error": "",
            "notes": round_notes([Attestation(QUAKE, "max_magnitude", False, QUIET)]),
        }
        sources = client.get("/api/health").json()["sources"]

    assert sources["measuring"] is True
    assert sources["readings_written"] == 0
    assert sources["failing"] == {}
    # The zero above, explained, without opening a log on the host.
    assert sources["last_round"] == [
        {"reference": QUAKE, "written": False, "why": QUIET},
    ]


def test_a_check_taken_before_the_first_round_has_no_round_to_report() -> None:
    """And says nothing rather than inventing an empty one."""
    app = create_app(trials=50, seed=11, run_chain=False, seed_book=False,
                     settings=Settings(faucet=True))
    with TestClient(app) as client:
        app.state.feed = Feed()
        app.state.measuring = {"rounds": 0, "last_at": 0.0, "asked": 0,
                               "wrote": 0, "last_error": ""}
        sources = client.get("/api/health").json()["sources"]

    assert sources["last_round"] == []
    assert sources["seconds_since_round"] is None
