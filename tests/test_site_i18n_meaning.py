"""Three things a translation can do to a contract, each found in a book.

1. Name a different scale. Japanese rendered Modified Mercalli intensity as
   bare 震度 in every live string that carries a buyer's own trigger. In
   Japanese 震度 on its own is the JMA shindo scale, which is the only
   intensity scale a Japanese reader has met: shindo 6 collapses wooden
   houses, MMI VI is "strong, light damage" and sits around shindo 4. So
   "震度 6.2 の揺れから支払われます" reads as a trigger several steps more
   severe than the policy's, and a buyer concludes the cover pays far more
   rarely than it does. Shindo also stops at 7 and is never written with a
   decimal, so the top rung printed "震度 8.0", a level that cannot exist on
   the scale the reader believes is in use. The correct メルカリ震度 existed in
   the book already, on the roman-numeral strings that the parametrised ones
   replaced, which is how a spot check would have missed it.

2. Lose the copula. Stripping dashes from the Russian book left "сезон,
   который измеряет полис,, ближайший на его станции": a sentence that no
   longer says which season is covered. Russian uses the dash where English
   uses "is", so a book with none is not a book with cleaner punctuation.

3. Turn permission into obligation. Turkish rendered "someone else is at that
   desk; they can leave it" as "kalkması gerekir", which says they must.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = ("de", "es", "fr", "ja", "ru", "tr")


def book(lang: str) -> dict[str, str]:
    raw = json.loads((ROOT / "site" / "i18n" / f"{lang}.json")
                     .read_text(encoding="utf-8"))
    return {k: v for group in raw.values() if isinstance(group, dict)
            for k, v in group.items()}


JA = book("ja")

#: Everything a Japanese buyer reads their own trigger from.
THE_TRIGGER_STRINGS = (
    "If the ground at {place} shakes at <b>intensity {level} or more</b>",
    "Shaking below intensity {level}",
    "Intensity {level} or more: strong, light damage",
    "Intensity {level} or more: very strong, damage to ordinary buildings",
    "Intensity {level} or more: severe",
    "The step at intensity {level} is your trigger",
    "pays from shaking of intensity {level}",
)


@pytest.mark.parametrize("head", THE_TRIGGER_STRINGS)
def test_japanese_names_the_scale_the_policy_settles_on(head: str) -> None:
    keys = [k for k in JA if k.startswith(head)]
    assert keys, f"no Japanese entry starts {head!r}; this test is stale"
    for key in keys:
        said = JA[key]
        assert "震度" in said, key
        for found in re.finditer("震度", said):
            at = found.start()
            assert said[max(0, at - 4):at] == "メルカリ", (
                f"bare 震度 reads as the JMA scale: {said[:60]}")


def test_the_scale_is_never_named_twice_over() -> None:
    for key, said in JA.items():
        assert "メルカリメルカリ" not in said, key


@pytest.mark.parametrize("lang", LANGUAGES)
def test_no_sentence_lost_its_punctuation(lang: str) -> None:
    """A doubled comma or a space before one is what stripping a dash leaves
    behind, and in Russian the dash is the verb."""
    for key, said in book(lang).items():
        assert ",," not in said, f"{lang}: {key[:60]} -> {said[:90]}"
        assert " ," not in said, f"{lang}: {key[:60]} -> {said[:90]}"


def test_the_russian_season_sentence_says_which_season() -> None:
    said = [v for k, v in book("ru").items()
            if k.startswith("No, and that is deliberate. Cover starts after a wait")]
    assert len(said) == 1
    assert "сезон, который измеряет полис, — ближайший" in said[0]


def test_turkish_does_not_turn_permission_into_obligation() -> None:
    said = book("tr")["someone else is at that desk; they can leave it"]
    assert "kalkabilir" in said
    assert "gerekir" not in said
