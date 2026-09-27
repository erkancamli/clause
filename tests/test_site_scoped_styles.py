"""A class selector reaches everything wearing that class, on every screen.

The Rialo page introduced a two column row and called it .said. So did the
hero's five beats, and had since long before that page existed, so the rule
reached all seven: a 390px box became a two column grid whose second column
was 26rem, the first collapsed, and the policy's own sentence came out one
character to a line on the home page. It shipped, and a reader found it
before any test did.

What went wrong is not the name. It is that a rule written for one screen was
declared where it could reach every screen. So the page marks the regions that
belong to a single view:

    /* == scoped styles for #view-rules, begin == */
    ...
    /* == scoped styles, end == */

and this file holds the promise those markers make. Written against the
markers rather than against a list of class prefixes, because a list of
prefixes is the answer written into the question: the first version of this
test chose "the page's classes" from such a list, and passed with the
collision put back.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

#: A marked region and the view it says it is for.
REGION = re.compile(
    r"== scoped styles for #(view-[a-z-]+), begin ==(.*?)== scoped styles, end ==",
    re.S,
)


def _regions() -> dict[str, list[str]]:
    """Every marked region, gathered under the view it names.

    A view may have more than one: a page's rules are written next to the
    shared rules they modify, not collected at the bottom of the sheet.
    """
    found: dict[str, list[str]] = {}
    for view, body in REGION.findall(PAGE):
        found.setdefault(view, []).append(body)
    return found


def _view(view: str) -> str:
    """The markup of one view, so a rule about it is about it."""
    at = PAGE.index(f'<section class="view" id="{view}">')
    return PAGE[at : PAGE.index("\n</section>", at)]


def _declared(bodies: list[str]) -> set[frozenset[str]]:
    """What a region can reach, as the set of classes an element must wear.

    Only the leftmost compound of a selector reaches: anything further right is
    already scoped by it, so `.pub .no` cannot touch a `.verdict.no` somewhere
    else. And a compound reaches an element only if the element wears all of
    it: `.kvs.rulebook` leaves the thirteen plain .kvs alone, while a bare
    `.said` is a compound of one and reaches every .said there is, which is
    the whole of what went wrong.
    """
    compounds: set[frozenset[str]] = set()
    for body in bodies:
        # The marker itself sits inside a comment, so the body opens mid-prose
        # and its `*/` has no `/*`. Put one back, or the prose runs on into the
        # region's first rule and swallows it: written without this, the test
        # passed with the first rule of every region invisible to it.
        stripped = re.sub(r"/\*.*?\*/", "", "/*" + body, flags=re.S)
        for group in re.findall(r"(?:^|[},])\s*([^{}@]+?)\{", stripped, re.M):
            for selector in group.split(","):
                first = re.split(r"[ >+~]", selector.strip(), 1)[0]
                worn = re.findall(r"\.([a-z][\w-]*)", first)
                if worn:
                    compounds.add(frozenset(worn))
    return compounds


def _wearers(classes: frozenset[str], markup: str) -> list[str]:
    """Every class attribute in this markup that wears all of these classes."""
    found = []
    for attr in re.findall(r'class="([^"]*)"', markup):
        if classes <= set(attr.split()):
            found.append(attr)
    return found


def test_the_page_marks_the_regions_that_belong_to_one_screen() -> None:
    regions = _regions()
    assert regions, "no scoped style region is marked at all"
    assert PAGE.count("== scoped styles, end ==") == sum(
        len(bodies) for bodies in regions.values()
    ), "a region is closed without being opened for a named view"
    for view in regions:
        assert f'<section class="view" id="{view}">' in PAGE, (
            f"{view} has styles of its own and no screen to wear them"
        )


def test_no_class_one_screen_lays_out_is_worn_on_another() -> None:
    for view, bodies in sorted(_regions().items()):
        declared = _declared(bodies)
        assert declared, f"{view}'s style regions declare no classes"

        # Elsewhere means another screen's markup. A view's own renderer
        # writes its rows from script, so script is not elsewhere.
        others = re.sub(
            r"<script\b.*?</script>", "", PAGE.replace(_view(view), ""), flags=re.S
        )
        trespass = {}
        for classes in sorted(declared, key=sorted):
            worn = _wearers(classes, others)
            if worn:
                trespass[".".join(sorted(classes))] = worn[:2]
        assert not trespass, (
            f"declared for {view} and worn on another screen: {trespass!r}"
        )


def test_a_scoped_rule_is_worn_by_the_screen_it_was_written_for() -> None:
    """A rule nothing wears is a rule nobody can see is wrong.

    The .said collision was found by a reader looking at the home page. A
    scoped rule that has lost the markup it was written for cannot be found
    that way at all, so it is held here instead.
    """
    for view, bodies in sorted(_regions().items()):
        mine = _view(view)
        scripts = "".join(re.findall(r"<script\b.*?</script>", PAGE, flags=re.S))
        for classes in sorted(_declared(bodies), key=sorted):
            shown = ".".join(sorted(classes))
            assert _wearers(classes, mine) or _wearers(classes, scripts), (
                f".{shown} is declared for {view} and nothing wears it"
            )
