"""The pool screen showed three figures it had made up.

Across the top of the screen headed "Someone has to be able to pay" sat Block,
Policies armed and Capital in the pool. Two were a random walk: the block
started at 412,000 and gained eight to twelve a second, and the count of armed
policies drifted up and down by one. Neither had ever been asked of the
protocol, and nothing on this site read /api/chain at all, so they were not
stale figures but invented ones. Measured against the protocol: the real
height is 15,307,897 and the real count of armed policies is 10.

The third was the string 3,500,000 written into the markup. The tranche panel
replaced it when the protocol answered and left it standing when it did not,
against a real balance of 274,745,994.

This site tells a reader on seven other screens that it will not show them a
record it made up. This screen was showing three, with real labels, animated,
on the one page whose whole argument is that somebody can pay.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import page_assembled

SITE = Path(__file__).resolve().parent.parent / "site"
PAGE = page_assembled()
MARKUP = (SITE / "index.html").read_text(encoding="utf-8")
POOL = (SITE / "app" / "94-pool-view.js").read_text(encoding="utf-8")

SAYS = ("This page cannot reach the protocol, so there is nothing real to show here."
        " It will not show you a figure it made up.")


def test_nothing_stands_in_the_readouts_until_the_protocol_has_spoken() -> None:
    for rid in ("r-height", "r-armed", "r-capital"):
        found = re.search(r'id="' + rid + r'">([^<]*)<', MARKUP)
        assert found, rid
        assert found.group(1) == "&ndash;", (rid, found.group(1))


def test_the_old_invented_figures_are_gone() -> None:
    """Asked of the markup with its comments taken out.

    The comment that explains what these were names all three, so a plain
    search finds them and passes or fails for the wrong reason. The first
    version of this test dodged that with an `or` whose left side was always
    true, which is to say it could not fail at all.
    """
    plain = re.sub(r"<!--.*?-->", "", MARKUP, flags=re.S)
    for made_up in ("412,000", "1,284", "3,500,000"):
        assert made_up not in plain, made_up
    # And the walk that moved two of them.
    assert "height+=8+Math.floor(Math.random()*5)" not in PAGE
    assert "armed+=Math.random()" not in PAGE


def test_the_figures_are_read_from_the_protocol() -> None:
    assert 'api("/api/chain"' in POOL
    assert 'api("/api/pool"' in POOL
    assert "stats.height" in POOL and "stats.armed" in POOL and "pool.balance" in POOL


def test_a_figure_is_only_written_when_there_is_one() -> None:
    """A protocol that answers without a field must not leave a stale number,
    and must not write undefined into the screen either."""
    assert "if(stats.height!=null)" in POOL
    assert "if(stats.armed!=null)" in POOL
    assert "if(pool.balance!=null)" in POOL


def test_the_screen_says_so_when_it_cannot_reach_the_protocol() -> None:
    assert SAYS in PAGE
    assert 'id="pool-unreachable"' in MARKUP
    # Both ways of not knowing: never connected, and the call refused.
    assert POOL.count("poolReadoutsSay(t(") == 2


def test_not_knowing_clears_the_figures_and_fills_the_notice() -> None:
    """Both halves, asked of the one function that does them.

    Checking only that the function is called twice passed while the lines
    that fill the notice were deleted: the screen cleared its figures to
    dashes and said nothing about why.
    """
    found = re.search(r"function poolReadoutsSay\(what\)\{(.+?)\n\}", POOL, re.S)
    assert found
    body = found.group(1)
    assert '["r-height","r-armed","r-capital"]' in body
    assert '"\\u2013"' in body
    assert 'var box=$("pool-unreachable");' in body
    assert "box.hidden=!what" in body
    assert "box.textContent=what" in body


def test_the_readouts_are_asked_for_at_a_human_pace() -> None:
    """A block height that moves once a second is an animation, not a reading,
    and the protocol serves this from a cache anyway."""
    assert "setInterval(readThePool,15000)" in POOL


def test_the_sentence_is_translated_everywhere() -> None:
    for lang in ("tr", "es", "fr", "de", "ru", "ja"):
        strings = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        assert SAYS in strings, lang
        assert strings[SAYS] != SAYS, (lang, "left in English")
