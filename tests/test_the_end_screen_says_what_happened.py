"""The last screen, when nothing was bought.

When the protocol cannot be reached the page still walks the flow, because
the flow is worth seeing, and the paragraph it writes says so plainly:
"Nothing was bought." The heading above that paragraph, the status lamp
beside it and the green seal above both are written into the markup as "You
are covered. There is nothing else to do." and "Armed on chain", and only
the two paths that did buy something ever replaced them.

So the one path that reaches this screen having bought nothing asserted a
policy in its heading, wore the tick for it, and contradicted itself three
lines below in the one paragraph it did set.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
DOCS = (SITE / "app" / "80-documents.js").read_text(encoding="utf-8")
HTML = (SITE / "index.html").read_text(encoding="utf-8")
CSS = (SITE / "styles" / "60-flow.css").read_text(encoding="utf-8")
LANGS = ("tr", "es", "fr", "de", "ru", "ja")
HEADING = "Nothing was bought: this page cannot reach the protocol."


def body_of(name: str) -> str:
    at = DOCS.index(f"function {name}(")
    return DOCS[at:DOCS.index("\n}", at) + 2]


def test_the_markup_still_defaults_to_the_bought_wording() -> None:
    """Which is why every path has to set it: this is the thing being guarded."""
    assert 'id="done-title" data-i18n>You are covered.' in HTML
    assert 'id="done-state" data-i18n>Armed on chain' in HTML


def test_the_offline_screen_writes_its_own_heading_and_lamp() -> None:
    said = body_of("demoDone")
    assert HEADING in said
    assert 't("Not connected")' in said
    assert '$("done-title").removeAttribute("data-i18n")' in said, (
        "left marked for translation, the next language change writes the "
        "bought wording back over it")
    assert '$("done-state").removeAttribute("data-i18n")' in said


def test_it_does_not_wear_the_seal_of_a_policy() -> None:
    assert '$("s5").classList.add("unbought")' in body_of("demoDone")
    assert ".done.unbought .seal" in CSS
    assert ".done.unbought .lamp" in CSS
    assert "animation:none" in CSS[CSS.index(".done.unbought .lamp"):][:120]


def test_the_two_that_did_buy_something_take_it_off_again() -> None:
    """A tab that walked the flow offline and then came back must not keep it."""
    for name in ("showDone", "showApplied"):
        assert '$("s5").classList.remove("unbought")' in body_of(name), name


def test_the_heading_is_translated_everywhere() -> None:
    for lang in LANGS:
        book = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        said = book.get(HEADING)
        assert said and said != HEADING, lang
        assert not re.findall(r"\{\w+\}", said), (lang, "no placeholders in this one")
