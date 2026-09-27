"""What the chain this protocol runs on has published.

The front page names Rialo. A reader who wants to know what that means should
be able to see what Rialo is actually doing, and the only open source for it is
Rialo's own front page: the documentation is behind a sign in, the blog serves
nothing to a fetcher, and /blog/rss.xml answers with HTML. So the page is read
and the cards on it are parsed, which means these tests are about the two ways
that goes wrong -- a page that changed shape, and a source that stops answering
-- rather than about the words on any particular card.
"""

from __future__ import annotations

import time
from pathlib import Path

from clause.live import Feed, parse_rialo, rialo_feed

FIXTURE = Path(__file__).parent / "feeds" / "rialo_home.html"
PAGE = FIXTURE.read_bytes()


def test_both_kinds_of_writing_are_read() -> None:
    """Research carries a number and an opening line; a note carries a date."""
    rows = parse_rialo(PAGE)
    kinds = {row["kind"] for row in rows}
    assert kinds == {"research", "note"}, kinds
    research = [r for r in rows if r["kind"] == "research"]
    notes = [r for r in rows if r["kind"] == "note"]
    assert len(research) >= 10 and len(notes) >= 3, (len(research), len(notes))
    first = research[0]
    assert first["number"] and first["when"] and first["summary"], first
    assert notes[0]["when"], notes[0]


def test_every_row_can_be_opened_and_read() -> None:
    """A half empty card is worse than one fewer card."""
    for row in parse_rialo(PAGE):
        assert row["title"], row
        assert row["url"].startswith("https://www.rialo.io/posts/"), row


#: The same piece, written once as a research card and once as a note. Today's
#: front page does not do this -- the one link it repeats is in a banner this
#: parser never reads -- so a fixture is the only way to hold the rule, and
#: without one the check passes whether or not the code does anything.
BOTH_SHAPES = b"""
<article class="docs-card">
  <span class="card-label">001</span><span class="card-date">Apr 2026</span>
  <h3 class="card-title">Reactive Transactions</h3>
  <p class="card-description">An opening line.</p>
  <a href="https://www.rialo.io/posts/reactive" class="card-link"><span>Read</span></a>
</article>
<a href="/posts/reactive" class="blog-entry">
  <time class="entry-date">Apr 20, 2026</time>
  <h3 class="entry-title">Reactive Transactions</h3>
</a>
<a href="/posts/something-else" class="blog-entry">
  <time class="entry-date">Apr 22, 2026</time>
  <h3 class="entry-title">Something else</h3>
</a>
"""


def test_nothing_is_listed_twice() -> None:
    """A piece featured in both shapes is one piece, not two.

    The two shapes also spell the address differently -- one absolute, one
    relative -- so this holds that they are compared after being made the
    same and not before.
    """
    rows = parse_rialo(BOTH_SHAPES)
    urls = [row["url"] for row in rows]
    assert urls == ["https://www.rialo.io/posts/reactive",
                    "https://www.rialo.io/posts/something-else"], urls
    assert len(urls) == len(set(urls))
    # And on the real page, still nothing twice.
    live = [row["url"] for row in parse_rialo(PAGE)]
    assert len(live) == len(set(live))


def test_a_page_that_changed_shape_says_nothing_rather_than_nonsense() -> None:
    """Someone else's markup is not a contract. When it moves, the right
    answer is an empty list, which the feed reports as stale."""
    assert parse_rialo(b"<html><body><p>Meet Rialo.</p></body></html>") == []
    assert parse_rialo(b"") == []
    half = b'<article class="docs-card"><h3 class="card-title">No link here</h3></article>'
    assert parse_rialo(half) == []


def test_the_source_is_read_a_few_times_a_day_not_a_few_times_a_minute() -> None:
    """This is writing, not weather, and it is somebody else's server."""
    calls = []

    def fetcher(url):
        calls.append(url)
        return PAGE

    feed = rialo_feed(fetcher=fetcher)
    now = time.time()
    for _ in range(5):
        feed.read(now=now)
    assert len(calls) == 1, calls
    assert feed.interval >= 3600.0, feed.interval
    feed.read(now=now + feed.interval + 1)
    assert len(calls) == 2, calls


def test_a_source_that_stops_answering_does_not_empty_the_list() -> None:
    """The last thing Rialo published is still the last thing it published."""
    state = {"up": True}

    def fetcher(url):
        if not state["up"]:
            raise OSError("no")
        return PAGE

    feed = rialo_feed(fetcher=fetcher)
    now = time.time()
    first = feed.read(now=now)
    assert first["items"] and not first["stale"]
    state["up"] = False
    later = feed.read(now=now + feed.interval + 1)
    assert later["items"] == first["items"]
    assert later["stale"] is True
