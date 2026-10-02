"""The figure in the sentence, against the figure the account is charged.

    "If the ground at Kadıköy shakes at intensity 6.25 or more ... you receive
     35,000 USDC, rising to 100,000 at intensity 8.25. You pay 11,758.31 USDC
     now, and nothing else ever."

The address was debited 12,087.54. The sentence passed ``q.premium``, the
pool's price, while the price row directly below it, the price bar and
``payableNow`` all add the issuing company's fronting fee, and the server
charges it. Measured on one Istanbul earthquake policy with a 100,000 limit on
a 1975 building: 329.23 short against the cheapest carrier, 1,061.36 against
the one charging nine per cent. Six sentences, one per peril, in seven
languages, on the screen where the money moves.

The arithmetic is lifted out and run, so this fails if the figure stops being
the one that leaves the account.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
FLOW = (SITE / "app" / "60-cover-flow.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def without_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:\w])//[^\n]*", "", src)


BARE = without_comments(FLOW)


def body_of(name: str) -> str:
    """One function, from its `function` to the closing brace at column one."""
    at = BARE.index(f"function {name}(")
    end = BARE.index("\n}", at) + 2
    return BARE[at:end]


def test_every_sentence_names_the_whole_price() -> None:
    said = body_of("plainSentence")
    passes = re.findall(r"premium:\s*money\(([^)]*\)?)\)", said)
    assert len(passes) == 6, f"expected six sentences, found {len(passes)}"
    assert all(p.strip() == "wholePrice()" for p in passes), passes


def test_the_whole_price_is_what_payable_now_is_built_from() -> None:
    """Two functions must not drift: one says the figure, one charges it."""
    whole, payable = body_of("wholePrice"), body_of("payableNow")
    assert "offerForPrice()" in whole
    assert "priced().premium+(offer?offer.fee:0)" in whole.replace(" ", "")
    assert "q.premium+(offer?offer.fee:0)" in payable.replace(" ", "")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_figure_is_the_premium_and_the_fee() -> None:
    cases = [
        # premium, offers, chosen carrier, what the account is charged
        {"premium": 11758.31, "offers": [{"carrier_id": "a", "fee": 329.23},
                                         {"carrier_id": "b", "fee": 1061.36}],
         "carrier": "a", "want": 12087.54},
        {"premium": 11758.31, "offers": [{"carrier_id": "a", "fee": 329.23},
                                         {"carrier_id": "b", "fee": 1061.36}],
         "carrier": "b", "want": 12819.67},
        # Nobody chosen yet: the first offer is the one they would get.
        {"premium": 1000.0, "offers": [{"carrier_id": "a", "fee": 90.0}],
         "carrier": None, "want": 1090.0},
        # No offers at all, which is the state before the protocol answers.
        {"premium": 1000.0, "offers": [], "carrier": None, "want": 1000.0},
    ]
    program = """
var flow = null;
function priced(){ return {premium: flow.premium}; }
function chosenOffer(){
  return (flow.offers||[]).filter(function(o){ return o.carrier_id===flow.carrier; })[0]||null;
}
function offerForPrice(){ return chosenOffer()||(flow.offers||[])[0]||null; }
WHOLE
console.log(JSON.stringify(CASES.map(function(c){ flow = c; return wholePrice(); })));
""".replace("WHOLE", body_of("wholePrice")).replace("CASES", json.dumps(cases))
    out = subprocess.run([NODE, "-e", program], capture_output=True, text=True,
                         timeout=30, check=True)
    # To the cent, which is what money() prints.
    assert [round(v, 2) for v in json.loads(out.stdout)] == \
        [c["want"] for c in cases]


def test_no_sentence_claims_the_fee_comes_later() -> None:
    """The words beside the figure. "Nothing else ever" is only true of a
    figure that already has the fee in it."""
    said = body_of("plainSentence")
    assert said.count("nothing else ever") == 6
    assert "before the company's fee" not in said
