"""The drawings, and the boxes the page gives them.

The hero has one instrument drawn twice: a landscape reading for a row, and an
upright one for the sticky column beside the five steps. Both are vectors, so
the browser will happily scale either to whatever it is handed -- which is how
the upright one ended up a 320px drawing painted across 338px of column inside
a 661px panel, and read to its reader as a big mostly-empty card.

So the rule these hold is the one that was learned the expensive way: a drawing
in a column of fixed width is capped at its own size, and the ink it was drawn
with stays inside the box it declares. Neither is a matter of taste and neither
survives an eye.
"""

from __future__ import annotations

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PAGE = (SITE / "index.html").read_text(encoding="utf-8")

#: The two drawings, by the class the markup puts on them.
TALL = 'class="art art-tall"'


def _tall_svg() -> str:
    """The drawing itself, without the arrowhead it keeps in <defs>.

    A marker has a coordinate space of its own, so its ten units are not ten
    of the drawing's and counting them as such says nothing true."""
    start = PAGE.index("<svg " + TALL)
    svg = PAGE[start : PAGE.index("</svg>", start)]
    return re.sub(r"<defs>.*?</defs>", "", svg, flags=re.S)


def _view_box(svg: str) -> tuple[float, float]:
    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    assert box, "the drawing has to say what box it was drawn in"
    return float(box.group(1)), float(box.group(2))


def _ink(svg: str) -> tuple[float, float]:
    """The highest and lowest the drawing actually reaches.

    Every mark here is placed absolutely, so the extremes can be read straight
    off the source: a circle reaches its radius past its centre, a line or a
    path reaches its furthest coordinate, and text hangs about a fifth of its
    size below its baseline.
    """
    top, bottom = float("inf"), float("-inf")
    for c in re.finditer(r'<circle[^>]*\bcy="([\d.]+)"[^>]*\br="([\d.]+)"', svg):
        cy, r = float(c.group(1)), float(c.group(2))
        top, bottom = min(top, cy - r), max(bottom, cy + r)
    for m in re.finditer(r'\by[12]="([\d.]+)"', svg):
        y = float(m.group(1))
        top, bottom = min(top, y), max(bottom, y)
    for t in re.finditer(r'<text[^>]*\by="([\d.]+)"[^>]*font-size="([\d.]+)"', svg):
        base, size = float(t.group(1)), float(t.group(2))
        top, bottom = min(top, base - size), max(bottom, base + size / 4)
    for d in re.finditer(r'\bd="M([^"]+)"', svg):
        nums = [float(n) for n in d.group(1).split()]
        for y in nums[1::2]:
            top, bottom = min(top, y), max(bottom, y)
    return top, bottom


def test_the_upright_drawing_is_never_given_a_frame_larger_than_itself() -> None:
    """A vector blown up past its own size is what a hollow panel is made of.

    The column it sits in is a fixed width, so the cap has to be written down;
    the page cannot discover it.
    """
    width, _ = _view_box(_tall_svg())
    rule = re.search(
        r"\.stage-body\s*>\s*svg\.art-tall\{[^}]*max-width:\s*([\d.]+)px", PAGE
    )
    assert rule, "the upright drawing is not capped anywhere"
    assert float(rule.group(1)) <= width, (
        f"capped at {rule.group(1)}px, which is wider than the {width:g}px it was drawn at"
    )


def test_the_cap_is_in_the_column_that_pins_the_drawing() -> None:
    """Capping it on a phone would leave a drawing marooned in a wide card.

    The cap belongs to the one context where the drawing has a column of its
    own: the sticky one, which the page opens at 1300px.
    """
    at = PAGE.index("svg.art-tall{max-width")
    opener = PAGE.rindex("@media (min-width:1300px)", 0, at)
    assert PAGE.count("}", opener, at) < 2, (
        "the cap has drifted out of the sticky column's media query"
    )


def test_the_upright_drawing_keeps_its_ink_inside_its_box() -> None:
    """Ink outside the viewBox is ink the reader never sees."""
    svg = _tall_svg()
    _, height = _view_box(svg)
    top, bottom = _ink(svg)
    assert top >= 0, f"the drawing reaches {top:g}, which is above its own box"
    assert bottom <= height, (
        f"the drawing reaches {bottom:g}, past the {height:g} it declares"
    )


def test_the_upright_drawing_fills_the_box_it_asks_for() -> None:
    """The other half of the same rule.

    A box far taller than the ink in it is the same empty card by another
    route, and it is the one the reader complained about: the drawing declared
    340 and used 296 of it, with a dead band between the validators and the
    instrument. Nine tenths is the floor.
    """
    svg = _tall_svg()
    _, height = _view_box(svg)
    top, bottom = _ink(svg)
    used = bottom - top
    assert used / height >= 0.9, (
        f"the drawing uses {used:g} of the {height:g} it reserves "
        f"({used / height:.0%}); the rest is empty card"
    )


def test_both_traces_are_told_how_long_they_are() -> None:
    """The trace draws itself by unrolling a dash as long as the path.

    The length can only be had from the browser, and for a while only the
    landscape path was asked for it; the upright one kept a fallback longer
    than itself, so it finished drawing early and then stood still.
    """
    assert 'querySelectorAll(".hx-trace")' in PAGE, (
        "only one of the two traces is being measured"
    )
    assert PAGE.count('class="a-settled hx-trace"') == 2
