"""The page about the chain this protocol runs on.

The front page said "Built on Rialo" and nothing else, which tells a reader a
logo rather than a fact. This page says what is actually true, and the danger
with a page like that is not that it looks wrong -- it is that it goes quietly
untrue: a method renamed in the client, a list of Rialo's writing frozen into
the markup a year ago, a claim of Rialo's repeated as though this protocol had
measured it.

So these hold the page against the code and against the protocol, rather than
against a screenshot.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import page_assembled

ROOT = Path(__file__).resolve().parent.parent
PAGE = page_assembled()
CLIENT = (ROOT / "clause" / "rpc" / "client.py").read_text(encoding="utf-8")

#: The part of the page that is this view, so a rule about it is about it.
VIEW = PAGE[PAGE.index('<section class="view" id="view-rialo">'):]
VIEW = VIEW[: VIEW.index("</section>\n\n<!--")]


def test_the_page_is_reachable_and_named() -> None:
    assert '"/rialo":"view-rialo"' in PAGE, "the page is not routed"
    assert '<a href="#/rialo" data-route="/rialo"' in PAGE, "the page is not in the menu"
    assert VIEW.count("<h1") == 1, "a screen takes its name from its one first-level heading"


def test_the_methods_named_on_the_page_are_the_ones_the_client_calls() -> None:
    """A page that names three calls is making a claim about the code.

    Only the block that claims to be calls: elsewhere the page sets a quorum,
    a median and a set of latch filters in the same face, and none of those is
    a method on the client.

    Renaming one in the client and not here would leave the page telling a
    reader something that stopped being true, which is worse than telling them
    nothing.
    """
    at = VIEW.index('id="rialo-rpc"')
    block = VIEW[at : VIEW.index("</div>\n      <p", at)]
    shown = set(re.findall(r'<code class="mono">(\w+)</code>', block))
    assert shown, "the page names no calls at all"
    called = set(re.findall(r'"(get_\w+)": MethodGroup\(', CLIENT))
    assert shown <= called, f"the page names calls the client does not make: {shown - called}"
    # And these three in particular, because they are the reactive machinery
    # and the reason this page exists.
    assert {"get_subscription", "get_triggered_transactions", "get_workflow_lineage"} <= shown


def test_what_rialo_has_published_is_read_and_not_remembered() -> None:
    """A list frozen into the markup is a list that is wrong by next month.

    The rows come from the protocol, which reads Rialo's front page; nothing
    about any particular piece of writing belongs in the page's source.
    """
    assert 'api("/api/live/rialo"' in PAGE, "the page does not read the protocol"
    assert 'id="rialo-out"' in VIEW and "renderRialo" in PAGE
    body = re.sub(r"<!--.*?-->", "", VIEW, flags=re.S)
    for frozen in ("Supermodularity", "Gauss", "Double Marginalization",
                   "Project 1337", "Threshold Cryptography:"):
        assert frozen not in body, f"{frozen!r} is written into the page rather than read"


def test_rialos_claims_are_marked_as_rialos() -> None:
    """The figures on this page are the chain's word, not this protocol's
    measurement of it, and the page has to say so where the figures are."""
    at = VIEW.index("What Rialo says about itself")
    band = VIEW[at : VIEW.index("</div>", VIEW.index("rialo-figs", at))]
    assert "Rialo's published figures" in band
    assert "not this protocol's measurements" in band


def test_the_page_says_what_is_not_used() -> None:
    """A page listing only what is used is a brochure. This one is not."""
    assert "What this protocol does not use, yet" in VIEW
    at = VIEW.index("What this protocol does not use, yet")
    band = VIEW[at : at + 900]
    for absent in ("privacy", "threshold cryptography"):
        assert absent in band.lower(), f"{absent} is not owned up to"


def test_every_sentence_on_the_page_can_be_translated() -> None:
    """Six languages, and a page added later is not exempt from that."""
    sentences = re.findall(r"data-i18n[^>]*>([^<]{12,})<", VIEW)
    assert len(sentences) >= 20, f"only {len(sentences)} marked sentences"
    import json

    for lang in ("tr", "de", "fr", "es", "ru", "ja"):
        said = json.loads((ROOT / "site" / "i18n" / f"{lang}.json")
                          .read_text(encoding="utf-8"))["strings"]
        for line in sentences:
            text = " ".join(line.split())
            assert said.get(text), f"{lang} has no words for {text[:44]!r}"


def test_the_copy_does_not_write_with_a_dash_where_punctuation_belongs() -> None:
    """An em dash standing in for a comma, a colon or a full stop.

    It is a tic rather than an error, and a reader who notices it stops reading
    the sentence and starts reading the writer. Every one of them on this site
    was a sentence that wanted ordinary punctuation, so they were rewritten
    rather than swapped for a hyphen.

    Russian is exempt, and deliberately: there the dash is grammar, standing in
    for the copula that the language leaves out, and removing it would leave
    122 sentences ungrammatical. The rule is about English prose and the
    translations that mirrored it, not about a language's own punctuation.
    """
    import json

    seen = []
    for m in re.finditer(r"data-i18n[^>]*>([^<]*—[^<]*)<", PAGE):
        seen.append(" ".join(m.group(1).split()))
    for m in re.finditer(r'[tN]\("([^"]*—[^"]*)"', PAGE):
        seen.append(m.group(1))
    assert not seen, f"an em dash in the copy a reader sees: {seen[:2]}"

    for lang in ("tr", "de", "fr", "es", "ja"):
        said = json.loads((ROOT / "site" / "i18n" / f"{lang}.json")
                          .read_text(encoding="utf-8"))["strings"]
        bad = [k for k, v in said.items() if "—" in k or "—" in v]
        assert not bad, f"{lang} still writes with a dash: {bad[:2]}"


def test_the_page_keeps_its_own_styles_inside_a_marked_region() -> None:
    """Whose rules these are is held in tests/test_site_scoped_styles.py.

    That file reads the markers rather than this page, so every page that
    grows styles of its own is covered by it. What is left here is only that
    this page still has such a region to be covered by: written the other way
    round, deleting the markers would take the guarantee with them and no test
    would say so.
    """
    assert PAGE.count("== scoped styles for #view-rialo, begin ==") == 2
