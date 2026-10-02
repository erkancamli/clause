"""Buying a second time in the same tab, which the done screen invites.

resetFlow set ``flow.statements`` to null. Every reader treats it as a map:
the mandate dialog assigns ``flow.statements.sanctions_clear``
(44-always-loaded.js), and both purchase paths read
``flow.statements[claim]`` whenever ``flow.need`` is set (75-buying.js), which
the requirement check sets again as soon as the next purchase reaches the
third question. Where it is declared it is ``{}``, and where a change of
country clears it it is ``{}``. One line out of three made it null.

So the second purchase in a tab threw a TypeError before anything was sent,
and what the buyer was told was that the protocol could not be reached and to
check My cover -- about a purchase that had not been attempted.

The arithmetic cannot be lifted out of this one, so what is tested is the
invariant: every place that sets flow.statements sets a map, and every reader
indexes it without a guard, which is why.
"""

from __future__ import annotations

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site" / "app"


def without_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:\w])//[^\n]*", "", src)


SOURCES = {path.name: without_comments(path.read_text(encoding="utf-8"))
           for path in sorted(SITE.glob("*.js"))}


def test_nothing_ever_sets_the_statements_to_null() -> None:
    found = []
    for name, src in SOURCES.items():
        for match in re.finditer(r"flow\.statements\s*=\s*([^;]+);", src):
            found.append((name, match.group(1).strip()))
    assert found, "flow.statements is never assigned, so this test is stale"
    for name, value in found:
        assert value == "{}", f"{name} sets flow.statements to {value}"


def test_it_is_set_where_the_flow_starts_over() -> None:
    """Not just "never null": the reset has to clear it, or a statement from
    one country's purchase is carried into another's."""
    reset = SOURCES["65-place-lookup.js"]
    at = reset.index("function resetFlow")
    body = reset[at:reset.index("\n}", at)]
    assert "flow.statements={}" in body.replace(" ", "")


def test_the_readers_index_it_without_a_guard() -> None:
    """Which is why the value matters. If this stops being true the invariant
    above is no longer load bearing and this file should say so."""
    buying = SOURCES["75-buying.js"]
    assert buying.count("flow.statements[") >= 2
    for match in re.finditer(r"(.{40})flow\.statements\[", buying):
        assert "flow.statements&&" not in match.group(1)
    assert "flow.statements.sanctions_clear=" in SOURCES["44-always-loaded.js"]
