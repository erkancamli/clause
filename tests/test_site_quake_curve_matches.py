"""The earthquake levels the page draws, against the levels the contract holds.

Measured across every building year from 1900, both indices, inside Türkiye
and out: 106 of 254 cases disagreed. A pre-1981 New York flat read
6.63 / 7.63 / 8.63 on the page and 6.62 / 7.62 / 8.62 on the contract and in
the chain's own predicate. Between 1981 and 2005 on the magnitude index it was
5.43 / 6.43 / 6.93 against 5.42 / 6.42 / 6.92.

The cause is where the rounding happens, not what it rounds. The protocol
rounds twice: ``vulnerability()`` returns the shift to two places,
``curve_for`` subtracts it and rounds the level to two places, and for the
magnitude index the magnitude step is rounded before that. The page rounded
once, at the end. Turkish buildings agree either way, which is why nobody
saw it: the shifts from the Turkish table have no half cent in them.

This runs the page's own arithmetic in node against the protocol's, for every
year and both indices, so a third rounding written anywhere in either one
fails here rather than on a policy.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from clause.perils import EARTHQUAKE
from clause.protocol.valuation import THIS_YEAR, schedule as _schedule

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site" / "app"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def source(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def without_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:\w])//[^\n]*", "", src)


def body_of(src: str, name: str) -> str:
    at = src.index(f"function {name}(")
    return src[at:src.index("\n}", at) + 2]


def literal(src: str, name: str) -> str:
    at = src.index(f"var {name}=")
    return src[at:src.index("};", at) + 2]


def the_pages_levels(cases: list[dict]) -> list[list[float]]:
    """structure() and homeAge() as the page ships them, run as they are."""
    model = without_comments(source("10-model.js"))
    flow_js = without_comments(source("60-cover-flow.js"))
    risk = without_comments(source("70-what-is-at-risk.js"))
    program = """
CURVES_LITERAL
var flow = null, VALUATION = null, THE_CASE = null;
function riskCountry(){ return THE_CASE.country; }
function shakingIndex(){ return THE_CASE.shaking; }
function carCurve(){ return null; }
function stormCurve(){ return null; }
function nearestStation(){ return null; }
function coordinates(){ return {latitude: 0, longitude: 0}; }
var STATIONS = {};
PROTOCOL_YEAR
HOME_AGE
STRUCTURE
var out = CASES.map(function(c){
  THE_CASE = c;
  flow = {peril: "quake", size: {kind: "home", valid: true, builtYear: c.built}};
  VALUATION = VALUATION_LITERAL;
  return structure().pts.map(function(p){ return p[0]; });
});
console.log(JSON.stringify(out));
"""
    program = (program
               .replace("CURVES_LITERAL", literal(model, "CURVES"))
               .replace("PROTOCOL_YEAR", body_of(risk, "protocolYear"))
               .replace("HOME_AGE", body_of(risk, "homeAge"))
               .replace("STRUCTURE", body_of(flow_js, "structure"))
               .replace("VALUATION_LITERAL",
                        json.dumps({"home_age": _schedule()["home_age"],
                                    "this_year": THIS_YEAR,
                                    "built": [1900, THIS_YEAR]}))
               .replace("CASES", json.dumps(cases)))
    done = subprocess.run([NODE, "-e", program], capture_output=True, text=True,
                          timeout=60, check=True)
    return json.loads(done.stdout)


def the_contracts_levels(case: dict) -> list[float]:
    inside = case["country"] == "TR"
    subject = EARTHQUAKE.validate_subject({
        "latitude": 41.0 if inside else 40.7,
        "longitude": 29.0 if inside else -74.0,
        "radius_km": 50.0, "built": case["built"],
        "index": "shaking" if case["shaking"] else "magnitude",
    })
    return [round(point.level, 2)
            for point in EARTHQUAKE.curve_for(subject).breakpoints]


EVERY_CASE = [{"built": year, "country": country, "shaking": shaking}
              for country in ("TR", "US")
              for year in range(1900, THIS_YEAR + 1)
              for shaking in (True, False)]


def test_every_year_and_both_indices_agree() -> None:
    said = the_pages_levels(EVERY_CASE)
    assert len(said) == len(EVERY_CASE)
    wrong = []
    for case, levels in zip(EVERY_CASE, said):
        want = the_contracts_levels(case)
        if [round(v, 2) for v in levels] != want:
            wrong.append(f"{case['country']} built {case['built']} "
                         f"{'shaking' if case['shaking'] else 'magnitude'}: "
                         f"page {levels} contract {want}")
    assert not wrong, f"{len(wrong)} of {len(EVERY_CASE)}:\n" + "\n".join(wrong[:8])


def test_the_two_cases_that_were_wrong_are_named() -> None:
    """The regression itself, so a reader of this file sees the numbers."""
    pre_1981_shaking = {"built": 1900, "country": "US", "shaking": True}
    mid_magnitude = {"built": 1981, "country": "US", "shaking": False}
    page = the_pages_levels([pre_1981_shaking, mid_magnitude])
    assert [round(v, 2) for v in page[0]] == [6.62, 7.62, 8.62]
    assert [round(v, 2) for v in page[1]] == [5.42, 6.42, 6.92]


def test_the_predicate_panel_reads_the_curve_and_names_the_right_field() -> None:
    """It had max_magnitude and 5.5 written into it, for both indices, under
    "what the chain is actually asked to hold"."""
    said = without_comments(body_of(without_comments(source("60-cover-flow.js")),
                                    "predicateHtml"))
    quake = said[said.index('flow.peril==="quake"'):said.index('flow.peril==="car"')]
    assert "max_magnitude &gt;= 5.5" not in quake
    assert 'shakingIndex()?"mmi":"max_magnitude"' in quake.replace(" ", "")
    assert "structure().pts[0][0]" in quake


def test_the_topic_is_the_protocols_own_reference_where_it_has_one() -> None:
    """Every address the page can invent names a .example host, which is the
    demonstration's reserved domain and does not resolve."""
    said = body_of(without_comments(source("60-cover-flow.js")), "reference")
    assert "flow.quoted.data_source" in said.replace(" ", "")
    assert said.index("data_source") < said.index(".example")
