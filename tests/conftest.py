
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


def page_assembled() -> str:
    """The page as a browser ends up with it: markup, styles and script in one.

    site/index.html is not a page a browser can run. The styles are nine files
    listed there, and the script is twenty-three parts of a single closure,
    also listed there; the build joins both where they are listed and
    `site/build.py --dev` does the same without minifying. A test that asks a
    question about the page, and does not care which of the three the answer is
    written in, should ask it of the whole thing. Asking site/index.html alone
    made eight tests pass while reading a stylesheet that was no longer there.
    """
    import pathlib
    import re

    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    page = (site / "index.html").read_text(encoding="utf-8")

    styles = re.sub(r"url\(\.\./", "url(", stylesheet())
    # A replacement is given as a function: the stylesheet and the script are
    # full of backslashes, and re.sub reads a backslash in a replacement string
    # as a group reference.
    page = re.sub(r'(?:[ \t]*<link rel="stylesheet" href="styles/[^"]+">\n?)+',
                  lambda _: f"<style>{styles}</style>\n", page, count=1)

    parts = re.findall(r'<script data-part="(app/[^"]+)"></script>', page)
    assert parts, "the page lists no script part"
    script = "".join((site / p).read_text(encoding="utf-8") for p in parts)
    return re.sub(r'(?:[ \t]*<script data-part="app/[^"]+"></script>\n?)+',
                  lambda _: f"<script>{script}</script>\n", page, count=1)
