"""The line between what a buyer loads and what only a desk opens.

Measured over a whole purchase, from the home page to the signing step, a
buyer runs 208,921 bytes of the page's 598,203 and never reaches the other
389,282. Three surfaces hold most of that and no buyer enters them: a
company's desk and the operator's screens, the proof register and the chain
beside it, and the profile. Emptying the three and building takes the
published page from 623,725 bytes to 479,626, and the wire, brotli, from
137,548 to 107,531.

They could not be fetched on demand while sixteen declarations written inside
them were used outside them: the cover flow read the buyer's saved things, My
cover drew its payout, mandate and funding panels from there, signing out
cleared the operator's session through it. Those moved to the side of the line
that is always in the page, and moving them pulled sixteen more after them.

This holds the line. It is not a style rule: a single new name declared on the
wrong side is a file that can no longer be deferred, and nothing else would
say so until someone tried and measured.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "site" / "app"

#: Fetched when somebody opens them, and not before.
DEFERRABLE = {
    "45-profile.js",
    "85-company-and-operator.js",
    "90-proof-and-chain.js",
}

#: What the router calls to open one. These are the interface, so they are the
#: one kind of name the rest of the page is allowed to know about.
ENTRY_POINTS = {
    "renderProfile", "renderProof", "renderInsurers", "renderAskedDocuments",
    "renderCompany", "bindOperator", "renderRules", "renderAskForm",
}


def _code(text: str) -> str:
    """The same text with comments and string bodies taken out.

    A name written in a note above a function is not a use of it, and the
    first version of this test failed on the prose that explains it.
    """
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    text = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', text)
    text = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", text)
    return text


def _parts() -> dict[str, str]:
    parts = {p.name: _code(p.read_text(encoding="utf-8")) for p in APP.glob("*.js")}
    assert parts, "there are no script parts"
    assert DEFERRABLE <= set(parts), f"missing: {DEFERRABLE - set(parts)}"
    return parts


def _declared(code: str) -> set[str]:
    """Names this part declares at the top level of the closure."""
    return ({m.group(1) for m in re.finditer(r"^function\s+([A-Za-z_$][\w$]*)", code, re.M)}
            | {m.group(1) for m in re.finditer(r"^var\s+([A-Za-z_$][\w$]*)\s*=", code, re.M)})


def test_nothing_outside_the_deferrable_parts_reaches_into_them() -> None:
    parts = _parts()
    theirs: dict[str, str] = {}
    for name in DEFERRABLE:
        for n in _declared(parts[name]):
            theirs[n] = name

    trespass: dict[str, list[str]] = {}
    for name, code in parts.items():
        if name in DEFERRABLE:
            continue
        for n, home in theirs.items():
            if n in ENTRY_POINTS or len(n) < 3:
                continue
            if re.search(r"(?<![\w$.])" + re.escape(n) + r"(?![\w$])", code):
                trespass.setdefault(f"{n} ({home})", []).append(name)

    assert not trespass, (
        "declared inside a part that is meant to be fetched on demand and used "
        f"outside it: {trespass}"
    )


def test_every_entry_point_is_declared_in_the_part_it_opens() -> None:
    """An interface nothing implements is an interface that has moved."""
    parts = _parts()
    inside = set()
    for name in DEFERRABLE:
        inside |= _declared(parts[name])
    missing = sorted(ENTRY_POINTS - inside)
    assert not missing, (
        f"named as the way into a deferrable part and declared somewhere else: {missing}"
    )
