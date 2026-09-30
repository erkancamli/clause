"""What a reader declares is at risk, and what the page lets them declare.

A reader insured a flat, went back to the first question, chose a flight
instead, and was carried all the way to the price and the contract before the
protocol refused the purchase with "http 422". The figure sent was the flat's:
a six figure sum against a flight, where a trip is capped at 20,000.

Two things put it there. The declaration opened at a made up 150,000 that
nobody had entered, and a change of peril cleared every field of the
declaration except the figure. A third let it through: the slider that offers
the figure was bounded by four times the largest cover rather than by the
bounds the protocol publishes for exactly this purpose.

These are static checks over the page. What they stand for -- that the flat's
value does not reach the flight -- is measured in a browser by walking that
path: 118,737 before, 1,000 after.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import page_assembled

SITE = Path(__file__).resolve().parent.parent / "site"
PAGE = page_assembled()


def _reset() -> str:
    """The block a change of peril runs."""
    at = PAGE.index("function choosePeril(key){")
    return PAGE[at : PAGE.index("goStep(2);", at)]


def _interest_fields() -> set[str]:
    """Every field the declaration is made of, from its own initialiser."""
    start = PAGE.index('  interest:{what:""')
    body = PAGE[start + len("  interest:{") : PAGE.index("},", start)]
    return {m.group(1) for m in re.finditer(r"(?:^|,)\s*(\w+)\s*:", body)}


def test_nothing_is_declared_until_somebody_declares_it() -> None:
    """The figure a reader never entered is not a declaration."""
    start = PAGE.index('  interest:{what:""')
    body = PAGE[start : PAGE.index("},", start)]
    value = re.search(r"\bvalue\s*:\s*([\d_]+)", body)
    assert value, "the declaration has no opening figure at all"
    assert int(value.group(1).replace("_", "")) == 0, (
        f"the declaration opens at {value.group(1)}, which nobody entered"
    )


def test_a_change_of_peril_clears_the_whole_declaration() -> None:
    """A flat in Kadıköy is not what is at risk on a flight -- and neither is
    what the flat was worth.

    Named field by field against the declaration's own initialiser, so a field
    added later is covered by this too rather than quietly kept.
    """
    reset = _reset()
    kept = {"country"}  # where the reader is does not change with the peril
    for field in _interest_fields() - kept:
        assert f"flow.interest.{field}=" in reset, (
            f"a change of peril keeps flow.interest.{field} from the last policy"
        )


def test_the_figure_offered_is_one_the_protocol_will_accept() -> None:
    """The protocol publishes its bounds so the page can hold the reader to
    them before the contract, not after."""
    at = PAGE.index("function valueRange(){")
    body = PAGE[at : PAGE.index("\n}", at)]
    assert "VALUATION[VALUE_BOUNDS[flow.peril]]" in body, (
        "the range is not taken from the protocol's published bounds"
    )
    assert "Math.min(" in body and "Math.max(" in body, (
        "the published bounds are read but not applied"
    )
    kinds = re.search(r"var VALUE_BOUNDS=\{([^}]*)\}", PAGE)
    assert kinds, "nothing maps a peril to the figure it declares"
    for peril, kind in (("flight", "trip"), ("car", "vehicle")):
        assert f'{peril}:"{kind}"' in kinds.group(1).replace(" ", ""), (
            f"{peril} is not held to the protocol's {kind} bounds"
        )


def test_the_page_holds_those_bounds_before_the_protocol_answers() -> None:
    """/api/valuation arrives after the first render, so the fallback carries
    them too or the slider is wrong until it does."""
    at = PAGE.index("var VALUATION={")
    body = PAGE[at : PAGE.index("var VALUATION_READ", at)]
    for kind in ("trip", "vehicle"):
        assert re.search(rf"\b{kind}:\s*\[\s*[\d.]+\s*,\s*[\d.]+\s*\]", body), (
            f"the page has no {kind} bounds to use before the protocol answers"
        )
