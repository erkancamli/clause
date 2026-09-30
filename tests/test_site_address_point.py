"""The address is written on one screen and the policy measures on another.

A buyer of home cover picks a place on the second step, and the list there
offers provinces, because the same list serves a drought policy that settles at
a named station. Pick "Adana" and the point the policy measures is the middle
of Adana. Type a street in Ceyhan on the next screen, forty-four kilometres
east, and nothing moves: the address is kept as text, and `flow.subject` is
still where it was.

Driven in a browser against the protocol, that purchase reaches the signing
step with the address reading Ceyhan and the measurement at Adana's centre. The
two are not the same risk: the model puts intensity 7 at Adana's centre once in
581 years and at Ceyhan once in 305, and the expected loss on the same cover is
144.76 against 224.37. The premium runs the other way, 456.74 against 380.24,
because the middle of Adana is where the book is concentrated and capital there
costs more, so this is not a story about underpaying and must not be told as
one. What it does is measure the policy forty-four kilometres from the building
it is written on.

The address is looked up now and what came back is put in front of the buyer
with the distance, and one press moves the measurement. It is never moved on
its own: a geocoder answers a street that does not exist with a street that
does, and "Ceyhan Caddesi 14, Ceyhan" comes back as an address in Ankara, 398
kilometres away, without hesitating.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import page_assembled

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "site" / "app"
PAGE = page_assembled()


def _part(name: str) -> str:
    return (APP / name).read_text(encoding="utf-8")


def test_the_address_is_looked_up_and_the_distance_is_said() -> None:
    body = _part("70-what-is-at-risk.js")
    assert "function lookUpTheAddress(" in body, "nothing looks the address up"
    assert "/api/geocode?q=" in body, "the address is not turned into a point"
    assert "The policy measures at {place}, which is {km} km from the address above." in body, (
        "the distance between the two is not said"
    )
    assert 'id="addr-far"' in PAGE, "the page has nowhere to say it"


def test_typing_an_address_never_moves_the_measurement_on_its_own() -> None:
    """The whole reason this is an offer and not an action.

    "Ceyhan Caddesi 14, Ceyhan" is answered with an address in Ankara, 398 km
    away, by a geocoder that has no way to say it is unsure. A policy moved
    there without being asked would be a worse defect than the one this fixes.
    """
    body = _part("70-what-is-at-risk.js")
    moves = [m for m in re.finditer(r"setPoint\s*\(", body)]
    assert moves, "nothing moves the measurement at all"
    for m in moves:
        before = body[max(0, m.start() - 400) : m.start()]
        assert "addEventListener" in before, (
            "the measurement is moved somewhere other than from a press"
        )


def test_the_offer_is_quiet_when_the_two_are_the_same_building() -> None:
    """A buyer who searched their own street does not need telling about it."""
    body = _part("70-what-is-at-risk.js")
    assert re.search(r"if\s*\(\s*away\s*<\s*1\s*\)", body), (
        "there is no distance under which the notice stays out of the way"
    )


def test_every_language_can_say_it() -> None:
    import json

    said = ["The policy measures at {place}, which is {km} km from the address above.",
            "Measure at this address", "Found: {what}", "the place you chose"]
    for path in sorted((ROOT / "site" / "i18n").glob("*.json")):
        book = json.loads(path.read_text(encoding="utf-8"))
        book = book.get("strings", book)
        for line in said:
            assert line in book, f"{path.name} has no line for {line!r}"
