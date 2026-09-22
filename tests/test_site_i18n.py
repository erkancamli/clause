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
from html.parser import HTMLParser
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


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "source", "track", "wbr"}


class _Marked(HTMLParser):
    """Collects the inner HTML of every element carrying data-i18n."""

    def __init__(self, src: str) -> None:
        super().__init__(convert_charrefs=False)
        self.src = src
        self.starts = [0]
        for line in src.split("\n"):
            self.starts.append(self.starts[-1] + len(line) + 1)
        self.depth = 0
        self.open: list[tuple[int, int]] = []   # (depth, offset just after the start tag)
        self.found: list[str] = []

    def _offset(self) -> int:
        line, col = self.getpos()
        return self.starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            return
        self.depth += 1
        if any(k == "data-i18n" for k, _ in attrs):
            text = self.get_starttag_text() or ""
            self.open.append((self.depth, self._offset() + len(text)))

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        while self.open and self.open[-1][0] == self.depth:
            _, start = self.open.pop()
            self.found.append(self.src[start:self._offset()])
        self.depth -= 1


def markup_sentences() -> set[str]:
    """Every English sentence the page carries in its own markup.

    ``page_sentences`` sees only what a script hands to ``t()``. The static
    page translates itself from its ``data-i18n`` elements, keyed by each
    element's own inner HTML with the whitespace collapsed, and nothing was
    checking those: a heading or a paragraph written straight into the markup
    without a translation reached a Japanese reader in English, and no test
    said a word.
    """
    html = (SITE / "index.html").read_text(encoding="utf-8")
    parser = _Marked(html)
    parser.feed(html)
    out = set()
    for raw in parser.found:
        text = re.sub(r"\s+", " ", raw).strip()
        if re.search(r"[A-Za-z]{2}", re.sub(r"<[^>]+>|\{\w+\}", "", text)):
            out.add(text)
    return out


@pytest.mark.parametrize("lang", LANGS)
def test_every_sentence_in_the_markup_is_translated(lang) -> None:
    """Brands and code stay English by design; they are the only exceptions."""
    strings = dictionary(lang)["strings"]
    missing = [s for s in markup_sentences()
               if s not in strings and " " in s
               and not re.match(r"^[A-Z0-9 ,.:+\-]+$", s)]
    assert not missing, missing[:8]


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
