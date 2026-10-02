"""The box on screen holds what the contract is sent.

renderInterest wrote #what from the model and then filled the model, in that
order, so for a home, a field and a car the field showed its placeholder
while flow.interest.what already held "A flat in Istanbul, Kadikoy". The
button said Continue, the summary row said the name, and both /api/contract
and /api/applications were sent it. The buyer signed a declaration of
insurable interest that the box they were looking at never showed.

It healed on the next render, which is one /api/compliance round trip away,
up to 18.9 seconds with the retry, and the text then appeared without the
buyer touching anything.

Read out of the source rather than run, because what is wrong is an order of
two statements.
"""

from __future__ import annotations

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
RISK = (SITE / "app" / "70-what-is-at-risk.js").read_text(encoding="utf-8")


def body_of(src: str, name: str) -> str:
    at = src.index(f"function {name}(")
    return src[at:src.index("\n}", at) + 2]


RENDER = body_of(RISK, "renderInterest")


def test_the_box_is_written_once() -> None:
    assert RENDER.count('$("what").value=') == 1, RENDER.count('$("what").value=')


def test_every_name_the_page_offers_is_worked_out_first() -> None:
    """Five perils name what is at risk; the write comes after all five."""
    writes = RENDER.index('$("what").value=')
    names = [m.start() for m in re.finditer(r'interest\.what=t\(', RENDER)]
    assert len(names) >= 5, f"five perils name it, found {len(names)}"
    assert all(at < writes for at in names), (
        "a name worked out after the box is written is a name the buyer never sees")


def test_the_place_is_cleared_before_the_box_is_written_too() -> None:
    """The line that drops a name the page chose when the place moves."""
    cleared = RENDER.index('interest.what="";')
    assert cleared < RENDER.index('$("what").value='), (
        "clearing it after the write leaves the old place on screen")


def test_the_placeholder_still_follows_the_value() -> None:
    assert RENDER.index('$("what").value=') < RENDER.index('$("what").placeholder')
