""""Nothing matched." is an answer. It was said before there was one.

The place box asks two services. The catalogue in the page answers at once;
the geocoder that holds the streets answers over the network, with a 450 ms
debounce, a nine second timeout and one retry, so up to 18.9 seconds. The
empty state fired on the catalogue's answer alone, so somebody typing their
street read "Nothing matched. Cover is written in ..." while the service that
would have matched it was still in flight, and the list filled in behind the
sentence a few seconds later.

And a lookup that was refused never recorded that it had answered, so the
page could not tell "no answer yet" from "answered, nothing". Both record it
now, which is what makes the waiting state end.
"""

from __future__ import annotations

import json
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PLACES = (SITE / "app" / "65-place-lookup.js").read_text(encoding="utf-8")
MAP = (SITE / "app" / "50-places-and-map.js").read_text(encoding="utf-8")
LANGS = ("tr", "es", "fr", "de", "ru", "ja")


def body_of(src: str, name: str) -> str:
    at = src.index(f"function {name}(")
    return src[at:src.index("\n}", at) + 2]


def test_the_waiting_state_comes_before_the_empty_one() -> None:
    said = body_of(PLACES, "renderResults")
    waiting = said.index('t("Still looking…")')
    empty = said.index('t("Nothing matched.")')
    assert waiting < empty, "the empty state still answers for the lookup"
    # The condition itself: a branch that cannot be taken is not a branch,
    # and `if (false && ...)` passed the first version of this test.
    bare = said.replace(" ", "")
    assert "if(!hits.length&&stillAsking(key,coordinate)){" in bare, (
        "the waiting branch is guarded by something else")


def test_what_counts_as_still_asking() -> None:
    said = body_of(PLACES, "stillAsking")
    assert "ADDR.query !== key" in said, "the street lookup"
    assert "WORLD.query !== key" in said, "the city lookup"
    assert "!link.live" in said, "offline, nothing is out"
    assert "coordinate" in said, "a coordinate is answered in the page"


def refusal_handler(src: str, name: str) -> str:
    """The second handler of the lookup's promise: what runs when it fails."""
    said = body_of(src, name)
    bare = said.replace(" ", "")
    at = bare.index("},function(){")
    # Map the position back through the un-stripped text.
    kept = 0
    for i, ch in enumerate(said):
        if kept == at:
            return said[i:]
        if ch != " ":
            kept += 1
    raise AssertionError(f"{name} has no refusal handler")


def test_a_refused_lookup_records_that_it_answered() -> None:
    """Otherwise the waiting state never ends."""
    for src, name, field in ((MAP, "searchAddress", "ADDR"),
                             (PLACES, "searchWorld", "WORLD")):
        refusal = refusal_handler(src, name)
        assert f"{field}.query" in refusal, f"{name} does not record a refusal"
        assert f"{field}.hits" in refusal, name
        assert "renderResults(key)" in refusal, f"{name} does not redraw on a refusal"


def test_both_sequence_numbers_are_still_honoured() -> None:
    """A refusal for an older query must not answer for the current one."""
    for src, name, field in ((MAP, "searchAddress", "ADDR"),
                             (PLACES, "searchWorld", "WORLD")):
        refusal = refusal_handler(src, name).replace(" ", "")
        assert f"seq!=={field}.seq" in refusal, name


def test_the_waiting_state_is_translated() -> None:
    for lang in LANGS:
        book = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        said = book.get("Still looking…")
        assert said and said != "Still looking…", lang
