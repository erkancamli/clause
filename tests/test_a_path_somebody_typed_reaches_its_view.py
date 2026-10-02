"""clause.insure/proof is what people write. It used to be a 404.

The page routes on the fragment, so each screen's own address is
clause.insure/#/proof, and nothing on the site ever links to it any other
way. People still do. A path typed from memory, a link pasted into a message
with the # dropped, a line read out loud: every one of them arrives without
the fragment, and every one of them reached the host's "Page not found",
which to the person holding the link is a broken site rather than a site
whose addresses have a # in them.

Measured on live before the fix: /proof and /faq both 404.

So each route is redirected to its fragment, and these tests are what keeps
the redirect list and the router's own list of screens from drifting apart --
the failure that would otherwise show up as one screen quietly 404ing again
some months after somebody added it.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

SITE = pathlib.Path(__file__).parent.parent / "site"


def views() -> set[str]:
    """Every route the page can show, read off the router itself."""
    source = (SITE / "app" / "30-routing.js").read_text(encoding="utf-8")
    found = set(re.findall(r'"(/[a-z-]*)":"view-', source))
    assert len(found) > 10, "the router's route table was not found"
    return found


def redirects() -> dict[str, dict]:
    with (SITE / "netlify.toml").open("rb") as handle:
        config = tomllib.load(handle)
    return {rule["from"]: rule for rule in config.get("redirects", [])}


def test_every_screen_has_a_path_that_reaches_it() -> None:
    missing = sorted(route for route in views() - {"/"}
                     if route not in redirects())

    assert not missing, f"typing these paths reaches a 404: {missing}"


def test_a_path_is_sent_to_its_own_fragment() -> None:
    rules = redirects()

    assert rules["/proof"]["to"] == "/#/proof"
    assert rules["/faq"]["to"] == "/#/faq"
    for route, rule in rules.items():
        assert rule["to"] == f"/#{route}", route


def test_the_redirect_is_found_and_not_moved() -> None:
    """A permanent one sits in the browser's cache and would outlast the
    decision to route on the fragment at all."""
    for route, rule in redirects().items():
        assert rule["status"] == 302, route


def test_no_redirect_points_at_a_screen_that_is_gone() -> None:
    """The other direction: a route deleted from the router leaves a redirect
    sending people to a fragment the page no longer knows, which lands them
    on the home screen with no hint of why."""
    known = views()
    stale = sorted(route for route in redirects() if route not in known)

    assert not stale, f"redirected to screens that no longer exist: {stale}"
