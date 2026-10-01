"""The desk an insurer runs its book on is a second page.

Three of the fifteen screens are the desk: the company view, the operator view
and the register of insurers. A buyer never opens one, and on the page a buyer
downloads they were 89,268 B of script and 14,148 B of markup, measured by
building the page both ways.

They are not deferred inside the closure, and the reason is worth keeping. The
whole script is one closure, and the desk's part reads fifty-one names out of
it; those fifty-one pull in 563 declarations between them, 77% of the script,
so a self-contained desk chunk would be the whole thing twice over. Handing
the fifty-one across a boundary instead would leave a list to keep by hand,
and the day someone adds a fifty-second the desk breaks on the route an
insurer uses to run their book, with nothing to say so until somebody goes
there.

So the desk is built from these same parts with nothing taken out, and the
buyer's page is built without them.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
SOURCE = (SITE / "index.html").read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("clause_site_build", SITE / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

BUYER = build.without_the_desk(SOURCE)

#: The three screens, and the part that draws them.
VIEWS = ["view-company", "view-admin", "view-insurers"]
PART = "app/85-company-and-operator.js"


def test_the_source_marks_what_the_desk_is() -> None:
    for view in VIEWS:
        assert f'id="{view}" data-desk>' in SOURCE, view
    assert f'<script data-part="{PART}" data-desk></script>' in SOURCE


def test_the_buyers_page_has_none_of_it() -> None:
    for view in VIEWS:
        assert f'id="{view}"' not in BUYER, view
    assert PART not in BUYER
    assert "data-desk" not in BUYER


def test_the_buyers_page_keeps_every_other_screen_and_part() -> None:
    """A stripper that takes a neighbour with it is worse than none."""
    before = re.findall(r'<section class="view[^"]*" id="(view-[a-z]+)"', SOURCE)
    after = re.findall(r'<section class="view[^"]*" id="(view-[a-z]+)"', BUYER)
    assert after == [v for v in before if v not in VIEWS], after
    parts_before = re.findall(r'data-part="(app/[^"]+)"', SOURCE)
    parts_after = re.findall(r'data-part="(app/[^"]+)"', BUYER)
    assert parts_after == [p for p in parts_before if p != PART], parts_after


def test_a_part_the_build_cannot_read_stops_the_build() -> None:
    """It did not, and both pages shipped 89,268 B lighter and short a desk.

    Marking the desk's part with an attribute put something between the path
    and the closing bracket, the pattern stopped matching, and the part was
    dropped without a word.
    """
    import pytest

    broken = SOURCE.replace(f'<script data-part="{PART}" data-desk></script>',
                            f'<script data-part="{PART}" data-desk ></script >')
    with pytest.raises(SystemExit) as raised:
        build.gather_scripts(broken)
    assert "the build does not read" in str(raised.value)


def test_the_build_reads_a_part_that_carries_other_attributes() -> None:
    assert build.gather_scripts(SOURCE) != SOURCE
    joined = build.gather_scripts(SOURCE)
    assert "function renderCompany" in joined, "the desk's part was dropped"
    assert "function renderCompany" not in build.gather_scripts(BUYER)


def test_the_router_sends_the_three_routes_to_the_desks_page() -> None:
    routing = (SITE / "app" / "30-routing.js").read_text(encoding="utf-8")
    assert 'var DESK_ROUTES={"/company":1,"/insurers":1,"/admin":1};' in routing
    assert "if(DESK_ROUTES[route]&&!deskIsHere()){ goToTheDesk(route); return; }" in routing


def test_which_page_this_is_is_asked_of_the_page() -> None:
    """Not of its address, so a copy served from anywhere still answers."""
    routing = (SITE / "app" / "30-routing.js").read_text(encoding="utf-8")
    assert 'return !!document.getElementById("view-company");' in routing


def test_the_redirect_carries_the_query_string() -> None:
    """The first version dropped it, and the desk arrived asking the wrong
    host: every screen answered with a 404."""
    routing = (SITE / "app" / "30-routing.js").read_text(encoding="utf-8")
    assert 'location.replace("desk.html" + location.search + "#" + route);' in routing


def test_the_view_loop_skips_a_screen_this_page_does_not_have() -> None:
    routing = (SITE / "app" / "30-routing.js").read_text(encoding="utf-8")
    assert "var view=$(VIEWS[k]); if(!view)return;" in routing


def test_both_pages_of_one_build_carry_one_build_name() -> None:
    """Two names for one build would have one of the two tabs reloading
    itself forever, because both ask the same version.json."""
    page, name = build.stamp("x __CLAUSE_BUILD__ y")
    desk, again = build.stamp("a different page __CLAUSE_BUILD__", name)
    assert again == name
    assert name in desk


def test_the_desks_page_is_checked_every_time_like_the_other_one() -> None:
    rules = (SITE / "netlify.toml").read_text(encoding="utf-8")
    at = rules.index('for = "/desk.html"')
    assert "must-revalidate" in rules[at:at + 200]
