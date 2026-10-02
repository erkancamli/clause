"""How precisely a policy says where it is, and why that is a privacy question.

A policy's coordinate is public twice over. It is in the book anybody can
read, and it is inside the oracle reference that lets somebody who does not
work here repeat the query and get the same answer, which is what makes a
reading evidence rather than a claim. So it cannot be coarsened in the public
view alone: the reference would stop matching the query that was actually
made.

It was four decimal places, about eleven metres, which for a home is the front
door. Measured on the live book before this: two policies published
41.0453, 28.7827 beside a street address.

Two places, about 1.1 km, and the policy is written on that point, so the
record, the reference, the predicate and the page all carry the same one.
Nothing measurable is lost: USGS ShakeMap is published on a grid of about a
kilometre, ERA5 on about twenty-five and ERA5-Land on about ten, and a
magnitude policy is a circle fifty or a hundred kilometres across. Sampled
across thirteen coordinates in Türkiye the point moves 61 to 511 m and not one
premium changed.
"""

from __future__ import annotations

import math
import random

import pytest

from clause.perils import EARTHQUAKE, STORM, VEHICLE_FLOOD
from clause.perils.base import PLACE_PLACES, insured_point
from clause.pricing import PricingEngine

#: The address the live book was publishing, to eleven metres.
A_HOME = (41.0453, 28.7827)

WITH_A_COORDINATE = [
    ("earthquake", EARTHQUAKE,
     {"latitude": A_HOME[0], "longitude": A_HOME[1], "radius_km": 50.0,
      "built": 2002, "place": "222. Cadde, Küçükçekmece, İstanbul"}),
    ("shaking", EARTHQUAKE,
     {"latitude": A_HOME[0], "longitude": A_HOME[1], "index": "shaking",
      "built": 2002, "place": "a flat"}),
    ("storm", STORM, {"latitude": A_HOME[0], "longitude": A_HOME[1]}),
    ("vehicle_flood", VEHICLE_FLOOD,
     {"latitude": A_HOME[0], "longitude": A_HOME[1]}),
]


def metres_between(first, second) -> float:
    north = (first[0] - second[0]) * 111_000.0
    east = (first[1] - second[1]) * 111_000.0 * math.cos(math.radians(first[0]))
    return math.hypot(north, east)


@pytest.mark.parametrize("name,peril,subject", WITH_A_COORDINATE,
                         ids=[row[0] for row in WITH_A_COORDINATE])
def test_a_policy_is_written_on_the_coarse_point(name, peril, subject) -> None:
    written = peril.validate_subject(subject)
    assert written["latitude"] == 41.05, name
    assert written["longitude"] == 28.78, name
    # Which is to say: not the eleven-metre point it was given.
    assert (written["latitude"], written["longitude"]) != A_HOME


def test_the_grid_is_the_one_this_file_describes() -> None:
    """Asked as the number, because asking round(x, PLACE_PLACES) against
    PLACE_PLACES would pass whatever it is."""
    assert PLACE_PLACES == 2
    assert insured_point(*A_HOME) == (41.05, 28.78)
    assert metres_between(A_HOME, insured_point(*A_HOME)) < 1200.0


@pytest.mark.parametrize("name,peril,subject", WITH_A_COORDINATE,
                         ids=[row[0] for row in WITH_A_COORDINATE])
def test_the_reference_carries_the_same_point_as_the_record(name, peril,
                                                            subject) -> None:
    """The half that cannot be solved by redacting a view: the reference is
    the query, and it has to be the query that was made."""
    written = peril.validate_subject(subject)
    reference = peril.data_source(written).reference
    assert "41.0453" not in reference, reference
    assert "28.7827" not in reference, reference
    assert "41.05" in reference and "28.78" in reference, reference


def test_the_predicate_carries_it_too(name="earthquake") -> None:
    written = EARTHQUAKE.validate_subject(WITH_A_COORDINATE[0][2])
    said = EARTHQUAKE.predicate(written, EARTHQUAKE.curve_for(written), "quote")
    assert "41.0453" not in said and "28.7827" not in said, said


def test_nothing_rounds_an_already_rounded_point_further() -> None:
    """Writing a policy twice gives the same point, so a renewal and a
    re-quote agree."""
    once = EARTHQUAKE.validate_subject(WITH_A_COORDINATE[0][2])
    twice = EARTHQUAKE.validate_subject(dict(once))
    assert (once["latitude"], once["longitude"]) == (twice["latitude"],
                                                     twice["longitude"])


def test_the_price_does_not_move_with_the_point() -> None:
    """The cost of the coarsening, measured rather than argued. The hazard
    model, the shaking map and the reanalyses are all coarser than the move,
    so the premium should not notice."""
    engine = PricingEngine(trials=2000, seed=7)
    random.seed(4)
    sampled = 0
    worst = 0.0
    for _ in range(14):
        latitude = round(random.uniform(36.5, 41.5), 4)
        longitude = round(random.uniform(27.0, 42.0), 4)
        given = {"latitude": latitude, "longitude": longitude,
                 "radius_km": 50.0, "built": 2002, "place": "X"}
        try:
            coarse = EARTHQUAKE.validate_subject(given)
        except ValueError:
            continue           # not a place this protocol writes cover for
        exact = dict(coarse, latitude=latitude, longitude=longitude)
        try:
            at_the_door = engine.quote(peril_key="earthquake", subject=exact,
                                       limit=100_000.0, term_days=365.0, book=[])
            on_the_grid = engine.quote(peril_key="earthquake", subject=coarse,
                                       limit=100_000.0, term_days=365.0, book=[])
        except Exception:
            continue
        sampled += 1
        worst = max(worst, abs(at_the_door.premium - on_the_grid.premium)
                    / max(at_the_door.premium, 1e-9))
    assert sampled >= 8, f"only {sampled} coordinates priced; the sample is too thin"
    assert worst < 0.005, f"the worst premium moved {worst * 100:.3f}%"


def test_a_named_place_is_already_on_the_grid() -> None:
    """The offered locations are province and district centres, written to two
    places, so choosing one and typing its coordinate agree."""
    named = EARTHQUAKE.validate_subject({"location": "IST-KADIKOY",
                                         "radius_km": 50.0, "built": 2002})
    for key in ("latitude", "longitude"):
        assert round(named[key], PLACE_PLACES) == named[key], named
