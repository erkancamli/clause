"""The sentence beside the ladder named a level the policy does not use.

"The step at intensity VI is your trigger" sat under a ladder whose first
paying row read "Intensity 6.9 or more". A roman numeral is a whole number and
these steps are not: an older building pays at less shaking, so the first step
is 6.9 for a flat built in 2005 and 6.3 for the same flat built in 1975, and
6.25 in Istanbul against 6.62 in New York. The sentence said VI for all of
them, which is a lower level than any of them, on the screen where the buyer
decides.

rungWords was written to avoid exactly this, and payRows was fixed for it when
it read the curve at VI, VII and VIII instead of at the policy's own points.
This sentence was the last place still carrying it.

Driven in a browser over two building ages: the ladder, the sentence and the
basis-risk paragraph now say 6.9 together, and 6.3 together.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import page_assembled

SITE = Path(__file__).resolve().parent.parent / "site"
PAGE = page_assembled()
FLOW = (SITE / "app" / "60-cover-flow.js").read_text(encoding="utf-8")

KEY = ("The step at intensity {level} is your trigger. Each step up pays more,"
       " so a reading just short of one level still pays the level below.")


def test_the_sentence_no_longer_names_a_fixed_level() -> None:
    assert "The step at intensity VI is your trigger" not in PAGE


def test_it_names_the_policys_own_first_step() -> None:
    found = re.search(r'note=t\("The step at intensity \{level\}[^;]+;', FLOW, re.S)
    assert found, "the sentence is gone or no longer takes a level"
    assert "structure().pts[0][0]" in found.group(0), found.group(0)[-120:]


def test_it_is_the_same_step_the_ladder_draws() -> None:
    """Both read the policy's own points, so they cannot drift apart."""
    ladder = re.search(r'rows\.push\(\[t\("Intensity \{level\} or more: strong,'
                       r' light damage",\{level:f1\.format\(([^)]+)\)\}\)', FLOW)
    assert ladder, "the ladder's first paying row moved"
    # qp is structure().pts in payRows; the sentence reads the same call.
    assert ladder.group(1) == "qp[0][0]", ladder.group(1)
    assert "var qp=c.pts;" in FLOW and "c=structure()" in FLOW


def test_it_says_intensity_where_the_ladder_says_intensity() -> None:
    """One screen calls a thing one name. The unit is named where naming it is
    the point: in what the cover does not pay for, and in the contract."""
    assert "The step at intensity {level} is your trigger" in PAGE
    assert "MMI" not in KEY


def test_the_old_sentence_is_gone_from_every_language() -> None:
    old = "The step at intensity VI is your trigger."
    for lang in ("tr", "es", "fr", "de", "ru", "ja"):
        strings = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        assert not [k for k in strings if k.startswith(old)], lang
        assert KEY in strings, lang
        assert strings[KEY] != KEY, (lang, "left in English")
        assert "{level}" in strings[KEY], (lang, "the level cannot be filled in")
