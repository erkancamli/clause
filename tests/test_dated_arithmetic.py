"""Arithmetic that was true in 2026 and would quietly stop being true.

Three places counted a building's or a vehicle's age from a literal 2026 while
the protocol counts it from time.gmtime().tm_year, and one published table of
year boundaries was worked out for 2026 and shipped as fact.

What would have happened on 1 January 2027, with nobody touching anything: a
building of 2006 outside Türkiye prices at hazard 1.0 on the page and 1.25 on
the server, because the server's bands are ages -- twenty years, forty-five --
and the table it published was those ages turned into years once. Two years of
buildings disagree in 2027, eight by 2030, and the measured gap on one worked
cover ceiling was 779.78 against a tolerance of 1.00.

Türkiye is unaffected either way: its bands are real building-code eras.
"""

from __future__ import annotations

import re
from pathlib import Path

from clause.protocol.valuation import (BUILT, THIS_YEAR, hazard_table,
                                       home_age_factors, schedule)

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site" / "app"


def without_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:\w])//[^\n]*", "", src)


def test_the_published_table_is_the_function_that_prices() -> None:
    """Not a copy of it: read out of it, for every year a buyer may give."""
    published = schedule()["home_age"]["hazard"]
    for country, key in (("TR", "TR"), ("", "*")):
        table = published[key]
        for built in range(BUILT[0], THIS_YEAR + 1):
            _, hazard = home_age_factors(built, country)
            said = next(f for year, f in table if built >= year)
            assert said == hazard, (
                f"{key} built {built}: table {said}, function {hazard}")


def test_the_table_moves_when_the_clock_does() -> None:
    """The reason the first test is not enough. With the year one on, a table
    of fixed years is wrong for the years on its boundaries, and this one is
    derived rather than written, so it moves."""
    import clause.protocol.valuation as valuation

    was = valuation.THIS_YEAR
    before = schedule()["home_age"]["hazard"]["*"]
    try:
        valuation.THIS_YEAR = was + 1
        # Through the schedule, because that is what is published and what the
        # page reads. Asking hazard_table directly would pass with the table
        # written back out as fixed years, which is the thing being fixed.
        moved = valuation.schedule()["home_age"]["hazard"]["*"]
        for built in range(BUILT[0], valuation.THIS_YEAR + 1):
            _, hazard = valuation.home_age_factors(built, "")
            said = next(f for year, f in moved if built >= year)
            assert said == hazard, f"built {built} with the clock at {was + 1}"
        assert moved != before, (
            "the published non-Türkiye table did not move with the clock")
    finally:
        valuation.THIS_YEAR = was


def test_the_schedule_says_which_year_it_counted_from() -> None:
    assert schedule()["this_year"] == THIS_YEAR


def test_no_page_file_counts_ages_from_a_year_of_its_own() -> None:
    """The page asks the protocol, and falls back to the browser's clock."""
    for path in sorted(SITE.glob("*.js")):
        src = without_comments(path.read_text(encoding="utf-8"))
        for found in re.finditer(r"(\d{4})\s*-\s*\w*(built|year|Year)", src):
            raise AssertionError(
                f"{path.name} counts an age from {found.group(1)}: "
                f"{found.group(0)}")


def test_the_page_takes_the_year_from_the_schedule() -> None:
    src = without_comments((SITE / "70-what-is-at-risk.js")
                           .read_text(encoding="utf-8"))
    at = src.index("function protocolYear(")
    body = src[at:src.index("\n}", at)]
    assert "VALUATION.this_year" in body
    assert "getUTCFullYear" in body
    for reader in ("function homeAge(", "function carCap("):
        start = src.index(reader)
        assert "protocolYear()" in src[start:src.index("\n}", start)], reader
