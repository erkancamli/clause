"""The paying screen is six named parts, and shows each amount once.

It was fifteen blocks in a row separated by a 14px gap and nothing else, and
two drawings of the same three amounts: the payout ladder and the exceedance
curve are both read off the policy's own points, so a buyer met the figures
twice and learnt nothing the second time. What the curve carries and the
ladder cannot -- the shape between the steps, and how far the trigger sits
from an ordinary reading -- is worth a drawing, but not worth 428px of the
screen where the money moves, so it is behind a disclosure.

These are static checks over the markup, the script and the stylesheet. That
the parts really render, in order, with nothing empty, is measured in a
browser by driving a purchase to the step.
"""

from __future__ import annotations

import re

from conftest import page_assembled, stylesheet

PAGE = page_assembled()
STYLES = stylesheet()

#: The parts, in the order a buyer meets them. The order is the argument: what
#: the cover is, then when it pays, then when it does not, then who stands
#: behind it, then what has to be signed, then the money.
PARTS = [
    ("part-cover", "Your cover"),
    ("part-pays", "When Clause pays"),
    ("part-basis", "What this does not cover"),
    ("part-issuer", "Who issues the policy"),
    ("part-docs", "Documents"),
    ("part-pay", "Payment and acceptance"),
]


def confirm_step() -> str:
    """The markup of the confirm step alone, up to the done screen."""
    start = PAGE.index('<div class="q" id="s4"')
    end = PAGE.index('<div class="done" id="s5"')
    return PAGE[start:end]


def test_the_confirm_step_is_the_six_parts_in_order() -> None:
    step = confirm_step()
    found = re.findall(r'<section class="part" id="(part-[a-z]+)"', step)
    assert found == [p for p, _ in PARTS], found


def test_every_part_carries_its_name_and_its_number() -> None:
    step = confirm_step()
    for number, (part, name) in enumerate(PARTS, start=1):
        at = step.index(f'id="{part}"')
        head = step[at:at + 400]
        assert f'<span class="part-n" aria-hidden="true">{number}</span>' in head, part
        assert f">{name}</span>" in head, part


def test_a_part_names_itself_to_a_screen_reader() -> None:
    """The number is decoration; the name and the heading level carry it."""
    step = confirm_step()
    for part, _ in PARTS:
        at = step.index(f'id="{part}"')
        head = step[at:at + 400]
        assert f'aria-labelledby="{part}-t"' in step[at - 120:at + 120], part
        assert f'id="{part}-t"' in head, part


def test_the_curve_is_behind_a_disclosure_and_the_ladder_is_not() -> None:
    """One drawing of the payout in the open, not two."""
    step = confirm_step()
    ladder = step.index('id="pay-rows"')
    curve = step.index('id="curve"')
    disclosure = step.index('<details class="more" id="curve-box">')
    shut = step.index("</details>", disclosure)
    assert disclosure < curve < shut, "the curve is not inside the disclosure"
    assert not (disclosure < ladder < shut), "the ladder was folded away too"


def test_the_curve_keeps_no_caption_of_its_own() -> None:
    """Everything the caption said is now said where it is read.

    The caption carried why the payout steps, which belongs beside the ladder,
    and what the index is measured on, which is basis risk in one sentence. A
    figure that repeats them under the drawing is how this screen came to hold
    two of everything.
    """
    script = PAGE
    assert '$("curve-cap").textContent="";' in script
    assert 'payNote.textContent=note' in script
    assert 'scaleBox.textContent=scaleSaid()' in script


def test_what_is_not_covered_is_a_part_and_not_a_row_of_the_summary() -> None:
    """It was the last row of the answers table under a 10px uppercase label.

    That is the typography of a field name, and this is the one thing on the
    screen a buyer is most likely to be wrong about.
    """
    assert 'basis.innerHTML=' in PAGE
    assert '<p class="basis-cut">' in PAGE
    assert 'class="ans basis"' not in PAGE, "the summary row came back"


def test_a_half_drawn_redraw_blanks_every_part_it_filled() -> None:
    """Nothing below a redraw that did not finish belongs to this policy."""
    for blanks in re.findall(r"var blanks=\[([^\]]+)\];", PAGE):
        assert '"basis-box"' in blanks, blanks
    assert PAGE.count('["pay-note","basis-scale"].forEach') == 2


def test_the_parts_are_separated_by_a_rule_and_not_by_a_gap_alone() -> None:
    assert re.search(r"\.part \+ \.part\{[^}]*border-top:1px solid var\(--edge\)", STYLES)


def test_a_part_with_nothing_to_say_shows_nothing() -> None:
    """Two of the places text lands are empty for most perils."""
    for box in ("#basis-scale", "#pay-note"):
        assert f"{box}:empty{{display:none}}" in STYLES, box
