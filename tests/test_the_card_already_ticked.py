"""Going back to the first question and tapping the same card again.

choosePeril cleared the subject, the radius, the floor area and the cover on
every tap, and cleared the place and the search box only when the answer had
actually changed. So tapping the card that was already ticked left the buyer
looking at their own address in the search box, an empty result list (the
query equalled the place it had just deleted), no pin on the map, and a
button reading "Choose a place". The only way out was to edit the text.

The flow says of itself that "Going back to a question already answered is
free in both directions". It is now: the tap changes nothing.

A renewal is the one case that must still start the declaration again, and
it is the case where the peril usually has not changed, so renewFrom says so
for itself.
"""

from __future__ import annotations

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PLACES = (SITE / "app" / "65-place-lookup.js").read_text(encoding="utf-8")


def body_of(name: str) -> str:
    at = PLACES.index(f"function {name}(")
    return PLACES[at:PLACES.index("\n}", at) + 2]


CHOOSE = body_of("choosePeril")


def changed_branch() -> str:
    """What runs only when the answer actually changed."""
    at = CHOOSE.index("if(key!==flow.peril||!flow.chosen){")
    return CHOOSE[at:CHOOSE.index("\n  }", at)]


def always() -> str:
    """What runs on every tap, including one on the card already ticked."""
    at = CHOOSE.index("\n  }", CHOOSE.index("if(key!==flow.peril||!flow.chosen){"))
    return CHOOSE[at:]


def test_nothing_the_buyer_answered_is_cleared_on_a_second_tap() -> None:
    kept = ["flow.subject=null", "flow.size=null", "flow.radius=50",
            "flow.limit=PERILS[key].presets[1]", "flow.grid=null",
            "flow.placeCountry=null", "flow.asset=null"]
    outside = [line for line in kept if line in always()]
    assert not outside, f"these still run on a tap that changed nothing: {outside}"


def test_they_are_all_still_cleared_when_the_answer_changes() -> None:
    """A flat in Kadikoy is not what is at risk on a flight."""
    changed = changed_branch()
    for line in ("flow.subject=null", "flow.size=null", "flow.radius=50",
                 "flow.limit=PERILS[key].presets[1]", "flow.place=null"):
        assert line in changed, line
    assert 'if($("place"))$("place").value="";' in changed, (
        "the box and the place are cleared together or not at all")


def test_the_place_and_the_box_are_never_cleared_apart() -> None:
    """The two halves of the bug: one cleared, the other left behind."""
    clears_place = "flow.place=null" in always()
    clears_box = '$("place").value=""' in always()
    assert clears_place == clears_box, (
        "clearing one and not the other is the state the buyer was left in")


def test_a_renewal_still_starts_the_declaration_again() -> None:
    renew = body_of("renewFrom")
    at = renew.index("choosePeril(key)")
    assert "flow.chosen=false" in renew[:at], (
        "a renewal of the cover already on screen would inherit it")


def test_the_tap_still_moves_to_the_second_question() -> None:
    assert "goStep(2)" in always()
    assert "flow.peril=key" in always() and "flow.chosen=true" in always()
