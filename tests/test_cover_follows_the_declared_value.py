"""Cover never sits above what the buyer says is at risk.

The protocol refuses cover above the value at risk, in its own words: "Cover
above the value at risk is a wager rather than an indemnity, so it is refused
rather than priced." The page has to keep the two in step, or the buyer meets
that refusal with no way to answer it.

Measured by walking the flow: a flight's cover arrives at 1,000 from the card
and the value slider's floor is 200, so dragging the slider to the bottom left
cover at 1,000 against 200 declared. The sentence that explains it is on the
fifth step, the only control that lowers cover is on the fourth, and the third
would not let the buyer past: the button read "Cannot be written" and pointed
at no field, because `at` is empty. The only escape was to drag the slider
back up, and nothing said so.

Every other path already kept them in step: the size path clamps when the
figure it derives is valid, and a car clamps through its own cap.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
RISK = (SITE / "app" / "70-what-is-at-risk.js").read_text(encoding="utf-8")
FLOW = (SITE / "app" / "60-cover-flow.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def body_of(src: str, name: str) -> str:
    at = src.index(f"function {name}(")
    return src[at:src.index("\n}", at) + 2]


def handler(element: str) -> str:
    at = RISK.index(f'$("{element}").addEventListener("input"')
    return RISK[at:RISK.index("\n});", at) + 4]


def test_the_value_slider_brings_the_cover_with_it() -> None:
    said = handler("value")
    assert "clampLimit()" in said, "a declared value the cover sits above is a dead end"
    assert "applyCarCap()" in said, "and a car still clamps through its cap"


def test_the_size_path_still_clamps() -> None:
    assert "if(z.valid) clampLimit();" in RISK


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_a_flight_dragged_to_the_floor_is_still_writable() -> None:
    """The deadlock, run: 1,000 of cover against 200 declared."""
    program = r"""
var PERILS = {flight: {limits: [200, 5000], presets: [500, 1000, 1500, 3000]}};
var flow = {peril: "flight", limit: 1000, interest: {value: 1000}};
CEILING
CLAMP
var out = [];
// The buyer drags the declared value to the slider's floor.
flow.interest.value = 200;
clampLimit();
out.push({limit: flow.limit, value: flow.interest.value});
// And back up again: cover stays where it was put, under the new ceiling.
flow.interest.value = 3000;
clampLimit();
out.push({limit: flow.limit, value: flow.interest.value});
console.log(JSON.stringify(out));
""".replace("CEILING", body_of(RISK, "coverCeiling")).replace("CLAMP", body_of(RISK, "clampLimit"))
    done = subprocess.run([NODE, "-e", program], capture_output=True, text=True,
                          timeout=30, check=True)
    at_floor, back_up = json.loads(done.stdout)
    assert at_floor["limit"] <= at_floor["value"], at_floor
    assert at_floor["limit"] == 200
    assert back_up["limit"] == 200, "raising the value does not raise the cover by itself"
    assert back_up["limit"] <= back_up["value"]


def test_the_refusal_this_avoids_is_still_the_one_that_would_fire() -> None:
    """If the protocol stops refusing this, the clamp is no longer the fix."""
    ruling = body_of(FLOW, "localRuling")
    assert "flow.limit>flow.interest.value" in ruling.replace(" ", "")
    assert "exceeds the {value} you declared at risk" in ruling
