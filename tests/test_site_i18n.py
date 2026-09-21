"""The site's translations, checked mechanically.

A wrong placeholder puts "{country}" on a buyer's screen; a lost tag breaks the
sentence it sat in; a sentence added to the page without a translation shows in
English to someone who asked for Japanese. None of those needs a person to
catch, so none of them is left to one.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
LANGS = ["tr", "es", "fr", "de", "ru", "ja"]


def dictionary(lang: str) -> dict:
    return json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


def _literal(src: str, i: int) -> tuple[str, int]:
    quote, j, out = src[i], i + 1, []
    while src[j] != quote:
        if src[j] == "\\":
            out.append({"n": "\n", "'": "'", '"': '"', "\\": "\\"}.get(src[j + 1], src[j + 1]))
            j += 2
        else:
            out.append(src[j])
            j += 1
    return "".join(out), j + 1


def page_sentences() -> set[str]:
    """Every English sentence the page passes through t(), N() or tspan()."""
    html = (SITE / "index.html").read_text(encoding="utf-8")
    js = html[html.index("<script>", html.index("<body")):]
    found: set[str] = set()
    for match in re.finditer(r"(?<![\w.$])(t|N|tspan)\(\s*", js):
        i, parts = match.end(), []
        while js[i] in "\"'":
            lit, i = _literal(js, i)
            parts.append(lit)
            k = i
            while js[k] in " \n\t\r":
                k += 1
            if js[k] == "+":
                k += 1
                while js[k] in " \n\t\r":
                    k += 1
                if js[k] in "\"'":
                    i = k
                    continue
                parts = []
            break
        text = "".join(parts)
        if re.search(r"[A-Za-z]{2}", re.sub(r"<[^>]+>|\{\w+\}", "", text)):
            found.add(text)
    return found


@pytest.mark.parametrize("lang", LANGS)
def test_every_translation_keeps_its_placeholders_and_markup(lang) -> None:
    strings = dictionary(lang)["strings"]
    ph = lambda s: collections.Counter(re.findall(r"\{\w+\}", s))
    tags = lambda s: collections.Counter(re.findall(r"<[^>]+>", s))
    wrong = [k for k, v in strings.items() if ph(k) != ph(v) or tags(k) != tags(v)]
    assert not wrong, wrong[:5]


@pytest.mark.parametrize("lang", LANGS)
def test_every_sentence_the_page_writes_is_translated(lang) -> None:
    """Brands and code stay English by design; they are the only exceptions."""
    strings = dictionary(lang)["strings"]
    missing = [s for s in page_sentences()
               if s not in strings and " " in s and not re.match(r"^[A-Z0-9 ,.:+\-]+$", s)]
    assert not missing, missing[:8]


@pytest.mark.parametrize("lang", LANGS)
def test_the_binding_text_is_english(lang) -> None:
    assert dictionary(lang)["binding"] == "en"


@pytest.mark.parametrize("lang", LANGS)
def test_the_legal_warnings_survived_translation(lang) -> None:
    """The sentences a buyer most needs are present, and translated."""
    strings = dictionary(lang)["strings"]
    for key in (
        "Translated for convenience. The English text is the binding one.",
        "Clause is not the insurer.",
        "What you are insuring is not inside the area this index measures, so a payout would not answer a loss you could actually suffer. That is the line between insurance and a wager, and it is the one line this protocol will not cross for you.",
    ):
        assert strings.get(key) and strings[key] != key, key


def table_sentences() -> dict[str, list[str]]:
    """English the page translates through a variable rather than a literal.

    ``page_sentences`` can only see what is written inside ``t("...")``. The
    seismology text is not written that way: the fault names, the sentence
    about a segment that has not ruptured, and the name of the zone all come
    out of tables and reach ``t()`` as ``t(site.nearest.name)``. Nothing
    checked them, so a value added to a table arrived on the page in English
    in every language and no test said a word.
    """
    html = (SITE / "index.html").read_text(encoding="utf-8")
    faults = json.loads(re.search(r"var FAULTS = (\[.*?\]);", html, re.S).group(1))
    zones = json.loads(re.search(r"var ZONE_NAMES = (\{.*?\});", html, re.S).group(1))
    inline = re.findall(r'zoneName:"([^"]+)"', html)
    return {
        "fault name": [f["name"] for f in faults],
        "fault gap note": [f["gap"] for f in faults if f["gap"]],
        "zone name": list(zones.values()) + inline,
    }


@pytest.mark.parametrize("lang", LANGS)
def test_the_sentences_that_reach_t_through_a_table_are_translated(lang) -> None:
    strings = dictionary(lang)["strings"]
    missing = [f"{kind}: {s}" for kind, values in table_sentences().items()
               for s in values if s not in strings]
    assert not missing, missing[:6]
