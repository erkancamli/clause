"""Walking the purchase, and the two things that walk found.

The flow was never driven end to end from a test. It was driven from a
browser, peril by peril, by answering each step through its own controls, and
the Continue button turned out to be the instrument: when it is blocked it
says what is missing, so the page itself says where a buyer would stop.

Four of the five perils reached the sign-in. The fifth stopped, and what
stopped it was the page's own doing.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")


def _function(name: str) -> str:
    at = PAGE.index(f"function {name}(")
    return PAGE[at : PAGE.index("\n}\n", at)]


def test_a_flight_number_is_only_invented_where_an_airline_is_known() -> None:
    """Two airports chosen one at a time do not name an airline.

    A route key names its airline first and the two ends after it, TK-IST-LHR.
    Choosing the ends separately makes the subject SAW-ESB, and taking the
    first part either way put an airport code where an airline code goes: the
    box was filled with SAW1979, which no flight number can be. The page then
    asked for a flight number over a field that already looked answered, and
    said nothing about what was wrong with it. A buyer choosing their own two
    airports could not get past the second step.

    Where the airline is not known the box is left empty, and the placeholder
    shows the shape of the thing to type.
    """
    body = _function("flightDefaults")
    assert "flightNumber" in body, "this is not the function that fills the number"

    # Whatever it does, it cannot take the first part of any subject at all.
    naive = re.search(r"flightNumber\s*=\s*\w+\.subject\.split\([\"']-[\"']\)\[0\]", body)
    assert not naive, "the first part of the subject is not an airline code"

    # It has to satisfy itself that the subject names one: three parts, and
    # the first of them two letters, which is what an airline code is.
    assert "length===3" in body.replace(" ", ""), "the subject's shape is not checked"
    assert re.search(r"/\^\[A-Za-z\]\{2\}\$/", body), "the airline code's shape is not checked"


def test_the_two_airport_subject_really_does_lack_an_airline() -> None:
    """The premise of the fix above, held against the code that builds it.

    If setAirport ever starts writing a three part subject, the guard becomes
    dead weight and should be revisited rather than left to rot.
    """
    body = _function("setAirport")
    assert re.search(r"subject\s*=.*flightFrom\s*\+\s*[\"']-[\"']\s*\+.*flightTo", body), (
        "the subject for two chosen airports is no longer FROM-TO"
    )


def test_nothing_is_priced_until_there_is_something_to_price() -> None:
    """The protocol was asked three times for a price it always refuses.

    A flight without its number came back "that cover cannot be priced" every
    time, which is the right answer to the wrong question: the page knew the
    subject was incomplete, because the same four checks are what its Continue
    button reads to say what is missing.

    Nothing waits on this. The page's own figure is already on the screen, and
    the protocol replaces it when there is a whole subject to send.
    """
    body = _function("refreshQuote")
    guard = body.index("flightReady()")
    call = body.index('api("/api/offers')
    assert guard < call, "the readiness check comes after the request it is meant to prevent"
    for check in ("flightReady()", "quakeReady()", "stormReady()", "carReady()"):
        assert check in body[:call], f"{check} is not consulted before asking for a price"


def test_every_peril_can_still_be_started() -> None:
    """The five the flow walks, so a peril quietly dropped fails here.

    Driven in a browser rather than read: each of these reached the sign-in
    from the first screen, in Turkish, by answering the steps.
    """
    picks = set(re.findall(r'data-peril="(\w+)"', PAGE))
    assert {"quake", "storm", "car", "drought", "flight"} <= picks, picks


def test_a_refused_reading_is_not_a_reading_still_coming() -> None:
    """The button told a buyer to wait for something that had already arrived.

    Storm and vehicle cover are written only within 60 km of a Turkish
    provincial centre. Outside it the protocol answers 400 with a sentence
    saying exactly that, the page prints the sentence under the map, and the
    Continue button said "Still reading the place" -- at four seconds, at
    twelve, at thirty, and for as long as anybody cared to watch. Measured in
    a browser with the protocol's own refusal served back to the page.

    One sentence covered two states, and only one of them ends by itself. The
    refusal is a state of its own now and the button names the way out of it.
    """
    # The button's words are decided here; setNextLabel only paints them.
    body = _function("whatIsMissing")
    refused = body.index("Choose another place")
    waiting = body.index("Still reading the place")
    assert refused < waiting, (
        "the button still offers to wait before it notices the reading was refused")

    # All three readings, because all three can come back refused: the grid
    # outside Türkiye, the wind record, the rainfall record.
    said = body[:waiting]
    for flag in ("gridError", "stormError", "vehicleError"):
        assert flag in said, f"a refused {flag} still reads as a reading in flight"


def test_a_flight_is_inside_the_flight_by_construction() -> None:
    """The one confirmation on that step was a tautology.

    "It is inside the area measured" is a real question for a home, a car or a
    field, and the page answers it for three of the five perils by
    construction: the place the buyer chose is where the home stands. For a
    flight the area measured is the flight -- areaSentence() says so in those
    words, "the flight itself" -- so the buyer was asked to confirm that their
    flight is inside their flight. Measured at 390px: every other field on the
    step arrived answered, and this was the only thing blocking Continue.

    Drought is the one that still asks, and should. The field can be
    kilometres from the station that settles it, the sentence names that
    distance, and basis risk lives in it.
    """
    body = _function("renderInterest")
    line = next(l for l in body.splitlines() if "insideTouched" in l and "inside=true" in l)
    assert '"drought"' in line, "the field is no longer the one peril that has to be confirmed"
    for peril in ('"quake"', '"storm"', '"car"', '"flight"'):
        assert peril not in line, f"{peril} is named again instead of being covered by construction"


def test_every_peril_offers_a_name_for_the_thing_at_risk() -> None:
    """Four came with one and drought came with an empty required box.

    A flat in Kadıköy, a house, my car, one flight and what missing it costs:
    every peril but drought filled that field, so its buyer met a blank where
    the others met something to read and correct. It is named after the crop
    already selected and the place already chosen, like the rest.
    """
    body = _function("renderInterest")
    for peril in ("quake", "storm", "car", "flight", "drought"):
        assert re.search(rf'!interest\.what&&flow\.peril==="{peril}"', body), (
            f"{peril} offers no name for what is at risk")
