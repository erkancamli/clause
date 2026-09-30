"""A part is named for what is in it, and the home page does not need the pool.

The script is one closure assembled from parts listed in site/index.html, and
the part names are the only map anyone has of what the buyer's page is made
of. 94-pool-view.js held two unrelated halves: the pool screen, and the live
reading bands the home page draws. So the home page's own part read eight
names out of a file named for a screen it has nothing to do with, and anyone
reading the parts to work out what a buyer downloads would have concluded the
pool view was part of it.

Measured when the question was asked with a parser rather than a grep: of the
12,340 B in that file, 7,596 B were the bands and 4,742 B were the pool. The
split moved the seam and nothing else; the built page came out byte for byte
the same, because the minifier takes the comments out again.
"""

from __future__ import annotations

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PAGE = (SITE / "index.html").read_text(encoding="utf-8")
PARTS = re.findall(r'<script data-part="(app/[^"]+)"></script>', PAGE)

#: What each of the two halves is for, by a name only that half can own.
POOL = ["buildMap", "fillCapBars", "startTick", "stopTick", "pushEv"]
BANDS = ["LIVE", "agoText", "bandFill", "fillNowCountries",
         "flightChip", "quakeChip", "weatherChip", "guessCountry"]


def part(name: str) -> str:
    return (SITE / "app" / name).read_text(encoding="utf-8")


def declares(src: str, name: str) -> bool:
    return bool(re.search(r"^(?:function\s+|var\s+)" + re.escape(name) + r"\b",
                          src, re.M))


def test_both_halves_are_parts_of_their_own() -> None:
    assert "app/94-pool-view.js" in PARTS
    assert "app/95-live-readings.js" in PARTS


def test_the_pool_view_holds_the_pool_and_nothing_else() -> None:
    src = part("94-pool-view.js")
    for name in POOL:
        assert declares(src, name), f"{name} left the pool view"
    for name in BANDS:
        assert not declares(src, name), f"{name} is back in the pool view"


def test_the_live_readings_hold_the_bands() -> None:
    src = part("95-live-readings.js")
    for name in BANDS:
        assert declares(src, name), f"{name} is not in the live readings"
    for name in POOL:
        assert not declares(src, name), f"{name} does not belong here"


def test_the_home_page_reads_the_bands_and_not_the_pool() -> None:
    """The reason the two were worth separating."""
    digest = part("96-digest.js")
    used = [n for n in BANDS if re.search(r"\b" + re.escape(n) + r"\b", digest)]
    assert len(used) >= 6, used
    assert not [n for n in POOL if re.search(r"\b" + re.escape(n) + r"\b", digest)]


def test_the_readings_are_in_place_before_the_page_that_draws_them() -> None:
    """One closure hoists functions, but a var is not initialised until its
    line runs, and half of what the bands are is tables."""
    assert PARTS.index("app/95-live-readings.js") < PARTS.index("app/96-digest.js")
