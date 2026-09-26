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
def test_a_single_word_is_translated_too(lang) -> None:
    """The tests above both require a space, so a one word label could never
    fail them. "Against" reached a Turkish reader in English and stayed there,
    and because the rail uppercases its labels it arrived as "AGAINST" with
    the dotted capital Turkish gives an i -- visibly foreign, and nothing said
    a word. A word is a sentence for this purpose.
    """
    strings = dictionary(lang)["strings"]
    words = {s for s in page_sentences() | markup_sentences()
             if " " not in s and re.fullmatch(r"[A-Za-z][a-z]{2,}", s)}
    missing = [s for s in words if s not in strings]
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


def _resolves(text: str, data: dict) -> bool:
    """Whether ``ts()`` would find a translation for this sentence."""
    strings = data["strings"]
    if text in strings:
        return True
    for template in data["patterns"]:
        source = re.escape(template).replace(r"\{", "{").replace(r"\}", "}")
        source = re.sub(r"\{(\w+)\}", "(.+?)", source)
        if re.fullmatch(source, text) and template in strings:
            return True
    return False


def peril_sentences() -> list[tuple[str, str]]:
    """Every cover name and subject line the protocol composes.

    These reach the page through ``ts(policy.peril_name)``, so neither the
    literal scan nor the markup scan can see them, and nothing was checking
    them. A buyer with a storm policy read "Storm, on extreme wind at the
    address" in English on an otherwise Turkish page, and the address line
    ended "wind read at İstanbul (17 km)" in the middle of a Turkish
    sentence.
    """
    from clause.perils import REGISTRY

    subjects: dict[str, list[dict]] = {
        "earthquake": [
            {"location": "IST-KADIKOY", "radius_km": 50.0},
            {"latitude": 40.99, "longitude": 29.03, "radius_km": 25.0, "place": "A street"},
            {"latitude": 40.99, "longitude": 29.03, "radius_km": 25.0,
             "place": "A street", "index": "shaking", "built": 1998},
        ],
        "storm": [{"latitude": 40.99, "longitude": 29.03, "place": "A street"}],
        "vehicle_flood": [{"latitude": 40.99, "longitude": 29.03, "place": "A street"}],
        "drought": [{"station": "TR-KONYA", "distance_km": 6.0, "hectares": 60.0}],
        "flight_delay": [{"route": "TK-IST-LHR", "flight_number": "TK1979",
                          "departure_date": "2026-10-05"}],
    }
    out: list[tuple[str, str]] = []
    for key, rows in subjects.items():
        peril = REGISTRY[key]
        for row in rows:
            try:
                subject = peril.validate_subject(dict(row))
            except Exception:  # a shape this peril does not accept
                continue
            out.append(("cover name", peril.title_for(subject)))
            out.append(("subject line", peril.describe_subject(subject)))
    return out


@pytest.mark.parametrize("lang", LANGS)
def test_every_cover_name_and_subject_line_is_translated(lang) -> None:
    data = dictionary(lang)
    missing = [f"{kind}: {text}" for kind, text in peril_sentences()
               if not _resolves(text, data)]
    assert not missing, missing[:6]


def refusals() -> dict[str, str]:
    """Every sentence the protocol can put in front of a person.

    The page's own words are covered twice over, by the literal scan and the
    markup scan, but a refusal is written in Python: ``Refused(409, "that
    policy cannot be cancelled")``, or the fallback ``safe_detail`` hands out
    in place of an internal error. Nothing was reading those, and forty of
    them had no translation in any language, so the one moment a person is
    told no was the one moment the page dropped into English.

    Only what actually reaches a browser is collected. Internal ``ValueError``
    text does not: ``safe_detail`` logs it and answers with the fallback.
    """
    import ast

    root = Path(__file__).resolve().parent.parent / "clause"
    found: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a file we cannot parse is not a message
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.id if isinstance(node.func, ast.Name)
                    else node.func.attr if isinstance(node.func, ast.Attribute) else None)
            texts = []
            if name == "Refused":
                texts += [a.value for a in node.args
                          if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            texts += [k.value.value for k in node.keywords
                      if k.arg == "fallback" and isinstance(k.value, ast.Constant)
                      and isinstance(k.value.value, str)]
            for text in texts:
                text = text.strip()
                if len(text) > 4 and re.search(r"[a-z]{3}", text):
                    found.setdefault(text, f"{path.name}:{node.lineno}")
    return found


@pytest.mark.parametrize("lang", LANGS)
def test_every_refusal_can_be_read(lang) -> None:
    data = dictionary(lang)
    missing = [f"{where}: {text}" for text, where in sorted(refusals().items())
               if not _resolves(text, data)]
    assert not missing, missing[:6]


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


#: A sentence may legitimately come through a translation unchanged, but only
#: three kinds of them do: the rule a subscription is written in, an
#: institution's name, and a string that is nothing but placeholders and
#: units. Everything else that survives unchanged survived by being forgotten.
_CODE = re.compile(r"[(){}]|>=|<=|→|\.\w+\(|_\w|::")
_UNITS = re.compile(r"^[\s\d{}a-z/·×%.,:-]+$", re.I)


def _a_name(text: str) -> bool:
    """Bermuda Monetary Authority, Central Bank of Ireland, NASA POWER."""
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", text)
    return bool(words) and all(word[0].isupper() or len(word) <= 3 for word in words)


@pytest.mark.parametrize("lang", LANGS)
def test_nothing_is_present_but_untranslated(lang: str) -> None:
    """A dictionary entry that repeats its English is not a translation.

    Every other test here asks whether a sentence has an entry. A sentence
    added to the page and copied into all six files without being translated
    has one, and passes them all, and reaches a reader of Japanese in English.
    This is the one that notices.
    """
    said = dictionary(lang)["strings"]
    forgotten = [
        english for english, translated in said.items()
        if english == translated and len(english) > 3
        and not _CODE.search(english) and not _UNITS.match(english)
        and not _a_name(english)
    ]
    assert not forgotten, f"{lang} repeats the English for: {forgotten[:8]}"
