"""Answering a question from what a source published.

The protocol settles policies by pointing a condition at a primary source. The
open resolver does the same thing with nothing staked on the answer, so these
hold the part that decides what a reader is told: which record was picked out
of many, what happens when the source has nothing to say, and the difference
between "no" and "we could not ask".

Every case here is given its records rather than fetching them, so what is
tested is the reading and not the network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clause.protocol import ask

NOW = 1_790_600_000.0


def quake_row(mag: float, lat: float, lon: float, *, at: float = NOW - 3600,
              id_: str = "x", place: str = "somewhere") -> dict:
    return {"id": id_, "magnitude": mag, "latitude": lat, "longitude": lon,
            "at": at, "place": place, "depth_km": 10.0,
            "url": f"https://earthquake.usgs.gov/{id_}"}


# Istanbul, and a point about 80 km east of it.
IST = (41.01, 28.98)
EAST = (41.01, 29.93)


def test_an_event_inside_the_radius_and_over_the_line_is_found() -> None:
    a = ask.quake([quake_row(5.4, *EAST)], latitude=IST[0], longitude=IST[1],
                  radius_km=100, magnitude=5.0, place="Istanbul", retrieved_at=NOW, now=NOW)
    assert a.verdict is True
    assert a.reading == 5.4
    assert a.unit == "Mw"
    assert a.source == "USGS"
    assert a.url.endswith("/x"), "the answer does not link to the record it was read from"
    assert 70 < a.detail["distance_km"] < 90


def test_an_event_just_outside_the_radius_is_not_counted() -> None:
    """The radius is the question, so a near miss is a no and says so.

    Written with a real distance rather than a made up one: the point used
    here is about 80 km from Istanbul, so a 50 km question must miss it and a
    100 km question must find it. A test that used the same coordinates for
    both would pass whatever the distance code did.
    """
    near = ask.quake([quake_row(6.0, *EAST)], latitude=IST[0], longitude=IST[1],
                     radius_km=50, magnitude=5.0, retrieved_at=NOW, now=NOW)
    far = ask.quake([quake_row(6.0, *EAST)], latitude=IST[0], longitude=IST[1],
                    radius_km=100, magnitude=5.0, retrieved_at=NOW, now=NOW)
    assert near.verdict is False and near.reading is None
    assert far.verdict is True and far.reading == 6.0


def test_the_largest_qualifying_event_is_the_one_reported() -> None:
    """Not the first in the list and not the nearest.

    A reader who is told M5.1 when the source also recorded M6.2 inside the
    same circle concludes the protocol missed the real event, and they are
    right to: the figure they would look up is the big one.
    """
    a = ask.quake(
        [quake_row(5.1, 41.2, 29.0, id_="small"),
         quake_row(6.2, 41.3, 29.1, id_="big"),
         quake_row(5.9, 41.05, 28.99, id_="near")],
        latitude=IST[0], longitude=IST[1], radius_km=100, magnitude=5.0,
        retrieved_at=NOW, now=NOW)
    assert a.reading == 6.2
    assert a.detail["record_id"] == "big"
    assert a.detail["events_in_radius"] == 3


def test_a_record_that_cannot_be_read_is_not_a_record_of_nothing() -> None:
    """A malformed row is skipped, and the good one beside it still answers."""
    a = ask.quake(
        [{"magnitude": "not a number", "latitude": 41.0, "longitude": 29.0},
         {"latitude": 41.0},
         quake_row(5.5, *EAST, id_="real")],
        latitude=IST[0], longitude=IST[1], radius_km=100, magnitude=5.0,
        retrieved_at=NOW, now=NOW)
    assert a.verdict is True and a.detail["record_id"] == "real"


def test_a_question_outside_what_can_be_asked_is_refused() -> None:
    for kw in ({"radius_km": 0.5}, {"radius_km": 5000}, {"magnitude": -1}, {"magnitude": 12}):
        base = dict(latitude=IST[0], longitude=IST[1], radius_km=100.0, magnitude=5.0)
        base.update(kw)
        with pytest.raises(ask.BadQuestion):
            ask.quake([], **base)


def test_the_answer_carries_the_line_it_was_decided_on() -> None:
    """A verdict without its figure beside it is an opinion in a number's coat."""
    a = ask.quake([quake_row(5.4, *EAST)], latitude=IST[0], longitude=IST[1],
                  radius_km=100, magnitude=5.0, retrieved_at=NOW, now=NOW)
    d = a.as_dict()
    for key in ("question", "verdict", "reading", "unit", "threshold",
                "source", "url", "measured_at", "retrieved_at"):
        assert key in d, f"the answer does not say {key}"
    assert d["threshold"] == 5.0 and d["reading"] == 5.4


# -- the weather feed ---------------------------------------------------------

WEATHER = [
    {"place": "Zonguldak", "latitude": 41.46, "longitude": 31.79,
     "rain_mm": 81.2, "gust_kmh": 42.8, "sky": "thunderstorm"},
    {"place": "Düzce", "latitude": 40.84, "longitude": 31.16,
     "rain_mm": 3.0, "gust_kmh": 71.0, "sky": "rain"},
]


def test_wind_and_rain_are_read_from_their_own_fields() -> None:
    wind = ask.weather(WEATHER, place="Düzce", measure="wind", threshold=60,
                       retrieved_at=NOW, now=NOW)
    rain = ask.weather(WEATHER, place="Düzce", measure="rain", threshold=60,
                       retrieved_at=NOW, now=NOW)
    assert wind.verdict is True and wind.reading == 71.0 and wind.unit == "km/h"
    assert rain.verdict is False and rain.reading == 3.0 and rain.unit == "mm"


def test_the_place_is_matched_whatever_case_it_was_typed_in() -> None:
    a = ask.weather(WEATHER, place="zonguldak", measure="rain", threshold=50,
                    retrieved_at=NOW, now=NOW)
    assert a.verdict is True
    assert a.detail["place"] == "Zonguldak", "the answer should name the place as the source does"


def test_a_place_the_source_does_not_publish_is_refused_not_answered() -> None:
    with pytest.raises(ask.BadQuestion):
        ask.weather(WEATHER, place="Kayseri", measure="rain", threshold=10)


def test_a_missing_figure_is_not_a_reading_of_zero() -> None:
    """The worst answer is a confident wrong one.

    A place the source published with no gust figure is not a place where the
    wind did not blow, and answering "no" on it would be wrong in exactly the
    direction that costs somebody a payout.
    """
    rows = [{"place": "Rize", "rain_mm": 12.0, "gust_kmh": None}]
    with pytest.raises(ask.BadQuestion):
        ask.weather(rows, place="Rize", measure="wind", threshold=10)
    # And the field that is there still answers.
    assert ask.weather(rows, place="Rize", measure="rain", threshold=10).verdict is True


# -- the delays feed ----------------------------------------------------------

DELAYS = [
    {"airport": "IST", "count": 7, "max_minutes": 120, "average_minutes": 66,
     "flights": [{"flight": "TK1"}, {"flight": "TK2"}]},
    {"airport": "AYT", "count": 2, "max_minutes": 51, "average_minutes": 48},
]


def test_an_airport_is_answered_from_its_own_row() -> None:
    a = ask.delays(DELAYS, airport="ist", count=5, retrieved_at=NOW, now=NOW)
    assert a.verdict is True and a.reading == 7.0
    assert a.detail["worst_minutes"] == 120
    assert a.detail["flights"] == ["TK1", "TK2"]


def test_an_airport_the_feed_does_not_name_had_nothing_late_enough() -> None:
    """Which is a real answer, and a different one from "we could not ask".

    This feed carries every airport it saw with a departure 45 minutes late or
    worse, so an airport missing from it had none. That is worth saying as a
    no rather than as a refusal, and it is only true because of how this
    particular feed is built.
    """
    a = ask.delays(DELAYS, airport="ESB", count=1, retrieved_at=NOW, now=NOW)
    assert a.verdict is False and a.reading == 0.0
    assert a.detail["airports_reporting"] == 2


def test_something_that_is_not_an_airport_code_is_refused() -> None:
    for bad in ("I", "ISTANBUL", "1ST", ""):
        with pytest.raises(ask.BadQuestion):
            ask.delays(DELAYS, airport=bad, count=1)


# -- staleness ----------------------------------------------------------------


def test_an_answer_from_a_feed_that_has_gone_quiet_says_so() -> None:
    """A stale feed answers about a world that has moved on.

    The answer is still given, because the figure it was read from is still a
    fact about when it was read; what is added is that the reader can see the
    clock on it.
    """
    fresh = ask.quake([quake_row(5.4, *EAST)], latitude=IST[0], longitude=IST[1],
                      radius_km=100, magnitude=5.0, retrieved_at=NOW, now=NOW)
    old = ask.quake([quake_row(5.4, *EAST)], latitude=IST[0], longitude=IST[1],
                    radius_km=100, magnitude=5.0,
                    retrieved_at=NOW - ask.STALE_AFTER_SECONDS - 60, now=NOW)
    assert fresh.stale is False
    assert old.stale is True
    # Without a clock on either side there is nothing to compare, and guessing
    # would mark every answer stale or none of them.
    assert ask.quake([], latitude=IST[0], longitude=IST[1], radius_km=100,
                     magnitude=5.0).stale is False


def test_nothing_here_stakes_or_pays_anything() -> None:
    """The one thing this must not become.

    What separates insurance from a wager is that the buyer has something
    actually at risk, and this protocol's own contract refuses cover where
    they do not. A question with money on it has nothing behind it, so the
    resolver carries no stake, no pool, no payout and no score.

    Read from the module's own syntax rather than by looking for words in the
    text, because the module has to be free to say in prose exactly what it
    will not do. Written the other way first, with a regular expression over
    the lines, and it passed with a stake and a payout added to the answer:
    the pattern was escaped twice and matched nothing at all.
    """
    import ast

    source = (Path(__file__).resolve().parent.parent
              / "clause" / "protocol" / "ask.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)

    written = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            written.append(node.id)
        elif isinstance(node, ast.Attribute):
            written.append(node.attr)
        elif isinstance(node, ast.arg):
            written.append(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            written.append(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            written.append(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                written.append(node.value)
    assert len(written) > 100, "the module is not being read; this test proves nothing"

    # Written out rather than stemmed. "bet" is the start of "between" and
    # "better", so a prefix match would refuse ordinary code; and a bare
    # \bwagers?\b does not catch a parameter called "wagered", which is what
    # the first version of this let through.
    banned = ("stake", "stakes", "staked", "staking",
              "wager", "wagers", "wagered", "wagering",
              "bet", "bets", "betting", "bettor", "bettors",
              "payout", "payouts", "odds", "pool", "pools",
              "wallet", "wallets", "score", "scores", "scoring")
    found = sorted({w for text in written for w in banned
                    if re.search(rf"\b{w}\b", text, re.I)})
    assert not found, f"the resolver deals in these, and it must not: {found}"


def test_the_window_is_part_of_the_question() -> None:
    """"No earthquake near you" is not a fact about the place.

    It is a fact about the last few days of it, and the source only ever knew
    the latter. An answer that leaves the window out invites a reader to
    believe a "no" much further than it goes. Found by asking about the
    epicentre of a real M5.3 and being told no: the event was four days old
    and the feed being read covered one day, and nothing in the answer said so.
    """
    a = ask.quake([quake_row(5.4, *EAST)], latitude=IST[0], longitude=IST[1],
                  radius_km=100, magnitude=5.0, place="Istanbul", window="day",
                  retrieved_at=NOW, now=NOW)
    assert "past day" in a.question
    assert a.detail["window"] == "day"

    b = ask.quake([], latitude=IST[0], longitude=IST[1], radius_km=100,
                  magnitude=5.0, place="Istanbul", window="week")
    assert "past week" in b.question, "a no must say how far back it looked"
    assert b.detail["window"] == "week"

    with pytest.raises(ask.BadQuestion):
        ask.quake([], latitude=IST[0], longitude=IST[1], radius_km=100,
                  magnitude=5.0, window="year")


def test_the_form_is_only_offered_what_can_be_answered() -> None:
    """A chip that refuses every question is worse than one never drawn.

    The list said "flight" for an afternoon after the flight question became a
    question about an airport's departures. A page drawing its form from this
    would have offered a shape the protocol had stopped being able to answer,
    and the reader would have concluded it cannot read flights at all.
    """
    kinds = {shape["kind"] for shape in ask.answerable()}
    answering = {name for name in dir(ask)
                 if not name.startswith("_") and callable(getattr(ask, name))
                 and name not in ("answerable", "Answer", "BadQuestion")}
    # Every shape offered is answered by a function of that name, or by the
    # weather one, which answers two of them from its own two fields.
    for kind in kinds:
        assert kind in answering or kind in ask.WEATHER_FIELDS, (
            f"the form offers {kind!r} and nothing answers it"
        )
    assert kinds == {"quake", "wind", "rain", "delays"}
    for shape in ask.answerable():
        assert "threshold" in shape["defaults"], f"{shape['kind']} has no line to start from"
        assert shape["asks"] in ("point", "place", "airport")
