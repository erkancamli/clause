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
