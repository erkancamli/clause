""""Check the pin, and drag it if it is not quite right."

Said as soon as the browser answered, which is before there is a pin: the
address behind it takes a call with a nine second timeout and one retry, and
setPoint and centreMap only run in that call's handlers. So for up to
eighteen seconds the page asked the buyer to check something that was not on
the screen, and if the call failed it said "Found" over bare coordinates.

Said now where the pin is put, in both of that call's outcomes, because the
failing one still places the pin.
"""

from __future__ import annotations

import json
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PLACES = (SITE / "app" / "50-places-and-map.js").read_text(encoding="utf-8")
LANGS = ("tr", "es", "fr", "de", "ru", "ja")
WAITING = "Found where you are. Reading the address…"
PINNED = "Check the pin, and drag it if it is not quite right."


def body_of(name: str) -> str:
    at = PLACES.index(f"function {name}(")
    return PLACES[at:PLACES.index("\n}", at) + 2]


LOCATE = body_of("locateMe")


def test_the_pin_is_mentioned_only_after_it_is_placed() -> None:
    """Where it is said, rather than where it sits in the file: it lives in a
    helper now, which the file holds before the call that runs it."""
    assert LOCATE.count(PINNED) == 1, "said in more than one place"
    helper = LOCATE[LOCATE.index("function pinned(){"):]
    helper = helper[:helper.index("\n    }") + 6]
    assert PINNED in helper, "it is not inside the helper that runs after the pin"
    before = LOCATE[:LOCATE.index("function pinned(){")]
    assert PINNED not in before
    assert "setPoint(" not in before, "nothing places the pin before the helper exists"


def test_both_outcomes_of_the_address_call_place_it_and_say_so() -> None:
    """The failing one puts the pin on bare coordinates, which still needs
    checking."""
    after = LOCATE[LOCATE.index("api(\"/api/reverse"):]
    assert after.count("pinned()") == 2, after.count("pinned()")
    assert after.count("setPoint(") == 2
    assert after.count("centreMap(16)") == 2


def test_the_wait_is_said_in_the_meantime() -> None:
    assert WAITING in LOCATE
    assert LOCATE.index(WAITING) < LOCATE.index(PINNED)


def test_the_accuracy_survives_into_the_later_message() -> None:
    """It comes off the browser's answer, which is out of scope by then."""
    assert "var metres=" in LOCATE
    assert "{m:f0.format(metres)}" in LOCATE


def test_the_wait_is_translated_everywhere() -> None:
    for lang in LANGS:
        book = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        said = book.get(WAITING)
        assert said and said != WAITING, lang
