
import datetime as _dt

# A departure two weeks out: flight subjects must name a date that is still
# ahead, whenever the suite runs.
FLIGHT_DATE = (_dt.date.today() + _dt.timedelta(days=14)).isoformat()


def start_cover(chain, policy) -> None:
    """Run the chain forward to the day a policy's cover starts.

    Every peril waits out its own forecast before the cover begins, so a test
    that attests a reading the moment it has bought would be measuring the
    waiting period rather than the thing it means to measure. The wait itself
    is tested in tests/test_waiting.py.
    """
    while chain.world_now(policy) < policy.starts_at:
        chain.produce_block()


def cover_has_started(policy) -> None:
    """Move a policy's start back to the day it was bought.

    Cover waits out its peril's forecast before it begins, and for a policy a
    person bought that wait runs in real days rather than the demonstration's
    accelerated ones. A test about what happens once the cover has started says
    so here instead of waiting a week for it.
    """
    policy.starts_at = policy.bought_at


def stylesheet() -> str:
    """The page's styles, as the browser ends up with them.

    They live in site/styles/ as nine files so the visual system can be worked
    on as a thing of its own, and the build puts them back into one inlined
    block in the order the page links them. A test that wants to read the
    stylesheet wants that same concatenation, not one of the nine, and reading
    it through the page's own link order means a file nobody links is a file
    nobody tests.
    """
    import pathlib
    import re

    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    page = (site / "index.html").read_text(encoding="utf-8")
    parts = re.findall(r'<link rel="stylesheet" href="(styles/[^"]+)">', page)
    assert parts, "the page links no stylesheet"
    return "".join((site / p).read_text(encoding="utf-8") for p in parts)


def page_with_styles() -> str:
    """The page as a browser ends up with it: the markup and the styles in one.

    The stylesheet is nine files in the source and one inlined block in what is
    published. A test that asks a question about the page, and does not care
    which of the two the answer is written in, should ask it of both; asking it
    of site/index.html alone made eight tests pass by reading a stylesheet that
    was no longer there.
    """
    import pathlib
    import re

    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    page = (site / "index.html").read_text(encoding="utf-8")
    styles = re.sub(r"url\(\.\./", "url(", stylesheet())
    return re.sub(r'(?:[ \t]*<link rel="stylesheet" href="styles/[^"]+">\n?)+',
                  f"<style>{styles}</style>\n", page, count=1)
