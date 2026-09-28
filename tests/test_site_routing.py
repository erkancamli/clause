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
SWITCHER = "Language. Choosing one changes the page at once"


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
    tells the two apart is set where nothing usable came back, and the retry
    is guarded by it.

    Two places set it, because there are two silences. The request can fail to
    arrive, and the answer can be cut off part way through being read: the
    second leaves a rejection with no status and no payload, which fell through
    every branch of the buy banner to the one sentence that names no reason.
    Both may be asked again, because in both the protocol may have acted and
    the same question is the only safe one to put twice.
    """
    assert "reason.unanswered = true;" in PAGE
    assert "error.unanswered = true;" in PAGE
    # And no more than those two: a reply with a status is a decision.
    assert PAGE.count("unanswered = true") == 2
    # In the rejection handler, before it rethrows.
    handler = PAGE[PAGE.index('reason.kind = (reason.name === "AbortError")'):]
    assert handler.index("reason.unanswered = true;") < handler.index("throw reason;")
    # And nowhere near the branch that has a status: a 409 is a decision the
    # buyer must read, not a question to put again.
    refused = PAGE[PAGE.index('error.kind = "http " + reply.status;'):]
    assert "unanswered" not in refused[:refused.index("throw error;")]
    # The cut off answer is the other silence, and it names why it is one.
    cut = PAGE[PAGE.index('error.kind = "answer cut off after http "'):]
    assert cut.index("error.unanswered = true;") < cut.index("throw error;")


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
    assert "/api/decided?limit=" in tail
    assert '"&kind="' in tail and "encodeURIComponent(sieveNow)" in tail
    # The figure asked for is the named one, because the register compares what
    # came back against it to tell a full page from a protocol out of records.
    assert "REGISTER_LIMIT" in tail


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


# ---------------------------------------------------------------------------
# A register shorter than its own count
# ---------------------------------------------------------------------------


def test_the_register_is_a_window_and_says_which_one() -> None:
    """The last ten of each stage, and the count is the count.

    The register looked like an archive while being a window, and that is what
    made the figure beside it read as a contradiction: 2,976 payments on a button
    and one row under it. Raising what is kept until the two agreed was the wrong
    repair -- nobody needs the whole book to see that this protocol decides, and
    keeping ten thousand records to prove it is ten thousand records nobody reads.

    So the page says what it is showing before a reader meets it: the most recent
    ten, with a count that nothing caps. An explanation offered after the fact,
    in the one case somebody happened to look, is what this replaces.
    """
    assert "var REGISTER_LIMIT=10;" in PAGE
    assert "The most recent {n}. The figure on each button counts all of them" in PAGE
    # Said next to the filter, not buried under the rows it is explaining.
    where = PAGE.index("The most recent {n}.")
    assert "sieveHtml(book)" in PAGE[where - 400:where], (
        "the window is not stated beside the buttons that choose it")
    # And nothing apologises for the gap any more, because the gap is stated.
    assert "the count outlives the record. Any of the others" not in PAGE


def test_every_stage_has_its_own_ten() -> None:
    """Paid, not triggered, and the one where the data never came. The third was
    missing from the filter although the protocol has always decided it and the
    endpoint has always answered for it -- so a reader could not ask the one
    question this peril makes people most nervous about: what happens when the
    source says nothing. Its label is the one the row itself carries, so it
    needed no new words."""
    for kind in ('""', '"paid"', '"lapsed"', '"expired"'):
        assert f"kind:{kind}" in PAGE.replace("kind: ", "kind:"), kind
    for count in ("evaluated", "paid", "lapsed", "expired"):
        assert f'count:"{count}"' in PAGE, count
    assert 'label:N("No data")' in PAGE
    for code in LANGS:
        strings = json.loads((SITE / "i18n" / f"{code}.json").read_text(encoding="utf-8"))["strings"]
        assert strings.get("No data"), code


def test_the_register_asks_for_as_many_rows_as_it_compares_against() -> None:
    """The sentence appears when fewer came back than were asked for, so the
    two figures have to be one figure. Twelve written in three places is two of
    them being left behind when the third is changed."""
    assert PAGE.count("REGISTER_LIMIT") >= 4, "the limit is not named where it is used"
    assert "?limit=12" not in PAGE and "?limit=10" not in PAGE, (
        "a literal figure is still in a request")


# ---------------------------------------------------------------------------
# The digest above the hero
# ---------------------------------------------------------------------------


def test_the_digest_carries_no_links() -> None:
    """The quake chips in the bands at the foot of the page are anchors to
    USGS, and they belong there, beside the source line. In front of the hero
    they would be tab stops a keyboard reader pays on the way to the first
    thing they came to do, for a second copy of something already on the page.
    Measured in a browser: nine chips in the digest, no anchors in it, and the
    bands below still linked."""
    assert "function chipUnlinked" in PAGE
    where = PAGE.index("function paintDigest")
    body = PAGE[where:PAGE.index("function digestUnreachable")]
    assert "map(chipUnlinked)" in body, "the digest paints the chips as they came"


def test_the_digest_holds_its_height_before_it_has_anything_to_say() -> None:
    """An empty row that fills later moves the hero under the reader, at the top
    of the page, which is the worst place for it. So it says it is reading from
    the first paint -- and for that to help, the row has to be the same height
    while it says so.

    It was not. The stand-in was a line of text and stood 65px; with readings in
    it the row is 55px. Ten pixels, at the top of the page, which is the whole
    thing the stand-in exists to prevent. It was reported as zero because the
    measurement filled the row before it read it: feeds that answer instantly
    make "before" the same moment as "after", so the state being measured was
    never on screen. Measured against the live feeds with their answers held
    back, it was ten; it is zero now, on a phone and a desktop.

    Two constants were tried before this and both were wrong -- a chip measures
    35.19px here, not the 37 that was assumed -- because the figure moves with
    the font. A chip is the same height as a chip, so the stand-in is one, and
    there is no number to get wrong.
    """
    assert "paintDigest();\n  fillNowCountries();" in PAGE, (
        "the row is not drawn until the protocol answers")
    where = PAGE.index("function digestSaying")
    saying = PAGE[where:where + 800]
    assert 'class="chip saying"' in saying, (
        "the stand-in is not a chip, so the row is a different height for it")
    assert "band-empty" not in saying, (
        "a line of text is not the height of the chip it stands in for")
    digest = PAGE[PAGE.index("function paintDigest"):PAGE.index("function digestSaying")]
    assert 'bandFill("band-now-run", [],' not in digest, (
        "the digest still paints an empty row through the line-of-text path")
    assert "Reading the sources" in digest


def test_no_feed_can_leave_the_digest_waiting() -> None:
    """The digest is drawn by whichever feed finishes last, so a path that
    paints its own band and does not tell the digest leaves "Reading the
    sources" above the hero for ever -- including the paths that answer with
    nothing, which are the easy ones to forget: a feed that failed, and a
    country with no places listed. Every place a band is filled is a place the
    digest is told."""
    import collections

    body = PAGE[PAGE.index("function renderLive"):PAGE.index("function startLive")]
    cut = body.index("fillNowCountries()")
    assert "digestUnreachable()" in body[:cut], (
        "an unreachable protocol leaves the digest reading for ever")
    live = body[cut:]
    fills = collections.Counter(re.findall(r'bandFill\("band-(quakes|weather|flights)"', live))
    tells = collections.Counter(re.findall(r'digestKeep\("(quakes|weather|flights)"', live))
    assert fills == tells, f"bands filled {dict(fills)}, digest told {dict(tells)}"


def test_the_digest_takes_only_a_few_from_each_feed() -> None:
    """One noisy source -- a hundred late departures -- would otherwise be the
    whole digest, and the other two sources would never appear in it. Severe
    readings come first within a feed and across all of them, because the row
    scrolls and what a glance gets is whatever is in view."""
    assert "DIGEST_PER_FEED = 3" in PAGE
    where = PAGE.index("function digestKeep")
    body = PAGE[where:where + 500]
    assert "slice(0, DIGEST_PER_FEED)" in body
    assert "chipRank" in body, "a feed's own share is not ordered by severity"
    merged = PAGE[PAGE.index("function paintDigest"):PAGE.index("function digestUnreachable")]
    assert "chipRank" in merged, "the merged row is not ordered by severity"


def test_what_the_digest_says_fits_the_row_it_says_it_in() -> None:
    """One row is one row wide, and a sentence longer than it is a sentence a
    reader cannot finish.

    Making the stand-in a chip fixed its height and broke this: a chip sits in a
    track that hides its overflow behind a mask, so the sentence the digest used
    to carry -- 451px of it against a 252px track on a 390px phone -- was cut and
    the mask made the cut look like a fade. It says something one row long now,
    and where even that does not fit it ends in an ellipsis, which at least says
    it was cut. Measured at 390px and 320px in all six languages and English:
    nothing overflows.

    The ellipsis needed the row to stop being as wide as it wants. The track is
    what there is, so the run takes the track's width while it is standing in,
    and the readings go back to taking the width they need because the row
    scrolls them.
    """
    where = PAGE.index("function digestSaying")
    saying = PAGE[where:where + 900]
    assert 'class="chip saying"' in saying, "the stand-in cannot be measured against the row"
    assert 'classList.add("one-line")' in saying, (
        "the row is still as wide as it wants, so nothing constrains the sentence")
    assert ".band-one .band-run.one-line{width:100%}" in PAGE
    assert "text-overflow:ellipsis" in PAGE[PAGE.index(".band-one .chip.saying"):][:300], (
        "a sentence too long for the row is cut without saying so")
    # And the readings take their own width back, or they would all be squeezed
    # into one screen instead of scrolling.
    digest = PAGE[PAGE.index("function paintDigest"):PAGE.index("function digestSaying")]
    assert 'classList.remove("one-line")' in digest


def test_the_digest_says_something_a_row_can_hold() -> None:
    """The long sentence was the wrong length for the place it was put, and the
    six translations of it are longer still. The short one is what the row says,
    and the sign in strip's own "not answering" stands in for the long
    unreachable sentence, which the three bands at the foot of the page have room
    for and the digest does not."""
    assert "The sources this protocol settles against have nothing to report" not in PAGE, (
        "the sentence that needed 451px is back in a 252px row")
    assert '"Nothing to report right now."' in PAGE
    for code in LANGS:
        strings = json.loads((SITE / "i18n" / f"{code}.json").read_text(encoding="utf-8"))["strings"]
        short = strings.get("Nothing to report right now.")
        assert short and short != "Nothing to report right now.", code
        # No translation may be wildly longer than the English, because the row
        # is the same width in every language.
        assert len(short) <= 40, f"{code}: {short!r} is {len(short)} characters"
