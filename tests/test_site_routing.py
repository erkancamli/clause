"""What the router owes a reader who cannot see the screen change.

A single page application changes everything but the address bar, and the two
things a browser would otherwise have done for it — name the page, and put the
reader at the top of the new one — it has to do itself. This site did neither:
twelve screens in seven languages shared the title "Clause", and focus stayed
on whatever link had been clicked.

These are static checks over the markup and the dictionaries, so they cost
nothing and run everywhere. The behaviour they stand for — that the title
really changes and that focus really lands — is checked in a browser by
scripts/accessibility.py's sweep.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PAGE = (SITE / "index.html").read_text(encoding="utf-8")
LANGS = ["tr", "es", "fr", "de", "ru", "ja"]

#: The switcher applies the reader's choice the moment it is made, which 3.2.2
#: permits only where the reader was told it would. This sentence is the
#: telling (technique G13), so it is not a label anyone may quietly shorten.
SWITCHER = "Language — choosing one changes the page at once"


def views() -> dict[str, str]:
    """Each routed screen's markup, by element id."""
    found = {}
    for match in re.finditer(r'<section class="view" id="(view-[a-z]+)">', PAGE):
        start = match.end()
        end = PAGE.index("\n</section>", start)
        found[match.group(1)] = PAGE[start:end]
    return found


def test_every_screen_is_routed_and_has_one_name():
    """The title is read off the screen's own h1, so there must be exactly one.

    Not zero, or the screen keeps the name of the one before it; not two, or
    which of them names the page is whichever the browser reaches first.
    """
    routed = set(re.findall(r'"(view-[a-z]+)"', PAGE))
    screens = views()
    assert routed <= set(screens), sorted(routed - set(screens))
    assert len(screens) >= 13, sorted(screens)
    for name, markup in screens.items():
        assert markup.count("<h1") == 1, f"{name} has {markup.count('<h1')} first-level headings"


def test_the_router_names_the_page_and_moves_focus():
    """2.4.2 and 2.4.3, in the one function that can honour them."""
    assert "document.title =" in PAGE, "nothing ever sets the page's name"
    # The name is derived, not tabulated: a second table is a second place for
    # the words to go stale, and the h1 is already translated.
    assert 'querySelector("h1")' in PAGE
    # Focus moves only when somebody navigated, never on the first render.
    assert 'addEventListener("hashchange",function(){show(currentRoute(), true);});' in PAGE
    assert 'heading.setAttribute("tabindex", "-1")' in PAGE


def test_each_question_in_a_purchase_is_a_place():
    """Baymard's finding, in the router: Back belongs to the buyer.

    People in a checkout reach for the browser's Back button rather than for a
    Change link on the page, and a flow living at one address throws them out
    of the purchase when they do. So each question has its own entry, and the
    address is corrected rather than obeyed when it asks for one the reader
    has not reached.
    """
    assert 'function stepHash(n){ return n > 1 && n < DONE_STEP ? "#/cover/" + n : "#/cover"; }' in PAGE
    assert "function goStep(n, quietly)" in PAGE
    assert "function stepAsked(route)" in PAGE
    # Nothing may move the question without moving the address with it.
    assert "flow.step++" not in PAGE
    assert "flow.step--" not in PAGE
    assert "flow.step=DONE_STEP" not in PAGE
    # Forwards is bounded by the furthest question ever asked, not by the one
    # on the screen, or the browser's Forward button stops working.
    assert "if(want > flow.reached)" in PAGE
    assert "reached:1," in PAGE
    # A purchase that has gone through is not somewhere to return to.
    assert "goStep(DONE_STEP, true)" in PAGE
    assert "if (flow.step >= DONE_STEP) resetFlow();" in PAGE


def test_typing_fields_are_not_small_enough_to_zoom_ios():
    """Under 16px, iOS Safari zooms the page and leaves the reader to pinch back."""
    assert "textarea{font-size:16px}" in PAGE


def test_the_language_switcher_says_what_choosing_does():
    assert SWITCHER in PAGE, "the switcher's label no longer warns that it acts at once"
    for lang in LANGS:
        strings = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        assert SWITCHER in strings, f"{lang} has no translation for the switcher's label"
        assert strings[SWITCHER].strip(), f"{lang}'s translation of the switcher's label is empty"


# ------------------------------------------------ buying while the book moves

def test_a_held_price_is_what_the_contract_is_keyed_on() -> None:
    """The contract's identity used to carry the page's live premium, so every
    move in the book -- another policy written by somebody else, anywhere --
    replaced the contract underneath the person reading it and silently
    un-ticked their acceptance. The contract is the longest thing on the page;
    a reader could not reach the end of it before the thing they were about to
    accept had been swapped, and the tick box then answered to nothing.

    A held quote is a promise about the price for ten minutes and the protocol
    keeps it: the contract is fetched with the lock's id and the purchase is
    sent with it. So while the lock is held, the lock is the key, and what the
    book does meanwhile is not the buyer's problem.
    """
    page = PAGE
    assert 'held?["lock",lock.id]:priced().premium' in page, (
        "contractKey no longer prefers the held lock, so a price move blocks buying")
    assert "function contractKey()" in page


def test_a_contract_that_could_not_be_prepared_says_so() -> None:
    """Both failure paths used to end in a checkbox that answered to nothing:
    the request failing wrote the refusal into the panel and left the old key
    in place, and a reply that arrived after the terms had moved was dropped
    with nothing asked again. Neither told anybody, and neither could be
    retried."""
    page = PAGE
    assert "function contractFailed(" in page
    assert "Try preparing it again" in page
    assert "renderContract.chased" in page, "a discarded contract is not asked for again"


# ---------------------------------------------------------------------------
# What happens when the reply to a purchase goes missing
# ---------------------------------------------------------------------------


def test_only_a_failure_that_carried_no_answer_may_be_asked_again() -> None:
    """A refusal is an answer and must be shown, not retried. The flag that
    tells the two apart is set in one place, on the branch where nothing came
    back at all, and the retry is guarded by it."""
    assert "reason.unanswered = true;" in PAGE
    # Set only where no reply arrived: inside the rejection handler, under the
    # same condition as the kind, and never on an http status.
    assert PAGE.count("unanswered = true") == 1
    # In the rejection handler, before it rethrows.
    handler = PAGE[PAGE.index('reason.kind = (reason.name === "AbortError")'):]
    assert handler.index("reason.unanswered = true;") < handler.index("throw reason;")
    # And nowhere near the branch that has a status: a 409 is a decision the
    # buyer must read, not a question to put again.
    refused = PAGE[PAGE.index('error.kind = "http " + reply.status;'):]
    assert "unanswered" not in refused[:refused.index("throw error;")]


def test_the_purchase_asks_again_once_and_sends_the_same_request() -> None:
    """The second ask is safe only because it is the same request: the protocol
    recognises the challenge and answers with the application it already wrote.
    A rebuilt body, with a fresh challenge, would be a second purchase."""
    where = PAGE.index('setBusy(t("Sending the application…"));')
    tail = PAGE[where:where + 3000]
    # One body, built once, sent by both asks.
    assert "var application={" in tail
    assert tail.count("body:application}") == 2
    # Guarded, so a refusal is never re-sent.
    assert "if(!(error&&error.unanswered))throw error;" in tail
    # And only twice: the second ask has no catch of its own.
    assert tail.count('api("/api/applications"') == 2


def test_a_purchase_does_not_sign_in_twice() -> None:
    """Signing in unconditionally meant the device door registered, challenged
    and verified twice for one purchase: three round trips added to the most
    fragile moment in the flow."""
    assert "(identity.token?Promise.resolve():signIn()).then(" in PAGE
    assert "\n  signIn().then(function(){\n    setBusy(t(\"Signing the terms…\"));" not in PAGE


def test_the_sentence_shown_while_it_asks_again_is_translated() -> None:
    for code in LANGS:
        strings = json.loads((SITE / "i18n" / f"{code}.json").read_text(encoding="utf-8"))["strings"]
        assert strings.get("Still sending. Asking again…"), code


def test_being_decided_never_promises_the_money_stayed() -> None:
    """Two answers mean "we do not know yet" — being replaced, and being
    decided — and the one thing this banner must never do is tell somebody who
    was charged that they were not."""
    assert "payload.detail&&payload.detail.deciding" in PAGE
    where = PAGE.index('var unsure=!!(payload&&(payload.error==="restarting"')
    line = PAGE[where:PAGE.index("\n", PAGE.index("nothing was charged", where))]
    assert 'payload.detail&&payload.detail.deciding' in line
    assert 'refused&&!unsure?"nothing was charged"' in line


def test_the_sentence_for_a_purchase_still_being_decided_is_translated() -> None:
    key = ("This purchase is still being decided. Nothing was sent twice. Look at My cover "
           "in a moment: if the cover is there it went through, and if it is not, nothing "
           "was taken.")
    assert key in PAGE
    for code in LANGS:
        strings = json.loads((SITE / "i18n" / f"{code}.json").read_text(encoding="utf-8"))["strings"]
        assert strings.get(key), code


# ---------------------------------------------------------------------------
# Reading one half of the proof register
# ---------------------------------------------------------------------------


def test_the_register_offers_both_halves_and_counts_them() -> None:
    """The page opened on the last twelve decisions of any kind, and in a book
    where most policies run their term quietly that is twelve quiet ones: a
    reader looking for a payment found none, on a page whose own figures said
    thousands had been made. The counts are on the buttons because a filter
    that hides how large the other half is would be the advertisement this page
    exists not to be."""
    assert 'data-sieve=' in PAGE
    for kind in ('""', '"paid"', '"lapsed"'):
        assert f'kind:{kind}' in PAGE.replace('kind: ', 'kind:'), kind
    assert 'count:"evaluated"' in PAGE and 'count:"paid"' in PAGE and 'count:"lapsed"' in PAGE


def test_choosing_a_half_asks_the_protocol_for_that_half() -> None:
    """Filtering in the browser would filter the twelve rows it already has,
    which are the twelve that do not contain what the reader is looking for."""
    where = PAGE.index("function bindSieve")
    tail = PAGE[where:where + 1800]
    assert '"/api/decided?limit=12"+(sieveNow?"&kind="+encodeURIComponent(sieveNow):"")' in tail


def test_the_buttons_are_bound_by_delegation() -> None:
    """The register is redrawn on every choice, so a handler attached to a
    button that has been replaced is a handler on nothing."""
    where = PAGE.index("function bindSieve")
    tail = PAGE[where:where + 900]
    assert "box.addEventListener" in tail
    assert "closest" in tail


def test_the_words_on_the_filter_are_translated() -> None:
    for code in LANGS:
        strings = json.loads((SITE / "i18n" / f"{code}.json").read_text(encoding="utf-8"))["strings"]
        for key in ("Every decision", "Paid", "Not triggered",
                    "Which decisions to show",
                    "No decision of this kind has been made yet."):
            assert strings.get(key), f"{code} is missing {key!r}"
