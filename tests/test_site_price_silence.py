"""A refusal and a silence are not the same answer.

The page told them apart by whether the protocol had sent a reason, and an
answer that never arrives carries none. A quote that timed out, a connection
that dropped, or any error whose body has no detail left flow.refusal null,
and every one of the five places a price goes read that as "not answered yet".

Measured in a browser, holding the quote unanswered: the paying screen read
"Pricing…" for seventy-five seconds, which was as long as the measurement was
willing to look, with nothing else on the screen and no way forward. After the
change it gives up at the quote's own 25 second timeout, says what happened,
and offers another go; pressing it with a working protocol draws the ladder
and returns the button to "Read and accept the contract".
"""

from __future__ import annotations

import re

from conftest import page_assembled

PAGE = page_assembled()


def test_no_reader_decides_the_state_from_whether_a_reason_arrived() -> None:
    """The idiom this replaces, in all five of the places it was written."""
    assert "flow.refusal?t(" not in PAGE


def test_the_three_states_are_told_apart_in_one_place() -> None:
    found = re.search(r"function priceSaid\(waiting\)\{(.+?)\n\}", PAGE, re.S)
    assert found, "priceSaid is gone"
    body = found.group(1)
    assert "if(flow.refusal)" in body
    assert "if(flow.unreached)" in body
    assert "return waiting;" in body


def test_every_place_a_price_goes_asks_that_one_place() -> None:
    """A button says "Pricing…" and a sentence says "working out your price",
    so the caller brings its own waiting word; what it may not do is decide
    which of the three states it is in."""
    assert PAGE.count("priceSaid(t(") == 5


def test_an_answer_that_never_came_is_remembered_as_such() -> None:
    assert "flow.unreached=!flow.refusal;" in PAGE


def test_a_fresh_attempt_forgets_the_last_silence() -> None:
    """Three places start over: a new quote, a new place, a new peril. A
    silence left behind on any of them would say the protocol is unreachable
    while it is answering."""
    assert PAGE.count("flow.unreached=false") == 3


def test_a_silence_is_offered_another_go_and_a_refusal_is_not() -> None:
    assert 'id="price-again"' in PAGE
    assert "if(said&&flow.unreached){" in PAGE
    found = re.search(r'again\.addEventListener\("click",function\(\)\{(.+?)\}\);', PAGE, re.S)
    assert found and "refreshQuote();" in found.group(1)


def test_nothing_is_charged_or_signed_is_said_where_it_is_needed() -> None:
    """The sentence a buyer needs first when a purchase screen goes wrong."""
    assert "Nothing has been charged and nothing has been signed." in PAGE


def test_no_shape_is_shown_for_an_answer_that_is_not_coming() -> None:
    assert "partsWaiting(!flow.unreached);" in PAGE


def test_the_new_sentences_are_translated_everywhere() -> None:
    import json
    import pathlib

    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    want = ["Clause could not be reached", "Clause could not be reached.",
            "Nothing has been charged and nothing has been signed."
            " The connection may have dropped, or the protocol may be busy."]
    for lang in ("tr", "es", "fr", "de", "ru", "ja"):
        strings = json.loads((site / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        for one in want:
            assert one in strings, (lang, one)
            assert strings[one] != one, (lang, one, "left in English")
