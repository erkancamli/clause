"""The wait the page tells a buyer about, against the wait the contract holds.

Measured: site/app/65-place-lookup.js had WAITING={quake:7,...} while
clause/perils/quake.py had waiting_days = 3.0, and section 10 of every
contract (clause/protocol/rulebook.py) said three days. The protocol was
changed deliberately -- the comment beside it argues for seventy-two hours --
and four places that say the number out loud were not: the page's table, the
sentence under the start date, the FAQ answer and docs/rulebook.md.

The shape of the failure is worth keeping in mind. Once a quote arrives
coverStartsAt prefers the server's own starts_at, so the confirm step printed
the correct date with "cover starts seven days after it is bought" directly
beneath it. Before the quote it printed a date four days past the one the
contract would carry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from clause.perils import REGISTRY

ROOT = Path(__file__).resolve().parent.parent
PLACES = (ROOT / "site" / "app" / "65-place-lookup.js").read_text(encoding="utf-8")
PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
RULES = (ROOT / "docs" / "rulebook.md").read_text(encoding="utf-8")

#: The page's name for each peril against the protocol's key for it.
AS_THE_PAGE_CALLS_IT = {"quake": "earthquake", "storm": "storm",
                        "car": "vehicle_flood", "flight": "flight_delay"}

IN_WORDS = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
            6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
            15: "fifteen"}


def site_waiting() -> dict[str, int]:
    found = re.search(r"var WAITING=\{([^}]*)\};", PLACES)
    assert found, "the page no longer has a WAITING table"
    return {k: int(v) for k, v in re.findall(r"(\w+):(\d+)", found.group(1))}


def test_every_wait_the_page_names_is_the_protocols_own() -> None:
    table = site_waiting()
    assert set(table) == set(AS_THE_PAGE_CALLS_IT), (
        "a peril was added to one side of this and not the other")
    for name, days in table.items():
        peril = REGISTRY[AS_THE_PAGE_CALLS_IT[name]]
        assert days == peril.waiting_days, (
            f"the page waits {days} days for {name}, the protocol "
            f"{peril.waiting_days}")


def test_the_sentence_under_the_date_says_the_same_number() -> None:
    """Not just the table: the number is also spelled out in words, and it was
    the words that were four days wrong."""
    said = re.search(r'if\(flow\.peril==="quake"\)\s*\n\s*return t\("([^"]+)"\)',
                     PLACES)
    assert said, "the quake wait sentence has moved"
    want = IN_WORDS[int(REGISTRY["earthquake"].waiting_days)]
    assert f"starts {want} days after it is bought" in said.group(1), said.group(1)


def test_the_faq_answer_says_the_same_number() -> None:
    answer = [line for line in PAGE.splitlines()
              if "Cover starts after a wait:" in line]
    assert len(answer) == 1, "the FAQ answer has moved or been duplicated"
    quake = IN_WORDS[int(REGISTRY["earthquake"].waiting_days)]
    storm = IN_WORDS[int(REGISTRY["storm"].waiting_days)]
    assert f"{quake} days for earthquake" in answer[0], answer[0]
    assert f"{storm} for storm and vehicle flood" in answer[0], answer[0]


def test_the_rulebook_page_says_the_same_number() -> None:
    for peril_key, label in (("earthquake", "Earthquake"), ("storm", "Storm"),
                             ("vehicle_flood", "Vehicle flood")):
        days = int(REGISTRY[peril_key].waiting_days)
        row = f"| {label} | Cover starts {days} days after it is bought |"
        assert row in RULES, f"docs/rulebook.md does not say {days} for {label}"


def test_no_translation_carries_the_old_number() -> None:
    """The books translate the sentence and the FAQ answer, so a corrected
    English string with a stale translation would still mis-sell it."""
    stale = {"de": "sieben Tage", "es": "siete días", "fr": "sept jours",
             "ja": "7日", "ru": "семь дней", "tr": "yedi gün"}
    for lang, words in stale.items():
        book = json.loads((ROOT / "site" / "i18n" / f"{lang}.json")
                          .read_text(encoding="utf-8"))
        flat = {k: v for group in book.values() if isinstance(group, dict)
                for k, v in group.items()}
        for key, value in flat.items():
            if "wait" in key.lower() or "cover starts" in key.lower():
                assert words not in value, f"{lang}: {key[:60]} still says {words}"
