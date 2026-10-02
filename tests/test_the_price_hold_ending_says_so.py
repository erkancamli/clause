"""A held price lasts ten minutes. The contract takes longer to read.

contractKey() carries the lock's id while a quote is held and the live
premium once it is not, so when the hold ends the key changes, renderContract
replaces the text with "Preparing the contract…" and takes the acceptance
back. That is right: the contract is written on a price, and the price is no
longer the one in it.

What was wrong is that it happened in silence. A buyer reading the longest
text in the product for more than ten minutes looked up to find the tick
gone and the button back to "Read and accept the contract", with nothing
saying why but a caption on the price bar. The comment above contractKey
describes this failure as fixed; the lock narrowed the window from every
penny to every ten minutes rather than closing it.

Said now, and only where the buyer did not cause it: every other thing that
changes the contract is something they just did.
"""

from __future__ import annotations

import json
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
MAP = (SITE / "app" / "50-places-and-map.js").read_text(encoding="utf-8")
HTML = (SITE / "index.html").read_text(encoding="utf-8")
LANGS = ("tr", "es", "fr", "de", "ru", "ja")
NOTE = ("The price was held for ten minutes and that time is up, so the contract "
        "has been drawn again at today's price. Read it and accept it again.")


def body_of(name: str) -> str:
    at = MAP.index(f"function {name}(")
    return MAP[at:MAP.index("\n}", at) + 2]


def test_there_is_somewhere_to_say_it() -> None:
    assert 'id="accept-note"' in HTML
    assert 'role="status"' in HTML[HTML.index('id="accept-note"') - 60:
                                   HTML.index('id="accept-note"') + 60], (
        "a line that appears without being announced is not said to a screen reader")


def test_it_is_said_when_the_tick_is_taken_back() -> None:
    said = body_of("renderContract")
    assert NOTE in said
    taken = said.index('$("accept").checked=false')
    assert said.index("var undone=") < taken, (
        "whether it was ticked has to be read before it is unticked")
    assert "onlyThePriceMoved(CONTRACT.key,key)" in said.replace(" ", "")


def test_it_is_not_said_when_the_buyer_changed_something() -> None:
    """Choosing another company or another cover changes the contract too,
    and the buyer who did it does not need telling."""
    said = body_of("onlyThePriceMoved")
    assert "slice(0,-1)" in said.replace(" ", ""), (
        "every answer but the price is compared")
    key = body_of("contractKey")
    assert key.rstrip().rstrip("}").rstrip().endswith("priced().premium]);"), (
        "the price is no longer the last element, so the comparison is wrong")


def test_the_tick_takes_the_note_away() -> None:
    at = MAP.index('$("accept").addEventListener')
    said = MAP[at:at + 400]
    assert "accept-note" in said and "hidden=true" in said


def test_it_is_translated_everywhere() -> None:
    for lang in LANGS:
        book = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        said = book.get(NOTE)
        assert said and said != NOTE, lang
