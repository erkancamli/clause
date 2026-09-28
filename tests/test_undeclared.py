"""What it used to cost to leave a rating factor out.

Found by asking the protocol the same question twice, once with an answer and
once without it, and comparing what came back. Three answers were cheaper to
withhold than to give, which is the one thing a contract about insurable
interest cannot allow: the buyer who knows their building is old, or their car
is old, was better off saying nothing.

Every number in here was measured before the fix, not reasoned about.
"""

from __future__ import annotations

import re

import pytest

from clause.perils.quake import Earthquake
from clause.protocol.valuation import ValuationError, value_of

KADIKOY = {"latitude": 40.9903, "longitude": 29.0270, "radius_km": 50}


def test_a_home_without_its_year_is_refused_rather_than_valued_as_new() -> None:
    """110 m² in Istanbul: 57,040.63 with no year, 31,372.35 said as 1968.

    Eighty two per cent more cover for saying less, because the ceiling
    factor that scales rebuild cost down for an old building was simply never
    applied. Every home has a year and the page has always asked for one, so
    the missing answer was never a buyer who could not give it.
    """
    old = value_of({"kind": "home", "building": "flat", "area_m2": 110, "built": 1968},
                   country="TR")
    new = value_of({"kind": "home", "building": "flat", "area_m2": 110, "built": 2021},
                   country="TR")
    # The rebuild rate escalates, so the figures move; what the year does to
    # them does not. 55% of new against 95%, which is the whole of the gap the
    # missing answer used to skip.
    assert old.value / new.value == pytest.approx(0.55 / 0.95, rel=1e-6)

    with pytest.raises(ValuationError, match="the year it was built"):
        value_of({"kind": "home", "building": "flat", "area_m2": 110}, country="TR")


def test_a_vehicle_without_its_model_year_is_refused_rather_than_uncapped() -> None:
    """A 2005 car declared at 240,000 is held to 50,000 when the year is said.

    With the year left out the whole 240,000 stood, which is exactly what the
    cap above it is written to prevent: "a stated value cannot buy new car
    cover for an old one". Nearly five times the cover, for one blank field.
    """
    capped = value_of({"kind": "vehicle", "value": 240_000, "model_year": 2005}, country="TR")
    assert capped.value == pytest.approx(50_000.0)

    with pytest.raises(ValuationError, match="the model year"):
        value_of({"kind": "vehicle", "value": 240_000}, country="TR")


def test_an_unsaid_building_year_is_priced_as_the_oldest_and_not_the_newest() -> None:
    """The price bar before the buyer has described the building.

    That subject has no year and still has to be priced, so it cannot be
    refused the way a valuation can. It used to be priced as a building of the
    current code -- the cheapest of the four bands -- which made the first
    figure a buyer saw one that no honest answer could improve on, and made
    every honest answer dearer: 706.29 against 770.98 for the same cover on a
    pre 1976 building.

    It is priced as the oldest now. The first figure is the dearest the
    building could be and answering only brings it down.
    """
    quake = Earthquake()
    unsaid = quake.vulnerability(dict(KADIKOY))
    oldest = quake.vulnerability({**KADIKOY, "built": 1968})
    newest = quake.vulnerability({**KADIKOY, "built": 2021})

    assert newest == 0.0, "a building of the current code is still the cheap end"
    assert oldest > newest, "the bands no longer separate an old building from a new one"
    assert unsaid == oldest, "an unsaid year is priced at something other than the oldest"


def test_the_page_prices_an_unsaid_year_the_same_way_the_protocol_does() -> None:
    """Otherwise the bar falls when the protocol answers and rises when they type.

    The page carries its own model of the payout curve so the price is never
    empty while a quote is in flight. That model had the same hole: no year
    meant no shift, which is a building of the current code. If only one of
    the two is fixed the figure on screen moves for no reason a buyer can see.

    Both take the oldest year the schedule allows, and the schedule is the
    protocol's own, so there is one definition rather than two.
    """
    from pathlib import Path

    from clause.protocol.valuation import BUILT, schedule

    page = (Path(__file__).resolve().parent.parent / "site" / "index.html").read_text(
        encoding="utf-8")
    body = page[page.index("function structure()"):]
    body = body[:body.index("\n}\n")]

    assert "VALUATION.built" in body, (
        "the page no longer takes its floor from the protocol's own schedule")
    assert not re.search(r"builtYear\s*\?\s*homeAge\([^)]*\)\.shift\s*:\s*0", body), (
        "an unsaid year is back to a shift of zero, which is a building of the current code")

    # And the floor really is the same number on both sides.
    assert schedule()["built"][0] == BUILT[0] == 1900
