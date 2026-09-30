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


# ---------------------------------------------------------------- waiting


def test_every_part_that_waits_carries_the_shape_of_what_is_coming() -> None:
    """Six headings over six empty parts read as a page that failed to load.

    The bar count is the shape of what will land there: four steps of a
    ladder, three lines of a company card.
    """
    step = confirm_step()
    slots = re.findall(r'<div class="part-wait" data-bars="(\d+)" hidden></div>', step)
    assert len(slots) == 5, slots
    at = {}
    for part, _ in PARTS:
        chunk = step[step.index(f'id="{part}"'):]
        head = chunk[:chunk.index("</section>")]
        found = re.search(r'class="part-wait" data-bars="(\d+)"', head)
        at[part] = int(found.group(1)) if found else 0
    assert at == {"part-cover": 0, "part-pays": 4, "part-basis": 2,
                  "part-issuer": 3, "part-docs": 3, "part-pay": 2}, at


def test_the_first_part_says_in_words_what_the_others_show_as_shapes() -> None:
    """A shape cannot say "working out your price"; five more lines of the
    same sentence would say nothing five more times."""
    step = confirm_step()
    cover = step[step.index('id="part-cover"'):step.index('id="part-pays"')]
    assert 'class="part-wait"' not in cover
    assert 'id="plain"' in cover
    assert 'working out your price' in PAGE


def test_the_shape_is_announced_as_busy_and_not_read_out_as_content() -> None:
    """Asked of the slot, not of the page.

    Four other things on this site draw skeletons, so "aria-busy is somewhere
    in the page" is true whatever these parts do. What is being asked is that
    the waiting slot is filled by the helper that marks itself busy.
    """
    assert "slot.innerHTML=show?skeleton(+slot.dataset.bars||3):\"\";" in PAGE
    found = re.search(r"function skeleton\(n\)\{(.+?)\n\}", PAGE, re.S)
    assert found and 'aria-busy="true"' in found.group(1)


def test_a_part_that_already_has_something_to_show_shows_no_shape() -> None:
    """Not every part waits for the price.

    The screening panel is drawn from who the buyer is and lands seconds
    before the protocol answers, and basis risk is read off the policy's own
    structure and needs no price at all.
    """
    assert "var show=waiting&&!partFilled(part);" in PAGE


def test_a_shape_stops_when_its_own_content_lands_not_when_the_price_does() -> None:
    # Four other files already watch something with a MutationObserver, so
    # asking whether the page has one answers nothing about this slot.
    assert "slot.watching=new MutationObserver(function(){" in PAGE
    assert "if(!slot.hidden&&partFilled(part)){ slot.hidden=true; slot.innerHTML=\"\"; }" in PAGE


def test_whether_a_part_is_filled_is_asked_of_its_contents_not_its_height() -> None:
    """The empty ladder is 8px tall: .pay-rows carries 4px of padding either
    side. A height test called it full, and the payout part alone never
    showed what it was waiting for."""
    assert 'child.childElementCount>0||child.textContent.trim()!==""' in PAGE
    assert re.search(r"\.pay-rows\{[^}]*padding-block:4px", STYLES), \
        "the padding this test stands on has moved; re-measure the empty ladder"


def test_a_disclosure_does_not_count_as_a_part_being_filled() -> None:
    """The curve's summary line is the same height whether the drawing behind
    it has been made or not."""
    assert 'if(child.tagName==="DETAILS")return false;' in PAGE


def test_the_shapes_go_when_the_price_lands_and_when_the_step_gives_up() -> None:
    assert PAGE.count("partsWaiting(false);") == 2
    assert PAGE.count("partsWaiting(true);") == 1
