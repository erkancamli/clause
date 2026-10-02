"""What the third question says when the country is the answer.

Two findings in one branch, both measured by walking the flow.

A US earthquake buyer: territory includes the United States because the
USGS publishes the curves, so a US city shows as available, is selectable,
and passes the second question. The third asked for the floor area and
refused it, because the rebuild cost schedule covers ten countries and not
that one, so the button read "Check the size above" about a number that was
correct, pointing at a field that could not be fixed. The real answer, that
no carrier is registered there, was the last test in the branch and the
size check short-circuited it every time.

A flight buyer, anywhere: COVERAGE starts null, so coverFor() answers null
for every country and licensing() read that as "No licensed carrier is
registered to write cover in Türkiye yet". For a home the empty address
fields hold the buyer back, but a flight has every field filled three taps
from the home page, so it met a red "Nobody registered" panel and a dead
"Cannot be written" button for as long as the health check and the
compliance call took, up to 18.9 seconds with the retries, and then cleared
itself without the buyer touching anything.

So the licensing question is asked first where it can be answered, and not
answered at all where it cannot: not knowing is its own state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
FLOW = (SITE / "app" / "60-cover-flow.js").read_text(encoding="utf-8")
RISK = (SITE / "app" / "70-what-is-at-risk.js").read_text(encoding="utf-8")
LANGS = ("tr", "es", "fr", "de", "ru", "ja")


def body_of(src: str, name: str) -> str:
    at = src.index(f"function {name}(")
    return src[at:src.index("\n}", at) + 2]


MISSING = body_of(FLOW, "whatIsMissing")
RULING = body_of(FLOW, "localRuling")


def step_three() -> str:
    """The branch of whatIsMissing that answers the third question."""
    at = MISSING.index("if(flow.step===RISK_STEP){")
    return MISSING[at:]


# -- the country first, where the country is the answer --------------------

def test_the_licence_is_asked_before_the_size() -> None:
    said = step_three()
    licence = said.index("licensing(riskCountry())")
    assert licence < said.index("sizeOk()"), (
        "the size check short-circuits the real reason")
    assert licence < said.index('t("Check the size above")')


def test_it_is_only_asked_once_the_answer_is_in() -> None:
    """Otherwise it is the second finding, in a new place."""
    said = step_three()
    at = said.index("licensing(riskCountry())")
    guard = said[said.rindex("if(", 0, at):at]
    assert "coverageKnown()" in guard, guard
    assert "link.live" in guard, guard


# -- and not knowing is not a refusal --------------------------------------

def test_the_ruling_has_a_state_for_not_knowing_yet() -> None:
    """The condition itself, because a condition that cannot be true is a
    branch that is not there: `if(0&&!coverageKnown())` passed the first
    version of this test."""
    bare = RULING.replace(" ", "").replace("\n", "")
    assert "if(!coverageKnown())return{allowed:false,unknown:true," in bare, (
        "the wait is not guarded by whether the answer has arrived")
    at = RULING.index("coverageKnown()")
    assert RULING.index("licensing(code)") > at, (
        "licensing() reads an empty COVERAGE as nobody being registered")


def test_the_waiting_state_is_a_wait_on_the_button() -> None:
    said = step_three()
    assert 'ruling.unknown' in said
    assert said.index("ruling.unknown") < said.index('!ruling.allowed'), (
        "a refusal reached first is the refusal the buyer reads")
    assert 't("Checking the licence")' in said


def test_the_panel_waits_too() -> None:
    panel = RISK[RISK.index('var box=$("rule-note")'):]
    panel = panel[:panel.index("setNextLabel();")]
    assert "coverageKnown()" in panel
    assert panel.index("!coverageKnown()") < panel.index('t("Nobody registered")'), (
        '"Nobody registered" before the answer arrives is a different sentence')
    assert 't("Still checking")' in panel


def test_the_confirm_panel_does_not_call_it_refused() -> None:
    verdict = body_of(FLOW, "verdictHtml")
    assert "ruling.unknown" in verdict
    assert verdict.index("ruling.unknown") < verdict.index('t("Refused")')


def test_coverage_is_known_only_once_it_has_arrived() -> None:
    assert "COVERAGE!==null" in body_of(FLOW, "coverageKnown").replace(" ", "")


# -- in every language -----------------------------------------------------

def test_the_three_new_sentences_are_translated() -> None:
    new = ["Still checking",
           "Still checking which company is licensed to write this in {country}.",
           "Checking the licence"]
    for lang in LANGS:
        book = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        for english in new:
            said = book.get(english)
            assert said and said != english, (lang, english)
            assert re.findall(r"\{\w+\}", said) == re.findall(r"\{\w+\}", english), (lang, said)
