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

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
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

    Renaming one in the client and not here would leave the page telling a
    reader something that stopped being true, which is worse than telling them
    nothing.
    """
    shown = set(re.findall(r'<code class="mono">(\w+)</code>', VIEW))
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
