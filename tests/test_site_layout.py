"""Width the page reserves against width the reader gets.

A grid track is held open by the stylesheet, not by its occupant, so hiding
the thing in it leaves the space behind. That is what happened to the confirm
step: it is the one step that wants no running rail beside it -- it is itself
the summary -- and it was laid out in 952px of a 1328px page with the rail's
340px column and its 36px gap, 376px in all, blank down the whole of the
longest page in the product.

These are static checks over the markup and the stylesheet. What they stand
for -- that the step really fills the page -- is measured in a browser by
driving the purchase to that step, which is how the 952 above was got.
"""

from __future__ import annotations

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PAGE = (SITE / "index.html").read_text(encoding="utf-8")

#: The class the flow puts on the wrap when it takes the rail away.
MARK = "no-rail"


def test_the_rail_and_its_track_are_taken_away_together() -> None:
    """One condition, both effects, or the space outlives its occupant."""
    hide = re.search(r"rail\.hidden\s*=\s*([^;\n]+);", PAGE)
    assert hide, "nothing hides the rail any more"
    condition = hide.group(1).strip()
    after = PAGE[hide.end() : hide.end() + 400]
    toggle = re.search(
        r'classList\.toggle\("' + MARK + r'",\s*([^)]+)\)', after
    )
    assert toggle, f"the wrap is never marked {MARK!r} where the rail is hidden"
    said = toggle.group(1).strip()
    assert said in ("rail.hidden", condition), (
        f"the track is dropped on {said!r} but the rail is hidden on {condition!r}"
    )


def test_the_marked_wrap_gives_up_the_second_column() -> None:
    """The mark has to actually collapse the grid, in the query that made it."""
    two = PAGE.index("#view-cover > .wrap{display:grid")
    rule = re.search(
        r"#view-cover > \.wrap\." + MARK + r"\{[^}]*grid-template-columns:([^;}]+)", PAGE
    )
    assert rule, f"no rule collapses a {MARK!r} wrap"
    # One track, counted outside the brackets: minmax(0,1fr) is a single
    # column that happens to contain a comma.
    tracks, depth = 1, 0
    for ch in rule.group(1).strip():
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch in " \t" and depth == 0:
            tracks += 1
    assert tracks == 1, (
        f"the collapsed wrap still asks for {tracks} tracks: {rule.group(1).strip()}"
    )
    # Both rules have to live under the same breakpoint, or the collapse
    # applies where there was never a second column to give up.
    assert PAGE.rindex("@media (min-width:", 0, two) == \
           PAGE.rindex("@media (min-width:", 0, rule.start()), (
        "the collapse is not in the media query that opened the second column"
    )


def test_the_step_keeps_a_measure_when_it_has_the_whole_page() -> None:
    """Filling the page is not the same as being readable across it.

    Given the rail's width back, the step would run the full 1328px and the
    prose under it with it. It keeps the measure the stylesheet always meant
    it to have, centred rather than pinned left.
    """
    rule = re.search(
        r"#view-cover > \.wrap\." + MARK + r" > \.q,\s*"
        r"#view-cover > \.wrap\." + MARK + r" > \.done\{([^}]*)\}",
        PAGE,
    )
    assert rule, "the freed step is given no measure of its own"
    body = rule.group(1)
    cap = re.search(r"max-width:\s*(\d+)px", body)
    assert cap and int(cap.group(1)) <= 1240, f"no usable cap in {body!r}"
    assert "margin-inline:auto" in body, "the step is pinned to one side of the page"
