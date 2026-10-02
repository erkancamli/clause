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
    """Six sentences, and one clause between them and the money."""
    said = body_of("plainSentence")
    assert said.count("pay:payClause()") == 6, said.count("pay:payClause()")
    assert said.count("{pay}") == 6
    assert "wholePrice()" in body_of("payClause")


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


def test_nothing_else_ever_is_said_only_where_it_is_true() -> None:
    """The words beside the figure.

    "Nothing else ever" is true of a figure that already has the fee in it
    and is paid once. Under a plan it was false twice over, and the plan box
    two rows below said so: measured on a Tokyo policy, the sentence read
    10,143.15 now and nothing else ever where the contract said 10,948.52 in
    twelve instalments of 912.38.
    """
    said = body_of("payClause")
    assert said.count("nothing else ever") == 1
    assert "n<2" in said.replace(" ", ""), "and only on the one payment branch"
    assert "more payments of the same" in said
    assert body_of("plainSentence").count("nothing else ever") == 0


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_clause_under_a_plan_names_every_payment() -> None:
    """The figures the Tokyo policy should have shown, and the surcharge."""
    cases = [
        # one payment: the premium and the fee, and nothing else ever
        {"instalments": 1, "premium": 10143.15, "offers": [], "carrier": None,
         "plans": [], "want": ["10,143.15", "nothing else ever"]},
        # twelve monthly at Japan's 5%: 10,143.15 x 1.05 / 12
        {"instalments": 12, "premium": 10143.15, "offers": [], "carrier": None,
         "plans": [{"count": 1, "surcharge": 0.0}, {"count": 12, "surcharge": 0.05}],
         "want": ["887.53", "11", "10,650.31"]},
        # a plan the protocol does not offer carries no surcharge
        {"instalments": 4, "premium": 1200.0, "offers": [], "carrier": None,
         "plans": [{"count": 12, "surcharge": 0.05}],
         "want": ["300.00", "3", "1,200.00"]},
        # and the fee is inside every one of those figures
        {"instalments": 2, "premium": 1000.0, "offers": [{"carrier_id": "a", "fee": 100.0}],
         "carrier": "a", "plans": [{"count": 2, "surcharge": 0.03}],
         "want": ["566.50", "1", "1,133.00"]},
    ]
    program = r"""
var flow = null, PLANS = {};
var f2 = new Intl.NumberFormat("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
function money(v){ return f2.format(v); }
function t(en, vars){
  return vars ? en.replace(/\{(\w+)\}/g, function(m, k){
    return Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m; }) : en;
}
function priced(){ return {premium: flow.premium}; }
function chosenOffer(){
  return (flow.offers||[]).filter(function(o){ return o.carrier_id===flow.carrier; })[0]||null;
}
function offerForPrice(){ return chosenOffer()||(flow.offers||[])[0]||null; }
WHOLE
CLAUSE
console.log(JSON.stringify(CASES.map(function(c){
  flow = c; PLANS = {plans: c.plans}; return payClause();
})));
""".replace("WHOLE", body_of("wholePrice")).replace("CLAUSE", body_of("payClause")) \
   .replace("CASES", json.dumps(cases))
    out = subprocess.run([NODE, "-e", program], capture_output=True, text=True,
                         timeout=30, check=True)
    said = json.loads(out.stdout)
    for clause, case in zip(said, cases):
        for wanted in case["want"]:
            assert wanted in clause, (wanted, clause)
    # The plan clauses never claim finality, and the single one always does.
    assert "nothing else ever" in said[0]
    assert all("nothing else ever" not in c for c in said[1:]), said[1:]


def test_the_clause_is_translated_in_every_book() -> None:
    """Both halves of it: the one payment and the plan."""
    import collections

    both = ["You pay <b>{premium} USDC</b> now, and nothing else ever.",
            "You pay <b>{each} USDC</b> today, then {rest} more payments of the same, "
            "<b>{total} USDC</b> in all."]
    for lang in ("tr", "es", "fr", "de", "ru", "ja"):
        book = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        for english in both:
            said = book.get(english)
            assert said and said != english, (lang, english[:40])
            holes = lambda s: collections.Counter(re.findall(r"\{\w+\}", s))
            assert holes(said) == holes(english), (lang, said)
