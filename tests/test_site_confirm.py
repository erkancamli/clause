"""The page a buyer signs on, and the two ways it lied.

A reader moved from a home to a flight and was shown, on the confirm step, an
earthquake sentence, an earthquake payout table and an earthquake contract
underneath a summary of their flight -- and could not go on, because the
contract on screen was not the contract the gate was hashing, so the button
asked them to accept a contract they had just accepted.

One line caused it. The flight sentence looked the route up in ROUTES by
flow.subject; the subject of a flight is "IST-GZT" and that table is keyed
"TK-IST-LHR", so the lookup was undefined and the line threw. The step is
drawn top to bottom, so everything below the throw stayed as it was: the
policy before this one.

These are static checks over the source. What they stand for -- that a flight
really draws a flight, and that a redraw which cannot finish stops the
purchase instead of leaving somebody else's terms on screen -- is checked in a
browser by walking the purchase twice, once whole and once with this line
broken on purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import page_assembled

SITE = Path(__file__).resolve().parent.parent / "site"
PAGE = page_assembled()


def _code() -> str:
    """The page's script with its comments taken out.

    A rule about what the code does must not be satisfied, or broken, by prose
    that happens to describe it -- including the prose above these lines, which
    names the very expression they forbid.
    """
    body = re.sub(r"/\*.*?\*/", "", PAGE, flags=re.S)
    return re.sub(r"^\s*//.*$", "", body, flags=re.M)


def test_the_route_table_is_never_read_by_the_flight_subject() -> None:
    """Two different keys, and only one of them was ever going to be there."""
    assert "ROUTES[flow.subject]" not in _code(), (
        "the route table is being read by the flight's subject again"
    )


def test_the_subject_of_a_flight_could_not_be_a_route_key() -> None:
    """Why that lookup can never hit, stated as the two shapes themselves.

    If someone makes the subject three parts, or the table two, the rule above
    stops being the thing that matters and this says so.
    """
    made = re.search(r"flow\.subject=\(flow\.flightFrom&&flow\.flightTo\)\?"
                     r"flow\.flightFrom\+\"(-)\"\+flow\.flightTo", _code())
    assert made, "the flight's subject is no longer built from its two ends"
    keys = re.findall(r'\n\s*"([A-Z0-9-]+)":\{carrier:', PAGE)
    assert keys, "the route table has no keys"
    assert all(k.count("-") == 2 for k in keys), (
        f"a route key no longer carries a carrier prefix: {keys}"
    )


def test_the_flight_sentence_names_its_ends_the_way_the_summary_does() -> None:
    """One policy on the page, named one way."""
    code = _code()
    said = re.search(r'return t\("If your flight from \{from\} to \{to\}[^;]+;', code, re.S)
    assert said, "the flight sentence is gone"
    for side in ("From", "To"):
        assert f"flow.flight{side}Text||flow.flight{side}" in said.group(0), (
            f"the {side.lower()} end is not named from the flight the reader chose"
        )


def test_a_redraw_that_cannot_finish_is_caught() -> None:
    """The step is drawn top to bottom; a throw halfway is not cosmetic."""
    code = _code()
    guard = re.search(r"function renderPrice\(\)\{(.*?)\n\}", code, re.S)
    assert guard, "renderPrice is gone"
    body = guard.group(1)
    assert "try{" in body and "catch" in body, "the redraw is unguarded again"
    assert "confirmUnshowable()" in body, "a failed redraw is not handled"
    assert "console.error" in body, (
        "a page that swallows its own errors is how this one stayed hidden"
    )


def test_a_failed_redraw_leaves_none_of_the_policy_before_it() -> None:
    """Blanked, because nothing below a failed redraw is this policy."""
    code = _code()
    hand = re.search(r"function confirmUnshowable\(\)\{(.*?)\n\}", code, re.S)
    assert hand, "nothing handles a failed redraw"
    body = hand.group(1)
    for block in ("plain", "pay-rows", "contract-text", "offers"):
        assert f'"{block}"' in body, f"{block} would keep the previous policy"
    assert "flow.unshowable=true" in body, "the gate is not told"


def test_the_gate_stops_before_it_weighs_anything_else() -> None:
    """A disabled button does not survive the next call to setNextLabel.

    Half a dozen things call it, so the flag has to be read inside it -- and
    read before the ruling, the price and the contract, none of which are about
    this policy when the redraw did not finish.
    """
    code = _code()
    gate = re.search(r"function setNextLabel\(\)\{(.*?)\n\}", code, re.S)
    assert gate, "setNextLabel is gone"
    body = gate.group(1)
    flag = body.find("flow.unshowable")
    assert flag != -1, "the gate does not know about a failed redraw"
    assert flag < body.index("localRuling()"), (
        "the gate weighs the policy before noticing it could not be shown"
    )
    after = body[flag : flag + 260]
    assert "disabled=true" in after and 'aria-disabled","true"' in after, (
        "the purchase is not actually stopped"
    )


def test_the_reader_is_told_in_every_language() -> None:
    """Being stopped without a reason is the state this replaces."""
    import json

    said = ("This cover cannot be shown, so it cannot be bought. Go back a step "
            "and choose again; nothing has been charged.")
    assert said in PAGE, "the page never says why it stopped"
    for lang in ("tr", "de", "fr", "es", "ru", "ja"):
        doc = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for line in (said, "This cover cannot be shown"):
            assert doc["strings"].get(line), f"{lang} has no words for {line[:32]!r}"
