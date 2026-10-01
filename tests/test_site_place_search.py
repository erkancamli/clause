"""A label the page wrote itself is not something the reader searched for.

Reported from the live site, with a screenshot. The reader pressed "use my
location", the browser answered, and the page resolved it to "222. Cadde,
Atakent Mahallesi, Küçükçekmece, İstanbul, Türkiye", dropped the pin, worked
out a price of 9,048 USDC and drew the payout ladder. Across from all of that
the results area said:

    Eşleşen bir şey yok. Deprem teminatı Amerika Birleşik Devletleri,
    Japonya, Meksika, Tayvan, Türkiye, Yeni Zelanda ve Şili için
    fiyatlanabiliyor.

Nothing matched, said over a placed pin and a working price, in a sentence
naming Türkiye as a country the cover is written in, about an address in
Türkiye.

setPoint writes the resolved name into the search box and renderStep writes it
back when the reader returns to this question, so the string being searched is
an address. The catalogue is provinces and districts, and will never hold a
street. setPoint's own comment already said there was nothing to search for,
on the line above the one that searched.

Driven against both builds with the same stubbed answer from the reverse
geocoder: the published one said "Eşleşen bir şey yok", this one leaves the
results area empty.
"""

from __future__ import annotations

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PLACES = (SITE / "app" / "65-place-lookup.js").read_text(encoding="utf-8")
MAP = (SITE / "app" / "50-places-and-map.js").read_text(encoding="utf-8")


def test_a_chosen_place_is_not_searched_for() -> None:
    at = PLACES.index("function renderResults(query)")
    head = PLACES[at:PLACES.index("var coordinate = parseCoordinate(query);", at)]
    assert 'if (flow.place && String(query || "").trim() === String(flow.place).trim()){' in head
    assert 'box.innerHTML = "";' in head


def test_the_rule_sits_where_every_caller_passes() -> None:
    """setPoint was the caller that was noticed. renderStep does the same
    thing when the reader comes back to the question, and so would the next
    one written."""
    at = PLACES.index("function renderResults(query)")
    before = PLACES[at:PLACES.index("searchAddress(key);", at)]
    # The guard comes before anything that looks the query up.
    assert before.index('String(flow.place).trim()') < before.index("searchPlaces(query)")


def test_set_point_still_writes_the_label_it_resolved() -> None:
    """The fix must not stop the box showing where the pin went."""
    assert 'if($("place"))$("place").value=flow.place;' in MAP
    assert "renderResults($(\"place\").value);" in MAP


def test_nothing_matched_is_still_said_when_nothing_matched() -> None:
    """A reader who types Brasil still gets an answer rather than a blank."""
    assert 'esc(t("Nothing matched."))' in PLACES
    at = PLACES.index('esc(t("Nothing matched."))')
    guard = PLACES.rindex("if (!hits.length){", 0, at)
    assert guard < at, "the message is no longer behind the empty-result check"
