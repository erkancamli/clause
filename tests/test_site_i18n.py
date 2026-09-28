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
def test_the_type_inside_a_drawing_is_translated(lang) -> None:
    """The two tests above both excuse a line set entirely in capitals.

    That is right for a unit or a ticker, and wrong for the labels on this
    site's drawings, which are set in capitals as a matter of style and are
    ordinary English underneath. Every one of them is in fact translated, so
    the exemption was never a decision about drawings; it was a hole those two
    tests happened to leave, and a new figure could ship its whole legend in
    English through it.
    """
    strings = dictionary(lang)["strings"]
    html = (SITE / "index.html").read_text(encoding="utf-8")
    labels = set()
    for svg in re.findall(r"<svg\b.*?</svg>", html, re.S):
        for text in re.findall(r"<text[^>]*\bdata-i18n\b[^>]*>([^<]+)</text>", svg):
            text = re.sub(r"\s+", " ", text).strip()
            if re.search(r"[A-Za-z]{2}", text):
                labels.add(text)
    assert len(labels) > 20, f"only {len(labels)} labels found; the drawings are not being read"
    missing = sorted(s for s in labels if s not in strings)
    assert not missing, missing[:8]


@pytest.mark.parametrize("lang", LANGS)
def test_what_a_drawing_says_to_a_screen_reader_is_translated(lang) -> None:
    """A drawing's description is the whole of it for anyone who cannot see it.

    Nothing was checking these, and five figures reached every non-English
    reader with their description in English. Four of them had been that way
    since the release that drew them.
    """
    strings = dictionary(lang)["strings"]
    html = (SITE / "index.html").read_text(encoding="utf-8")
    described = set(re.findall(r'aria-label="([^"]+)" data-i18n-aria', html))
    assert described, "no described elements found; the page is not being read"
    missing = sorted(s for s in described if s not in strings)
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

    Only what actually reaches a browser is collected, and that is wider than
    it looked. Most internal ``ValueError`` text does not reach one, because
    ``safe_detail`` logs it and answers with the fallback. But a peril reading
    what the buyer typed raises ``ValueError`` and the API forwards it word
    for word -- ``raise HTTPException(400, str(error))`` -- and the same goes
    for the valuation's ``ValuationError``, which becomes a 422 carrying its
    own sentence. Sixteen of those were reaching every reader in English,
    among them the one a buyer meets by choosing a place outside the band:
    "storm cover is written only within 60 km of a Türkiye provincial centre".

    So the two kinds are collected together: whatever is raised while the
    protocol is reading a subject or valuing what is at risk, and whatever
    ``Refused`` is given anywhere.
    """
    import ast

    root = Path(__file__).resolve().parent.parent / "clause"
    found: dict[str, str] = {}
    # The functions whose refusals the API hands on unchanged: a peril reading
    # a subject, and the valuation working out what a description supports.
    reading = {"validate_subject", "value_of", "rate_for", "harvest_for"}

    def forwarded(tree) -> list[tuple[str, int]]:
        out = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name not in reading:
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                    continue
                f = node.exc.func
                raised = (f.id if isinstance(f, ast.Name)
                          else f.attr if isinstance(f, ast.Attribute) else None)
                if raised not in ("ValueError", "ValuationError"):
                    continue
                for arg in node.exc.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        out.append((" ".join(arg.value.split()), node.lineno))
        return out

    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a file we cannot parse is not a message
            continue
        for text, line in forwarded(tree):
            if len(text) > 4 and re.search(r"[a-z]{3}", text):
                found.setdefault(text, f"{path.name}:{line}")
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


def rulebook_sentences() -> dict[str, str]:
    """Every sentence the calculation rules page prints, from the protocol.

    The page is the rulebook: which source is read, which stands in when it is
    silent, what counts as the final figure, the tests a reading must pass,
    when the cover applies. It reached every non-English reader in English --
    49 of its 53 sentences had no entry in any dictionary -- while the layout
    around them translated perfectly, which is the worst version of the fault
    because it looks finished.

    Read from the protocol rather than from a list here, so a peril added or a
    rule reworded fails this instead of shipping untranslated.
    """
    root = Path(__file__).resolve().parent.parent / "clause"
    found: dict[str, str] = {}

    from clause.protocol import rulebook
    for key, rule in rulebook.RULES.items():
        for field in ("index", "primary", "final_data", "waiting"):
            if rule.get(field):
                found.setdefault(rule[field], f"rulebook.{key}.{field}")
        for group in ("fallbacks", "criteria"):
            for i, text in enumerate(rule.get(group) or []):
                found.setdefault(text, f"rulebook.{key}.{group}[{i}]")
    found.setdefault(rulebook.SUCCESSOR_RULE, "rulebook.SUCCESSOR_RULE")
    found.setdefault(rulebook.ARCHIVE_RULE, "rulebook.ARCHIVE_RULE")

    # And what a source says when it never publishes, which the page prints as
    # the Silence row. Those sentences live with the perils, not the rulebook.
    for path in sorted((root / "perils").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"on_missing_data=\(?\s*((?:\s*\"[^\"]*\")+)", src):
            text = "".join(re.findall(r'"([^"]*)"', m.group(1)))
            if len(text) > 20:
                found.setdefault(text, f"{path.name}:{src[:m.start()].count(chr(10)) + 1}")
    return found


@pytest.mark.parametrize("lang", LANGS)
def test_every_rule_that_decides_money_can_be_read(lang) -> None:
    data = dictionary(lang)
    sentences = rulebook_sentences()
    assert len(sentences) > 40, f"only {len(sentences)} rules read out of the protocol"
    missing = [f"{where}: {text[:60]}" for text, where in sorted(sentences.items())
               if not _resolves(text, data)]
    assert not missing, missing[:6]


@pytest.mark.parametrize("lang", LANGS)
def test_a_rule_keeps_its_figures_and_its_sources_in_translation(lang) -> None:
    """A threshold that changed in translation is a different rule.

    These sentences decide money: 24 hours before a fallback is read, 0.3
    magnitude units between two networks, 15 days before a season's sales
    close. A translator who writes 48 where the protocol wrote 24, or drops
    GFZ GEOFON from the list of who is read, has not mistranslated a sentence
    but rewritten a term, and nobody reading only the translation can tell.

    Units are the one thing allowed to change, because km/h is written km/sa
    in Turkish and км/ч in Russian, and that is the unit arriving in the
    reader's own alphabet rather than a figure going missing.
    """
    strings = dictionary(lang)["strings"]
    named = ["USGS", "ShakeMap", "AFAD", "Kandilli", "GEOFON", "ERA5-Land", "ERA5",
             "NASA POWER", "MERRA-2", "ADS-B", "MMI", "Mw"]
    wrong = []
    for english in rulebook_sentences():
        local = strings.get(english)
        if not local or local == english:
            continue
        for name in named:
            if name in english and name not in local:
                wrong.append(f"{name} lost: {english[:50]}")
        for figure in sorted(set(re.findall(r"(?<![\w.,])\d+(?:\.\d+)?(?![\w])", english))):
            if figure in local or figure.replace(".", ",") in local:
                continue
            wrong.append(f"{figure} lost: {english[:50]}")
    assert not wrong, wrong[:6]


def test_a_sentence_the_protocol_sends_is_never_printed_raw() -> None:
    """Having a translation is not the same as using it.

    The attestation rule -- three of four validators, the median, five per
    cent -- is in every dictionary, and the Proof page printed it with esc()
    instead of ts() for as long as that band existed. A Turkish reader got the
    heading in Turkish and the rule under it in English, on the one page whose
    whole job is to be worth trusting. The guard written the release before
    could not see it: that one holds that a sentence *has* a translation, and
    this one is about whether the page bothers to ask for it.

    So this follows the value. It finds what the page stores a prose field of
    the protocol's into, follows that through the hands it passes, and
    requires every esc() of it to translate first.

    A hop is an alias and nothing else -- a name given a member access,
    optionally guarded, optionally defaulted to empty. Written loosely, as
    "the field name appearing anywhere in an assignment", it collected
    "class", "textContent" and "id" within three rounds and then demanded that
    tsHtml translate the English original it exists to show.
    """
    html = (SITE / "index.html").read_text(encoding="utf-8")
    script = "".join(re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S))

    #: Fields of an API reply that carry a sentence rather than a name, a
    #: number or an address. "attestation" is left out on purpose: the
    #: purchase flow calls a sanctions statement by that name, and that is an
    #: object, not a sentence.
    prose = ("aggregation_rule", "successor", "archive", "final_data",
             "on_missing_data", "waiting", "primary")
    alias = (r'(?:var\s+)?(\w+)\s*=\s*(?:[\w.$]+\s*&&\s*)*[\w.$]*\.(?:{})'
             r'\s*(?:\|\|\s*(?:""|\'\'|\{{\}}|\[\]|null))?\s*[;,)}}]')

    carriers = set(prose)
    for _ in range(4):
        found = set(re.findall(alias.format("|".join(map(re.escape, sorted(carriers)))), script))
        if found <= carriers:
            break
        carriers |= found
    carriers -= set(prose)    # the fields themselves are read, never printed
    assert carriers, "nothing is being followed; this test proves nothing"

    raw = []
    for call in re.finditer(r"\besc\(([^()]*(?:\([^()]*\)[^()]*)*)\)", script):
        inside = call.group(1)
        if "ts(" in inside or "tsHtml(" in inside:
            continue
        # A name, not the same word inside a sentence: "the rule written into
        # the policy" is English being shown, not a variable called rule.
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', inside)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        for name in carriers:
            if re.search(rf"(?<![\w.]){re.escape(name)}\b", code):
                raw.append(f"esc({inside.strip()[:56]})")
    assert not raw, (
        "the protocol's own sentence is printed without translating it: " + repr(raw[:4])
    )


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


@pytest.mark.parametrize("lang", LANGS)
def test_no_sentence_is_translated_twice_in_one_dictionary(lang) -> None:
    """A second entry for the same sentence is a translation nobody can see.

    json.loads keeps whichever came last and says nothing, so the two can
    disagree for as long as anybody likes and the file still parses. Adding
    thirteen refusals to these dictionaries put three sentences in twice, and
    the screen showed the other one: found by reading a refusal in a browser
    and not recognising the wording.
    """
    seen: collections.Counter[str] = collections.Counter()

    def count(pairs):
        seen.update(key for key, _ in pairs)
        return dict(pairs)

    json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"),
               object_pairs_hook=count)
    twice = sorted(key for key, n in seen.items() if n > 1)
    assert not twice, twice[:5]
