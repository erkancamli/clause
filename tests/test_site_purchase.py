"""Walking the purchase, and the two things that walk found.

The flow was never driven end to end from a test. It was driven from a
browser, peril by peril, by answering each step through its own controls, and
the Continue button turned out to be the instrument: when it is blocked it
says what is missing, so the page itself says where a buyer would stop.

Four of the five perils reached the sign-in. The fifth stopped, and what
stopped it was the page's own doing.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from conftest import page_assembled

ROOT = Path(__file__).resolve().parent.parent
PAGE = page_assembled()


def _function(name: str) -> str:
    at = PAGE.index(f"function {name}(")
    return PAGE[at : PAGE.index("\n}\n", at)]


def test_a_flight_number_is_only_invented_where_an_airline_is_known() -> None:
    """Two airports chosen one at a time do not name an airline.

    A route key names its airline first and the two ends after it, TK-IST-LHR.
    Choosing the ends separately makes the subject SAW-ESB, and taking the
    first part either way put an airport code where an airline code goes: the
    box was filled with SAW1979, which no flight number can be. The page then
    asked for a flight number over a field that already looked answered, and
    said nothing about what was wrong with it. A buyer choosing their own two
    airports could not get past the second step.

    Where the airline is not known the box is left empty, and the placeholder
    shows the shape of the thing to type.
    """
    body = _function("flightDefaults")
    assert "flightNumber" in body, "this is not the function that fills the number"

    # Whatever it does, it cannot take the first part of any subject at all.
    naive = re.search(r"flightNumber\s*=\s*\w+\.subject\.split\([\"']-[\"']\)\[0\]", body)
    assert not naive, "the first part of the subject is not an airline code"

    # It has to satisfy itself that the subject names one: three parts, and
    # the first of them two letters, which is what an airline code is.
    assert "length===3" in body.replace(" ", ""), "the subject's shape is not checked"
    assert re.search(r"/\^\[A-Za-z\]\{2\}\$/", body), "the airline code's shape is not checked"


def test_the_two_airport_subject_really_does_lack_an_airline() -> None:
    """The premise of the fix above, held against the code that builds it.

    If setAirport ever starts writing a three part subject, the guard becomes
    dead weight and should be revisited rather than left to rot.
    """
    body = _function("setAirport")
    assert re.search(r"subject\s*=.*flightFrom\s*\+\s*[\"']-[\"']\s*\+.*flightTo", body), (
        "the subject for two chosen airports is no longer FROM-TO"
    )


def test_nothing_is_priced_until_there_is_something_to_price() -> None:
    """The protocol was asked three times for a price it always refuses.

    A flight without its number came back "that cover cannot be priced" every
    time, which is the right answer to the wrong question: the page knew the
    subject was incomplete, because the same four checks are what its Continue
    button reads to say what is missing.

    Nothing waits on this either way: there is no figure on the screen until
    the protocol answers, so a call it is certain to refuse buys nothing.
    """
    body = _function("refreshQuote")
    guard = body.index("flightReady()")
    call = body.index('api("/api/offers')
    assert guard < call, "the readiness check comes after the request it is meant to prevent"
    for check in ("flightReady()", "quakeReady()", "stormReady()", "carReady()"):
        assert check in body[:call], f"{check} is not consulted before asking for a price"


def test_every_peril_can_still_be_started() -> None:
    """The five the flow walks, so a peril quietly dropped fails here.

    Driven in a browser rather than read: each of these reached the sign-in
    from the first screen, in Turkish, by answering the steps.
    """
    picks = set(re.findall(r'data-peril="(\w+)"', PAGE))
    assert {"quake", "storm", "car", "drought", "flight"} <= picks, picks


def test_a_refused_reading_is_not_a_reading_still_coming() -> None:
    """The button told a buyer to wait for something that had already arrived.

    Storm and vehicle cover are written only within 60 km of a Turkish
    provincial centre. Outside it the protocol answers 400 with a sentence
    saying exactly that, the page prints the sentence under the map, and the
    Continue button said "Still reading the place" -- at four seconds, at
    twelve, at thirty, and for as long as anybody cared to watch. Measured in
    a browser with the protocol's own refusal served back to the page.

    One sentence covered two states, and only one of them ends by itself. The
    refusal is a state of its own now and the button names the way out of it.
    """
    # The button's words are decided here; setNextLabel only paints them.
    body = _function("whatIsMissing")
    refused = body.index("Choose another place")
    waiting = body.index("Still reading the place")
    assert refused < waiting, (
        "the button still offers to wait before it notices the reading was refused")

    # All three readings, because all three can come back refused: the grid
    # outside Türkiye, the wind record, the rainfall record.
    said = body[:waiting]
    for flag in ("gridError", "stormError", "vehicleError"):
        assert flag in said, f"a refused {flag} still reads as a reading in flight"


def test_a_flight_is_inside_the_flight_by_construction() -> None:
    """The one confirmation on that step was a tautology.

    "It is inside the area measured" is a real question for a home, a car or a
    field, and the page answers it for three of the five perils by
    construction: the place the buyer chose is where the home stands. For a
    flight the area measured is the flight -- areaSentence() says so in those
    words, "the flight itself" -- so the buyer was asked to confirm that their
    flight is inside their flight. Measured at 390px: every other field on the
    step arrived answered, and this was the only thing blocking Continue.

    Drought is the one that still asks, and should. The field can be
    kilometres from the station that settles it, the sentence names that
    distance, and basis risk lives in it.
    """
    body = _function("renderInterest")
    line = next(l for l in body.splitlines() if "insideTouched" in l and "inside=true" in l)
    assert '"drought"' in line, "the field is no longer the one peril that has to be confirmed"
    for peril in ('"quake"', '"storm"', '"car"', '"flight"'):
        assert peril not in line, f"{peril} is named again instead of being covered by construction"


def test_every_peril_offers_a_name_for_the_thing_at_risk() -> None:
    """Four came with one and drought came with an empty required box.

    A flat in Kadıköy, a house, my car, one flight and what missing it costs:
    every peril but drought filled that field, so its buyer met a blank where
    the others met something to read and correct. It is named after the crop
    already selected and the place already chosen, like the rest.
    """
    body = _function("renderInterest")
    for peril in ("quake", "storm", "car", "flight", "drought"):
        assert re.search(rf'!interest\.what&&flow\.peril==="{peril}"', body), (
            f"{peril} offers no name for what is at risk")


def test_no_figure_appears_before_the_figure_that_will_be_charged() -> None:
    """The price shown first was not the price, and it moved by seventy per cent.

    This page can price a policy in a millisecond, and for a while it showed
    that while the protocol worked: 4,003 USDC captioned "before the company's
    fee", then 6,827 two seconds later. Both were honest about what they were.
    Neither helps a buyer who reads the first one and taps Continue.

    The gap is not a rounding of the same sum. The page charges one policy for
    the capital it needs standing alone; the protocol charges it for the
    capital it adds to a book of a hundred thousand others, which is a
    different and much smaller number, and then the company's fee goes on top.
    Measured at one address in Kadikoy the two agreed on the total to within
    seven per cent by coincidence and disagreed on every part of it by three
    times over.

    So the page cannot close the gap by computing harder, because it does not
    have the book. It waits instead, and says that it is waiting.
    """
    for name in ("updatePriceBar", "updateRunRail"):
        body = _function(name)
        figure = min(
            (body.index(call) for call in ("tweenAmount(", "money(total)") if call in body),
            default=-1,
        )
        assert figure > 0, f"{name} puts no price on the screen at all"

        # What the figure waits on, read as the page writes it.
        settled = re.search(r"var settled\s*=\s*([^;]+);", body)
        assert settled, f"{name} does not say what a settled price is"
        rule = settled.group(1).replace(" ", "")
        assert "&&" in rule, f"{name} settles on one half of the price: {rule}"
        assert "current" in rule, f"{name} does not wait for the protocol's answer: {rule}"
        assert "offer" in rule, f"{name} does not wait for the company's fee: {rule}"

        # And it is the quote for this selection, not any quote ever received.
        assert "flow.quotedFor===quoteKey()" in body[:settled.start()], (
            f"{name} does not check whose quote it is holding"
        )

        # Between the rule and the figure, the way out taken while it is unmet.
        between = body[settled.end():figure]
        assert re.search(r"if\(!settled\)", between), f"{name} does not act on its own rule"
        assert "return;" in between, f"{name} falls through to a figure it has not got"

        # Not connected is the exception, and the rule has to name it: there
        # the browser's own figure is the price by declaration, and the banner
        # at the top of the page says so.
        assert "link.live" in rule, f"{name} has nothing to show when nothing is connected: {rule}"


def test_the_quote_is_filed_under_the_company_it_was_struck_with() -> None:
    """A right answer filed under the wrong question is a wrong answer.

    The key was taken before the offers came back, so it carried no company;
    the offers then named one, the key moved, and the quote that arrived a
    moment later was already stale against it. Nothing was wrong with the
    number. It just did not count, so the page asked again and the buyer
    waited through two round trips to be told the same thing twice, with the
    bar empty in between.
    """
    body = _function("refreshQuote")
    named = body.index("flow.carrier=flow.offers.length")
    keyed = body.index("key=quoteKey()")
    assert named < keyed, "the price is keyed before the company it is struck on is known"
    assert body.index("flow.quotedFor=key") > keyed


def test_no_caption_promises_that_the_figure_will_change() -> None:
    """The half-price was captioned, and the caption was the giveaway.

    "before the company's fee; the whole price follows in a moment" is a
    sentence that only exists because a figure is on the screen that is not the
    figure. There is no such figure now, so there is no such sentence: the only
    place the page still says "before the company's fee" is where it is not
    connected at all and has told the reader so in the banner above.
    """
    assert "the whole price follows in a moment" not in PAGE
    assert "A price is a quote until the protocol answers for it" not in PAGE
    for lang in ("tr", "es", "fr", "de", "ru", "ja"):
        words = (ROOT / "site" / "i18n" / f"{lang}.json").read_text(encoding="utf-8")
        assert "the whole price follows in a moment" not in words, lang


def test_the_step_a_buyer_signs_on_shows_no_price_of_its_own() -> None:
    """The bar was fixed and the page under it was not.

    Arriving at the confirm step threw the protocol's answer away and asked
    for a fresh one, so for as long as that round trip took, the panel a buyer
    signs on drew its sentence, its breakdown, its payout table and its summary
    row from the browser's model -- the figure that had just been kept off the
    bar for being the wrong one, now printed four times over on the last screen
    before the money moves.

    Two things changed. The answer already in hand is kept while a fresh one is
    asked for, so in the ordinary walk there is nothing to wait for; and if
    there is no answer for this exact policy, the panel is not drawn at all.
    """
    body = _function("renderPriceBody")
    handoff = body.index("confirmPricing()")
    assert "flow.quotedFor===quoteKey()" in body[:handoff], (
        "the panel does not check whether the answer is this policy's"
    )
    assert "return;" in body[handoff:body.index("\n", handoff)], (
        "the panel goes on drawing after handing off to the waiting state"
    )
    # And nothing below the handoff is reached before it.
    for drawn in ("plainSentence()", "payRows()", "renderContract()"):
        assert body.index(drawn) > handoff, f"{drawn} is drawn before the check"

    # The answer in hand is no longer discarded at the start of a refresh.
    asking = _function("refreshQuote")
    assert "flow.quoted=null" not in asking.replace(" ", ""), (
        "the protocol's answer is thrown away before a replacement exists"
    )

    # The summary row obeys the same rule as the bar.
    answers = _function("renderAnswers")
    rule = re.search(r"var settled\s*=\s*([^;]+);", answers)
    assert rule, "the summary has no rule about when it carries a figure"
    assert "flow.quotedFor===quoteKey()" in rule.group(1), rule.group(1)
    assert rule.end() < answers.index("var price="), "the rule is settled after it is used"


def test_a_bar_that_stood_down_does_not_count_back_from_the_old_price() -> None:
    """The last thing the animation was still doing on its own.

    tweenAmount counts from whatever the element said last, which it keeps in
    a data attribute. With the bar standing down to an em dash between
    selections, that attribute held the price of a policy nobody is buying any
    more, so the new figure arrived by sweeping down from it: 1,283 to 517 over
    four hundred milliseconds, measured in a browser walking the flow. To
    anyone glancing at the bar that is the price changing while they watch,
    which is the whole thing this bar was just taught not to do.

    Standing down now forgets the figure as well as erasing it.
    """
    stand_down = _function("noAmount")
    assert "dataset.v" in stand_down, "the remembered figure survives standing down"
    assert "\u2014" in stand_down or "—" in stand_down, "standing down shows nothing in its place"

    # And nowhere writes the em dash without going through it.
    body = PAGE[PAGE.index("function updatePriceBar("):]
    body = body[: body.index("\n}\n")]
    assert 'pb-amt").textContent="—"' not in body, (
        "the bar blanks the figure without forgetting it"
    )
    assert body.count("noAmount(") >= 2, "the bar has ways of blanking that do not forget"


def test_the_model_card_a_buyer_opens_is_the_model_that_priced_them() -> None:
    """One country, three catalogue models, and one link between them.

    The page linked the model card by the country the grid reported. That was
    the same thing as the model until the United States became three of them:
    the lower forty eight, Alaska and Hawaii. A buyer in Anchorage following
    that link would read a model fitted on ground three thousand kilometres
    away, with a different b value, a different completeness magnitude and a
    largest event nearly a whole unit smaller, and would have no way to tell.

    The card is opened by the region now, which is the model's own key, and
    falls back to the country for every model that is one.
    """
    body = _function("radiusNoteHtml")
    assert "modelCardLink(g.region||g.country)" in body.replace(" ", ""), (
        "the card is still opened by the country rather than the model"
    )


def test_the_payout_table_is_the_policy_and_not_the_round_numbers_near_it() -> None:
    """Three answers to one question, on one policy, and none of them the contract's.

    An older building is damaged by less shaking, and the policy carries that:
    in Istanbul the steps are 6.25, 7.25 and 8.25, in New York 6.62, 7.62 and
    8.62, and they pay 35, 75 and 100 per cent. Neither table on this page said
    so.

    The table on the second step wrote all three levels and all three shares
    down by hand -- VI, VII and VIII at 25, 60 and 100 -- and read the hazard at
    those round numbers. A New York policy looked as though it paid once in
    1,788 years; it pays once in about 3,100, because 6.62 is a level that
    happens half as often as 6.0.

    The table on the confirm step read the policy's own curve, which is right,
    but at VI, VII and VIII, which is not: at 6.0 an Istanbul policy pays
    nothing, so the first row said zero, and the second row showed the first
    step's share under the second step's name.

    Both are built from the curve's own points now, as the car and storm rows
    always have been.
    """
    for name in ("payRows", "shakingHtml"):
        body = _function(name)
        block = body[body.index("shakingIndex()"):] if name == "payRows" else body
        block = block[: block.index("else if")] if "else if" in block else block

        assert "Intensity {level} or more" in block, f"{name} still names a fixed level"
        for fixed in ("Intensity VI:", "Intensity VII:", "Intensity VIII"):
            assert fixed not in block, f"{name} still writes {fixed!r} down"
        # And the shares come from the curve rather than from this file.
        for share in ("0.25", "0.6,", "),0.25", ",0.6"):
            assert share not in block.replace(" ", ""), f"{name} still writes a share down"


def test_a_roman_numeral_is_a_whole_number_and_these_steps_are_not() -> None:
    """MMI VII for a step at 6.62 is a level that happens half as often.

    The price bar names each rung of the ladder. It rounded the level to the
    nearest numeral, so New York's first step, 6.62, was printed as VII. The
    numeral is kept where the step really is a whole number, which is a
    building of the current code, and the number itself is printed otherwise.
    """
    packed = _function("rungWords").replace(" ", "")
    assert "ROMAN[Math.round(level)]" not in packed, "the level is still rounded to a numeral"
    assert "level===Math.round(level)" in packed, "there is no test for a whole number"
    assert "f1.format(level)" in packed, "a step that is not whole is not printed as a number"


def test_the_sentence_a_buyer_reads_is_the_policy_they_are_buying() -> None:
    """The most read line on the page had the policy written into it by hand.

    "If the ground shakes at intensity VI or more you receive a quarter, rising
    to the full amount at intensity VIII." Three facts, none of them this
    policy's: the shaking cover pays 35 per cent at its first step, and that
    step is 6.25 in Istanbul and 6.62 in New York, because an older building is
    damaged by less shaking. The magnitude sentence beside it named 5.5 and 7
    the same way, and those move with the building too.

    The car and storm sentences have always read their levels from the policy's
    own curve. All four read their levels and their first payment from it now.
    """
    body = _function("plainSentence")
    for fixed in ("intensity VI or more", "at intensity VIII",
                  "magnitude 5.5 or more", "for a magnitude 7"):
        assert fixed not in body, f"the sentence still names {fixed!r}"
    # And no share is written down: every one comes off the curve.
    assert ".25*l" not in body.replace(" ", ""), "a payout share is still written down"
    for share in ("qc[0][1]*l", "mc[0][1]*l", "cc[0][1]*l", "sc[0][1]*l"):
        assert share in body.replace(" ", ""), f"{share} does not come from the curve"


def test_one_quote_names_one_amount() -> None:
    """The at-risk line said 49,228 and every screen after it said 49,227.

    One float, two roundings. What a buyer reads on the "at risk" step went
    through money(), which rounds to the nearest whole number above a thousand;
    what became the cover ceiling, the top preset and the figure in the
    contract went through Math.floor. A quote for an Istanbul flat of 120 m²
    built in 2005 lands between two whole numbers, so the two disagreed by one
    USDC, on desktop and on the phone, in the same session.

    The value is rounded down once now, inside sizeValue, and everything
    downstream carries that same whole number.
    """
    from clause.protocol.valuation import schedule

    # Whether one area happens to land between two whole numbers depends on a
    # rate that moves with the exchange rate, so the scenario is found rather
    # than written down: the first written-down one, 120 m² at 519.29, stopped
    # splitting the day the rate reached 519.33 and this test would have gone
    # quiet rather than red.
    rate = schedule()["rebuild_per_m2"]["TR"]["flat"]
    ceiling = max(0.55, 1 - 0.01 * (2026 - 2005))
    splits = [a for a in range(15, 3001)
              if math.floor(a * rate * ceiling) != round(a * rate * ceiling)]
    assert splits, (
        f"at {rate} per m² no allowed floor area falls between two whole numbers, "
        "so nothing here would show the two roundings apart"
    )

    body = _function("sizeValue")
    for produced in ("Math.floor(area*rate*f.ceiling)", "Math.floor(z.area_ha*per)"):
        assert produced in body.replace(" ", ""), f"{produced} is not rounded where it is made"

    # And the one caller does not round it a second time.
    assert "flow.interest.value=value;" in PAGE.replace(" ", ""), "the caller no longer takes the value as made"
    assert "flow.interest.value=Math.floor(value)" not in PAGE.replace(" ", ""), "the second rounding is back"


def test_the_home_page_counts_the_steps_the_stepper_counts() -> None:
    """The button said three and the stepper drew five.

    "Get cover in three steps" is the most clicked thing on the site and it was
    wrong about the only thing it promises. The stepper names its steps out
    loud, What, Where, At risk, How much, Confirm, and the routes run from
    #/cover to #/cover/5. A buyer who takes the button at its word is surprised
    twice before the price.

    The count is read off the stepper here, so the two cannot drift apart
    again without this failing.
    """
    names = re.findall(r't\("([^"]+)"\)', _function("stepsBar").split("]", 1)[0])
    assert names == ["What", "Where", "At risk", "How much", "Confirm"], names

    words = {3: "three", 4: "four", 5: "five", 6: "six"}
    said = f"Get cover in {words[len(names)]} steps"
    assert said in PAGE, f"the home page does not say {said!r}"

    for wrong in (w for n, w in words.items() if n != len(names)):
        assert f"Get cover in {wrong} steps" not in PAGE, f"it still also says {wrong}"

    # And every language says the same number, not the number it was translated from.
    for path in sorted((ROOT / "site" / "i18n").glob("*.json")):
        book = json.loads(path.read_text(encoding="utf-8"))
        book = book.get("strings", book)
        assert said in book, f"{path.name} has no line for {said!r}"


def test_the_showcase_policy_is_written_on_one_index() -> None:
    """"if shaking >= M5.5" names two different measurements at once.

    Magnitude is the size of the earthquake at its source, one number for the
    whole event. Shaking is what arrives at an address, and it is a different
    number at every address. The hero wrote a magnitude threshold and called it
    shaking, and then the beat below it measured the event at M7.2, which is a
    magnitude reading. Both of the site's earthquake products are real, and the
    showcase was a picture of neither.

    It is the magnitude product now, all the way through: the rule, the caption
    under the drawing and the reading that settles it.
    """
    hero = PAGE[PAGE.index('class="phone"') : PAGE.index('id="hero-beats"')]
    assert "magnitude ≥ 5.5 within 50 km" in PAGE, "the rule is not a magnitude rule"
    assert "TRIGGER  M5.5" in hero, "the caption no longer names the trigger"

    # Nothing anywhere pairs the word shaking with a magnitude threshold.
    for near in re.findall(r"shaking[^<>]{0,60}", PAGE):
        assert not re.search(r"\bM\d", near), f"shaking is still measured in magnitude: {near!r}"


def test_the_page_does_not_say_that_nobody_decides() -> None:
    """The most prominent line on How it works was not true.

    "Nobody decides whether you get paid." A licensed company decides whether
    to issue the policy, and the page's own FAQ says so: the premium is held
    and not taken while it screens the buyer and confirms the thing is theirs.
    Validators decide what reading reaches the chain, and they can disagree.
    What nobody does is value the damage afterwards and form an opinion about
    what the loss was worth, and that is the thing worth saying.

    A buyer who reads the headline and then reads the FAQ finds the site
    contradicting itself on the question the whole product turns on.
    """
    assert "Nobody decides whether you get paid" not in PAGE, (
        "the page claims nobody decides, which its own FAQ contradicts"
    )
    said = "A measurement decides what you are paid, not an assessor."
    assert said in PAGE, f"the page does not say {said!r}"

    # And it says it in every language, not only in English.
    for path in sorted((ROOT / "site" / "i18n").glob("*.json")):
        book = json.loads(path.read_text(encoding="utf-8"))
        book = book.get("strings", book)
        assert said in book, f"{path.name} has no line for it"
        assert "Nobody decides whether you get paid." not in book, (
            f"{path.name} still carries the old claim"
        )
