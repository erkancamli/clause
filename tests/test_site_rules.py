"""The page that prints the rulebook.

The rulebook is eleven rows for each of five perils, and five of those rows
carry the same text for every one of them: how a reading is attested, how long
you have to object, what happens if a publisher goes away, what is archived,
and which version this is. Printed peril by peril they came out five times
each, which pushed what actually differs between perils down a page of
repetition, and made the rows a reader needs to compare the furthest apart.

So the page says those once. The danger in that is a row going missing: split
a list in two and a field can fall between the halves with nothing to say so,
and a rulebook with a row missing is worse than one that repeats itself.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
from clause.protocol import rulebook

VIEW = PAGE[PAGE.index('<section class="view" id="view-rules">'):]
VIEW = VIEW[: VIEW.index("\n</section>")]
RENDER = PAGE[PAGE.index("function renderRules(){"):]
RENDER = RENDER[: RENDER.index("\n/* What a decision is called")]


def test_the_page_is_reachable_and_named() -> None:
    assert '"/rules":"view-rules"' in PAGE, "the page is not routed"
    assert VIEW.count("<h1") == 1, "a screen takes its name from its one first-level heading"


def test_every_row_the_rulebook_publishes_is_printed_somewhere() -> None:
    """Split the rows in two and one can fall between the halves.

    Read from the rulebook rather than listed here, so a row added to the
    protocol and forgotten on the page fails rather than passes quietly.
    """
    peril = next(iter(rulebook.RULES))
    fields = set(rulebook.for_peril(peril, deadline_days=7, on_missing_data="x",
                                    attestation="y"))
    fields -= {"peril"}  # the key, not a row
    assert len(fields) >= 10, f"only {len(fields)} rows read out of the rulebook"

    # What the renderer reads off a peril, not merely what it names: written as
    # a substring search, this passed with the archive row deleted, because the
    # word "archive" was still there as the key that decides where the row goes.
    read = set(re.findall(r"\bx\.(\w+)\b", RENDER))
    missing = sorted(f for f in fields if f not in read)
    assert not missing, f"the rulebook publishes these and the page never prints them: {missing}"


def test_a_row_is_printed_once_and_the_page_decides_which_half() -> None:
    """Each shared row has two possible homes and one test choosing.

    The same ``common(field)`` picks the row into the panel above and out of
    the peril's own, so the two cannot drift apart. A list of "these four are
    the same" written into the page would be true until the day a peril is
    given an archive rule of its own, and then silently wrong.
    """
    assert "keys.every(" in RENDER, "the page assumes what is shared instead of reading it"
    for field in ("attestation", "objection_days", "successor", "archive"):
        assert RENDER.count(f'common("{field}")') >= 2, (
            f"{field} is not tested in both halves, so the two can disagree"
        )
    assert RENDER.count('common("version")') == 2, "the version is not chosen the same way"


def test_the_binding_english_is_built_by_the_same_code_as_the_translation() -> None:
    """The rulebook is the terms and the English text is the binding one.

    So it is one click away, once per peril rather than once per sentence: a
    reader who wants the binding wording wants all of it, and eleven toggles
    in one panel is a page of controls. Written as per-sentence toggles first,
    which added 1,500px to the page.

    Both readings come out of one function given a way to say a sentence.
    Two functions would drift, and the one that drifted would be the one
    nobody reads until it decides money.
    """
    assert "rows(x,false)" in RENDER.replace(" ", ""), "the translated rows are built some other way"
    assert "rows(x,true)" in RENDER.replace(" ", ""), "the binding English is not built from the same rows"
    assert RENDER.count("function rows(") == 1, "there is more than one row builder to drift apart"
    assert RENDER.count("function sharedRows(") == 1
    for body in ("sharedRows(perils[keys[0]],false)", "sharedRows(perils[keys[0]],true)"):
        assert body.replace(" ", "") in RENDER.replace(" ", ""), body
    # And it is not offered to a reader who is already reading the English.
    assert 'if(LANG==="en"' in RENDER.replace(" ", ""), (
        "an English reader is offered a toggle onto the text already on screen"
    )


def test_the_six_stations_are_type_and_not_a_picture() -> None:
    """A drawing shrinks with its frame; type does not.

    Drawn, the six stations sat in a 760 unit picture, which a 390px phone
    scales to 342px and puts the legend at four and a half pixels. A legend
    nobody on a phone can read is a legend the page does not have. As boxes
    they reflow to one column and keep their size.

    The same drawing also cut its prose into hand placed rows, which made
    "That reading is not used. The" a translatable string of its own; that is
    not a sentence in any language, and no translation could re-break it.
    """
    assert "<svg" not in VIEW, "the stations are a picture again, and a picture shrinks"
    assert VIEW.count('<ol class="stations">') == 1, "the six stations are not written"
    assert VIEW.count("<li") == 6, "there are not six stations"
    # An ordered list, because six steps in order is what a screen reader
    # should hear, not six boxes.
    assert '<div class="s"' in VIEW
    assert '<figcaption class="stops">' in VIEW, "the three stops are not written anywhere"

    region = re.search(
        r"== scoped styles for #view-rules, begin ==(.*?)== scoped styles, end ==", PAGE, re.S)
    assert region, "the page's own styles are not marked as its own"
    styles = region.group(1)
    # One column by default and more only where there is room, so the narrow
    # case is the one that needs no media query to be right.
    assert ".stations{display:grid;gap:10px;grid-template-columns:minmax(0,1fr);" in styles
    many = re.search(r"@media \(min-width:(\d+)px\)\{\.stations\{grid-template-columns:repeat\(3", styles)
    assert many and int(many.group(1)) >= 600, "three across on a phone is three columns of nothing"


def test_the_rulebook_reads_at_a_readable_measure() -> None:
    """Both ends of it.

    The shared key and value grid fits as many 150px columns as it will hold,
    which is right for a name beside an amount and wrong for a paragraph: on
    this page it made columns twenty two characters wide, four words to a line.
    The page therefore wears a modifier of its own rather than bending the
    class thirteen other places wear.
    """
    assert 'class="kvs rulebook"' in RENDER, "the rulebook rows wear the shared grid unmodified"
    region = re.search(
        r"== scoped styles for #view-rules, begin ==(.*?)== scoped styles, end ==", PAGE, re.S)
    assert region, "the page's own styles are not marked as its own"
    assert ".kvs.rulebook{grid-template-columns:minmax(0,1fr)" in region.group(1)
    # The site has one definition of a readable line now, and this page uses
    # it rather than a number of its own. Written as the literal 72ch when
    # this page was built, which is how it caught the change: a ch is the
    # width of a zero, so 72 of them held ninety eight characters.
    assert ".kvs.rulebook .v{max-width:var(--measure)}" in region.group(1)


def test_an_anchor_inside_the_page_is_not_read_as_a_route() -> None:
    """A hash router and an in-page anchor want the same character.

    Routes are written "#/rules"; an anchor is written "#main". The router
    reads what follows the hash, finds no screen of that name, and falls
    through to "/", so following an anchor took the reader home. The skip link
    at the top of the document did that from every page, and it exists so that
    somebody on a keyboard can reach the content of the page they are on. The
    rulebook's index of perils was about to do the same.

    Held here rather than on the rules page alone, because the fault belongs
    to the router and the next anchor written anywhere would inherit it.
    """
    handler = re.search(
        r"addEventListener\(\"click\",function\(e\)\{(.{0,1200}?)\n\}\);", PAGE, re.S)
    assert handler, "nothing keeps an in-page anchor away from the router"
    body = handler.group(1)
    assert 'name.charAt(0)==="/"' in body, "the handler does not leave routes to the router"
    assert "e.preventDefault()" in body, "the handler lets the hash change anyway"
    assert "scrollIntoView" in body and "focus" in body, "the anchor does not take the reader there"

    # And every anchor the page writes names something that exists.
    routes = set(re.findall(r'"(/[a-z/]*)":"view-', PAGE))
    fragments = {h[1:] for h in re.findall(r'href="(#[^"\'+]*)"', PAGE)}
    for frag in sorted(fragments):
        if not frag or frag.startswith("/"):
            assert not frag or frag in routes or frag.rstrip("/") in routes, f"#{frag} is no screen"
        else:
            assert f'id="{frag}"' in PAGE, f"#{frag} names nothing in the document"
