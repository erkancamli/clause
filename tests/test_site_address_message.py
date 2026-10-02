"""Asking for the part that is already filled, and pointing at the wrong field.

Driven on the live site from "Konumumu kullan". The browser answered, the
page resolved the point and wrote "Küçükçekmece" into the town field, and the
button on the risk step read:

    Sokağı ve şehri girin        disabled: true
    addr-street: ""   addr-city: "Küçükçekmece"

The town was there. The message asked for it anyway, because it named both
parts whenever addressOk() refused, without looking at which part was
missing. And `at:` always sent the cursor to the street, so a reader who had
typed a street and left the town empty was moved away from the empty field.

Choosing a place from the list fills the town the same way, so this is what
most readers of this message were told.

The branch is lifted out of the source and run, so the test fails if the
message or the field it focuses stops following what is in the address.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
FLOW_SOURCE = (SITE / "app" / "60-cover-flow.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def without_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:\w])//[^\n]*", "", src)


FLOW = without_comments(FLOW_SOURCE)
RISK = without_comments(
    (SITE / "app" / "70-what-is-at-risk.js").read_text(encoding="utf-8"))


def the_branch() -> str:
    """The `if(!addressOk())` block, from its `if` to its own closing brace."""
    start = FLOW.index("if(!addressOk()){")
    depth = 0
    for i in range(FLOW.index("{", start), len(FLOW)):
        if FLOW[i] == "{":
            depth += 1
        elif FLOW[i] == "}":
            depth -= 1
            if depth == 0:
                return FLOW[start:i + 1]
    raise AssertionError("the address branch has no closing brace")


def ask(cases: list[dict]) -> list:
    """Run the branch against each address and return what it says."""
    program = """
var t = function(s){ return s; };
var flow = null, addressOk = null;
var answers = CASES.map(function(c){
  flow = {interest:{address:c.address}};
  addressOk = function(){ return c.ok; };
  return (function(){ BRANCH; return null; })();
});
console.log(JSON.stringify(answers));
""".replace("CASES", json.dumps(cases)).replace("BRANCH", the_branch())
    out = subprocess.run([NODE, "-e", program], capture_output=True, text=True,
                         timeout=30, check=True)
    return json.loads(out.stdout)


pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def test_it_asks_only_for_the_part_that_is_missing() -> None:
    said = ask([
        {"address": {"street": "", "city": "Küçükçekmece"}, "ok": False},
        {"address": {"street": "222. Cadde", "city": ""}, "ok": False},
        {"address": {"street": "", "city": ""}, "ok": False},
    ])
    assert said[0]["say"] == "Enter the street"
    assert said[1]["say"] == "Enter the town"
    assert said[2]["say"] == "Enter the street and the town"


def test_the_cursor_goes_to_the_empty_field() -> None:
    said = ask([
        {"address": {"street": "", "city": "Küçükçekmece"}, "ok": False},
        {"address": {"street": "222. Cadde", "city": ""}, "ok": False},
        {"address": {"street": "", "city": ""}, "ok": False},
    ])
    assert said[0]["at"] == "addr-street"
    assert said[1]["at"] == "addr-city", "sent away from the field that is empty"
    assert said[2]["at"] == "addr-street"


def test_a_street_too_short_to_be_one_still_counts_as_missing() -> None:
    """addressOk() wants three characters of street and two of town. The
    message has to agree with it, or it names the filled part."""
    said = ask([
        {"address": {"street": "  ", "city": "Van"}, "ok": False},
        {"address": {"street": "Ab", "city": "Van"}, "ok": False},
        {"address": {"street": "222. Cadde", "city": " "}, "ok": False},
    ])
    assert [s["say"] for s in said] == ["Enter the street", "Enter the street",
                                        "Enter the town"]


def test_an_address_without_the_two_keys_does_not_throw() -> None:
    said = ask([{"address": {}, "ok": False}])
    assert said[0]["say"] == "Enter the street and the town"


def test_nothing_is_said_when_the_address_is_accepted() -> None:
    assert ask([{"address": {"street": "222. Cadde", "city": "İstanbul"},
                 "ok": True}]) == [None]


def test_the_lengths_match_the_rule_that_refuses() -> None:
    """Read from addressOk itself, so the two drift apart loudly."""
    at = RISK.index("function addressOk(")
    rule = RISK[at:RISK.index("\nfunction ", at + 1)]
    assert "length>=3" in rule and "length>=2" in rule
    branch = the_branch()
    assert "street&&a.street.trim().length>=3" in branch
    assert "city&&a.city.trim().length>=2" in branch


def test_all_three_sentences_are_translated() -> None:
    for name in ("de", "es", "fr", "ja", "ru", "tr"):
        book = json.loads((SITE / "i18n" / f"{name}.json").read_text(encoding="utf-8"))
        flat = {k: v for group in book.values() if isinstance(group, dict)
                for k, v in group.items()}
        for sentence in ("Enter the street", "Enter the town",
                         "Enter the street and the town"):
            assert flat.get(sentence), f"{name} has no {sentence!r}"
