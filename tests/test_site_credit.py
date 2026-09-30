"""Who the data belongs to, said where the data is used.

Three of the sets this site shows are other people's work under licences that
ask for the notice: place names from GeoNames under CC BY 4.0, map tiles and
reverse geocoding from OpenStreetMap, airport codes from airportsdata under
MIT. The protocol sends an attribution line with two of them and the page was
dropping one of them on the floor, which is not a styling lapse but a licence
not being met.

The pattern this site already uses is attribution at the point of use, under
the results that came from it, rather than a colophon nobody opens. These hold
that pattern.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import page_assembled

ROOT = Path(__file__).resolve().parent.parent
PAGE = page_assembled()


def test_the_licences_that_ask_for_a_notice_get_one() -> None:
    """Named in the copy a reader sees, not only in a source comment."""
    body = re.sub(r"/\*.*?\*/", "", PAGE, flags=re.S)
    for who, licence in (("GeoNames", "CC BY 4.0"),
                         ("airportsdata", "MIT"),
                         ("OpenStreetMap", None)):
        assert who in body, f"{who} is not credited anywhere a reader looks"
        if licence:
            near = [m for m in re.findall(r"[^<>\"]{0,200}" + who + r"[^<>\"]{0,200}", body)
                    if licence in m]
            assert near, f"{who} is named without its licence ({licence})"


def test_the_airport_list_credits_the_set_it_came_from() -> None:
    """The protocol sends the line; the page has to actually show it.

    Under the results, where GeoNames already sits under the place results.
    """
    at = PAGE.index("function airportHits(")
    body = PAGE[at : PAGE.index("\n}", PAGE.index("box.innerHTML=hits.map", at))]
    assert "reply.attribution" in body, (
        "the attribution the protocol sends is dropped rather than shown"
    )
    assert "airportsdata" in body, "the airport list names no source"


def test_the_protocol_still_sends_what_the_page_shows() -> None:
    """An attribution the page prints and the protocol stopped sending would
    be this site claiming a provenance on its own word."""
    from clause.perils.airports import attribution

    said = attribution()
    assert "airportsdata" in said and "MIT" in said, said


def test_the_assistant_says_whose_model_it_runs_on() -> None:
    """An assistant that will not name its model is asking for more trust
    than it has earned, and this one moves money."""
    body = re.sub(r"/\*.*?\*/", "", PAGE, flags=re.S)
    assert "Anthropic" in body, "the model behind the assistant is never named"


def test_every_agency_that_can_settle_money_is_named_in_the_terms() -> None:
    """The rulebook is section 10 of every contract.

    A source whose reading can settle a policy, or refuse to, has to be named
    there and not only in the code that queries it. Two were missing: the
    chain of agencies actually asked is USGS, EMSC, GFZ GEOFON and the
    national network.
    """
    from clause.hazard.regions import REGIONS
    from clause.protocol import rulebook

    quake = rulebook.RULES["earthquake"]
    written = " ".join([quake["primary"], *quake["fallbacks"]])
    region = REGIONS["TR"]
    for source in region.sources:
        first = source.name.split()[0]
        assert first in written, (
            f"{source.name} is queried on every event and is not in the terms"
        )
