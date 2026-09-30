"""The page that points a question at a source.

The protocol settles policies by reading a primary source, and until this
page existed the only way to watch that happen was to buy cover and wait for
the weather. So the danger is not that the page looks wrong; it is that it
drifts into being something else. A question with money on it is a wager, and
what makes this protocol's cover insurance rather than a bet is that the buyer
has something actually at risk. These hold the page to being a reading.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import page_with_styles

ROOT = Path(__file__).resolve().parent.parent
PAGE = page_with_styles()

VIEW = PAGE[PAGE.index('<section class="view" id="view-ask">'):]
VIEW = VIEW[: VIEW.index("\n</section>")]
#: This page's whole script, from where its state is declared to where the
#: next page's begins.
SCRIPT = PAGE[PAGE.index("var ASK={"):]
SCRIPT = SCRIPT[: SCRIPT.index("function renderRules(")]
DRAW = SCRIPT[SCRIPT.index("function drawAskFields(){"):]
DRAW = DRAW[: DRAW.index("\nfunction form_chips")]


def test_the_page_is_reachable_and_named() -> None:
    assert '"/ask":"view-ask"' in PAGE, "the page is not routed"
    assert '<a href="#/ask" data-route="/ask"' in PAGE, "the page is not in the menu"
    assert VIEW.count("<h1") == 1, "a screen takes its name from its one first-level heading"
    assert 'if (route === "/ask") renderAskForm();' in PAGE, "the form is never drawn"


def test_the_form_is_drawn_from_what_the_protocol_says_it_can_answer() -> None:
    """Not from a list written into the page.

    A question shape the protocol stops being able to answer has to stop being
    offered by itself, or the page keeps a chip that refuses every question
    put through it, and a reader concludes the protocol cannot read that kind
    of source at all.
    """
    assert '"/api/ask/shapes"' in SCRIPT, "the page never asks what can be asked"
    for kept in ("ASK.shapes=", "ASK.places=", "ASK.airports="):
        assert kept in SCRIPT.replace(" ", ""), f"the page does not keep {kept}"
    # The chosen shape decides the fields, and its defaults fill them.
    assert "askShape(ASK.kind)" in DRAW, "the fields are not drawn from the protocol's answer"
    assert "shape.defaults" in DRAW, "the lines are not the protocol's own starting points"
    # The places and airports a question may name come from the source too.
    assert "ASK.places" in DRAW and "ASK.airports" in DRAW


def test_every_answer_shows_what_it_was_read_from() -> None:
    """A verdict without its provenance is an opinion in a number's clothes.

    The source, the record it came from, the figure, the line that figure was
    compared against, and the three clocks. Confusing those three is how a
    question gets answered against the wrong one, so all three are shown.
    """
    draw = PAGE[PAGE.index("function drawAnswer("):]
    draw = draw[: draw.index("\n}\n")]
    for shown in ("a.source", "a.url", "a.reading", "a.threshold",
                  "a.measured_at", "a.retrieved_at", "a.asked_at"):
        assert shown in draw, f"the answer does not show {shown}"
    assert 't("Yes")' in draw and 't("No")' in draw, "the verdict is not stated in words"


def test_the_page_says_it_is_not_a_settlement_and_carries_no_stake() -> None:
    """The one thing this must not drift into.

    Held against the page a reader sees, not against a comment: the sentence
    under every answer and the section explaining why this is not a prediction
    market are both things somebody can check without reading the source.
    """
    assert "Nothing was staked on this answer and nothing was paid on it." in PAGE
    assert "Why this is not a prediction market" in VIEW

    # And no machinery for one has appeared in this page's own script.
    script = SCRIPT
    # Matched as the start of a name rather than as a whole one, because a
    # script names things in camelCase: written as whole words this passed
    # with a "stakeTotal" added to the page's state.
    banned = ("stake", "wager", "payout", "odds", "gambl", "jackpot")
    # "bet" is the start of "between" and "better", so it is matched exactly.
    exact = ("bet", "bets", "betting", "bettor", "bettors")

    # The words are allowed where the page says out loud what it will not do:
    # its comments, and the English it hands to t() for translation.
    code = re.sub(r"/\*.*?\*/", "", script, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    code = re.sub(r'\bt\("(?:[^"\\]|\\.)*"', 't("', code)
    code = re.sub(r"\besc\('(?:[^'\\]|\\.)*'", "esc('", code)

    found = sorted({w for w in banned if re.search(rf"\b{w}[A-Za-z]*\b", code, re.I)}
                   | {w for w in exact if re.search(rf"\b{w}\b", code, re.I)})
    assert not found, f"this page's script deals in these, and it must not: {found}"


def test_a_class_attribute_is_written_whole() -> None:
    """Because one pasted together cannot be read back by anything.

    Both of this page's state-carrying classes were built by concatenation at
    first -- ``class="answer' + (yes ? " yes" : "") + '"`` and ``class="fld ' +
    size + '"`` -- and the guard that holds a page's styles to that page found
    nothing wearing either of them. The verdict rides an attribute now and the
    field classes are written out in full.
    """
    script = SCRIPT
    pasted = re.findall(r'class="[^"]*\'\s*\+', script)
    assert not pasted, f"a class attribute is pasted together: {pasted[:2]}"
    assert 'class="fld wide"' in script and 'class="fld num"' in script
    assert 'class="answer" data-yes="' in script


def test_the_narrow_case_needs_no_media_query_to_be_right() -> None:
    region = re.search(
        r"== scoped styles for #view-ask, begin ==(.*?)== scoped styles, end ==", PAGE, re.S)
    assert region, "the page's own styles are not marked as its own"
    styles = region.group(1)
    assert ".askfields{display:flex;flex-wrap:wrap" in styles, (
        "the fields cannot wrap, so a phone gets a row that overflows"
    )
    assert ".clocks{display:grid;gap:10px" in styles, "the clocks do not stack by default"
    many = re.search(r"@media \(min-width:(\d+)px\)\{\.clocks\{grid-template-columns", styles)
    assert many and int(many.group(1)) >= 600, "three clocks abreast on a phone is three slivers"
