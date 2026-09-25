"""Writing what the agencies said onto the chain, and refusing to when they disagree.

The readers are tested in test_oracle.py against responses actually fetched
from USGS, EMSC and AFAD. This file tests the layer above them: which
references get asked about at all, what is written, and -- the part that
matters most -- what is deliberately not written.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from clause.oracle.feed import (Feed, MEASURED_HOSTS, circle_of, field_of,
                                host_of, is_measured)

FEEDS = pathlib.Path(__file__).parent / "feeds"

# The circle the Kahramanmaras fixtures sit in, and a window around the
# sequence. Pazarcik was 01:17 UTC on 6 February 2023 and Elbistan 10:24.
EPICENTRE = (37.29, 37.04)
WINDOW = (1675640000.0, 1675690000.0)

MEASURED = ("earthquake.usgs.gov/fdsnws/event/1/query"
            "?lat=37.29&lon=37.04&radius_km=100")
SIMULATED = "api.seismic.example/v1/max-magnitude?lat=37.29&lon=37.04&radius_km=100"


def canned(**by_host: str):
    """A fetch that answers from the recorded responses instead of the network."""
    def fetch(url: str) -> tuple[bytes, str]:
        for fragment, name in by_host.items():
            if fragment in url:
                if name == "down":
                    raise OSError("connection refused")
                return (FEEDS / name).read_bytes(), url
        raise OSError(f"nothing recorded for {url}")
    return fetch


# -- which references are anybody's business --------------------------------

def test_a_reference_that_names_an_agency_is_one_somebody_asks_about() -> None:
    assert is_measured(MEASURED)
    assert host_of(MEASURED) in MEASURED_HOSTS


def test_a_reference_reserved_for_examples_is_never_fetched() -> None:
    """The demonstration book writes against a domain that cannot resolve. A
    protocol that tried to resolve it would be asking a question with no one
    on the other end, and the answer it invented would settle policies."""
    assert not is_measured(SIMULATED)
    assert not is_measured("api.weather.example/v1/rain?lat=1&lon=2")


def test_the_circle_is_read_back_out_of_the_reference() -> None:
    assert circle_of(MEASURED) == (37.29, 37.04, 100.0)
    # A shaking reference is read at the address and carries no radius.
    assert circle_of("earthquake.usgs.gov/fdsnws/event/1/query"
                     "?index=mmi&lat=37.29&lon=37.04") == (37.29, 37.04, 0.0)
    assert circle_of("earthquake.usgs.gov/fdsnws/event/1/query") is None


def test_the_reference_says_which_quantity_it_reads() -> None:
    assert field_of(MEASURED) == "max_magnitude"
    assert field_of("earthquake.usgs.gov/fdsnws/event/1/query"
                    "?index=mmi&lat=1&lon=2") == "mmi"


# -- what comes back --------------------------------------------------------

def test_three_agencies_measuring_one_earthquake_give_one_reading() -> None:
    """USGS 7.8, EMSC 7.8, AFAD 7.7 for Pazarcik. The primary's number is the
    number; the others are there to say whether it can be believed, and an
    average of two official magnitudes would be a third number nobody
    published.

    Inside Türkiye the primary is AFAD, because that is what the rulebook on
    the buyer's own policy names: the national network, with the others read
    against it. So this reads 7.7 and not 7.8, and the tenth between them is
    not rounding -- a policy attaching at 7.75 pays on one official source and
    not on the other, which is the reason this layer names its primary in the
    contract instead of picking whichever answered first.
    """
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "usgs_kahramanmaras.json",
                                "seismicportal": "emsc_kahramanmaras.json",
                                "afad": "afad_kahramanmaras.json"}))
    reading = feed.earthquake(latitude=EPICENTRE[0], longitude=EPICENTRE[1],
                              radius_km=100.0, since=WINDOW[0], until=WINDOW[1])
    assert reading.settles, reading.why
    assert reading.primary == "AFAD"
    assert reading.value == pytest.approx(7.7, abs=0.05)
    assert {o.source for o in reading.observations} >= {"USGS", "EMSC", "AFAD"}
    assert reading.spread <= 0.3


def test_the_primary_is_the_one_the_policy_names() -> None:
    """The national network where there is one this protocol reads, and USGS
    where there is not. Shaking is USGS's own estimate wherever it is, because
    no other source here publishes that quantity at all."""
    assert Feed.primary_for(37.29, 37.04, "max_magnitude") == "AFAD"
    assert Feed.primary_for(35.68, 139.69, "max_magnitude") == "USGS"
    assert Feed.primary_for(37.29, 37.04, "mmi") == "USGS"


def test_a_source_that_cannot_be_reached_is_not_a_reading_of_zero() -> None:
    """The failure that has to be loud. A quiet hour and an unreachable agency
    look identical to a running maximum, and only one of them means nothing
    happened."""
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "down",
                                "seismicportal": "down", "afad": "down"}))
    reading = feed.earthquake(latitude=EPICENTRE[0], longitude=EPICENTRE[1],
                              radius_km=100.0, since=WINDOW[0], until=WINDOW[1])
    assert not reading.settles
    assert reading.value == 0.0
    assert "USGS" in reading.why and "EMSC" in reading.why
    assert feed.trouble


# -- what is written, and what is held --------------------------------------

class FakeChain:
    """Just enough chain to see what the feed does to one."""

    def __init__(self, reference: str, standing: float = 0.0) -> None:
        import threading

        from clause.chain.world import EdgeReading

        self.lock = threading.RLock()
        self.readings = {reference: EdgeReading(
            reference=reference, fields={"max_magnitude": standing, "events": 0},
            attested_at=0.0, publisher="USGS", index_field="max_magnitude")}
        self.written: list[tuple[str, str, float]] = []

    def attest(self, reference, field, value, *, final=True):
        self.written.append((reference, field, value))
        self.readings[reference].fields[field] = value
        return self.readings[reference]


def test_a_reading_the_agencies_agree_on_is_written() -> None:
    chain = FakeChain(MEASURED)
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "usgs_kahramanmaras.json",
                                "seismicportal": "emsc_kahramanmaras.json",
                                "afad": "afad_kahramanmaras.json"}))
    notes = feed.poll(chain, now=WINDOW[1])
    assert len(notes) == 1 and notes[0].written, notes[0].why
    assert chain.written and chain.written[0][1] == "max_magnitude"
    # AFAD's figure, because the circle is in Türkiye; see above.
    assert chain.written[0][2] == pytest.approx(7.7, abs=0.05)


def test_sources_further_apart_than_the_cover_settles_within_write_nothing() -> None:
    """The rule the Paris Charles de Gaulle station is the reason for. Picking
    one of two irreconcilable official numbers is deciding, and not deciding is
    the entire promise of a parametric policy."""
    chain = FakeChain(MEASURED)
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "usgs_kahramanmaras.json",
                                "seismicportal": "emsc_kahramanmaras.json",
                                "afad": "afad_kahramanmaras.json"}))
    # A tolerance tighter than the agencies' own disagreement about this event.
    import clause.oracle.agreement as agreement

    was = agreement.TOLERANCE["earthquake"]
    agreement.TOLERANCE["earthquake"] = 0.0
    try:
        notes = feed.poll(chain, now=WINDOW[1])
    finally:
        agreement.TOLERANCE["earthquake"] = was
    assert notes and not notes[0].written
    assert not chain.written
    assert "do not agree" in notes[0].why


def test_a_quiet_window_does_not_lower_a_running_maximum() -> None:
    """A cover reads the largest event in its window. Asking again an hour
    later and finding a quiet hour does not undo the earthquake."""
    chain = FakeChain(MEASURED, standing=7.9)
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "usgs_kahramanmaras.json",
                                "seismicportal": "emsc_kahramanmaras.json",
                                "afad": "afad_kahramanmaras.json"}))
    notes = feed.poll(chain, now=WINDOW[1])
    assert notes and not notes[0].written
    assert "already standing" in notes[0].why
    assert chain.readings[MEASURED].fields["max_magnitude"] == 7.9


def test_a_window_nobody_answered_for_is_asked_again() -> None:
    """If the sources were unreachable, the window must not close behind them:
    an agency down for an hour would otherwise erase that hour for good."""
    chain = FakeChain(MEASURED)
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "down",
                                "seismicportal": "down", "afad": "down"}))
    feed.poll(chain, now=WINDOW[1])
    assert chain.readings[MEASURED].measured_through == 0.0

    feed.fetch = canned(**{"earthquake.usgs.gov": "usgs_kahramanmaras.json",
                           "seismicportal": "emsc_kahramanmaras.json",
                           "afad": "afad_kahramanmaras.json"})
    notes = feed.poll(chain, now=WINDOW[1])
    assert notes[0].written
    assert chain.readings[MEASURED].measured_through == WINDOW[1]


def test_the_simulated_reference_is_left_alone() -> None:
    chain = FakeChain(SIMULATED)
    feed = Feed(fetch=canned())          # any fetch at all would raise
    assert feed.poll(chain, now=WINDOW[1]) == []
    assert not chain.written
