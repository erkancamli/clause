"""Airports, so a buyer can name their own flight.

The flight cover used to offer six routes. Anyone whose flight was not one of
them could not buy it, which is not a product: a traveller who cannot find
their flight has nothing to insure. So the route is not a list any more. The
buyer names the flight number and the two airports, and this module is what
turns an IATA code into a place, a country and, most importantly, a clock.

The clock is the part that has to be right. The cover has to be bought
twenty-four hours before the scheduled departure, and a departure written on a
ticket is written in the time at the airport it leaves from. Without the zone
the same "09:00" is a different instant in Istanbul and in São Paulo, and the
rule would refuse flights it should sell and sell flights it should refuse.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent / "airports.json"


@lru_cache(maxsize=1)
def _loaded() -> tuple[dict[str, dict[str, Any]], str]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    fields = raw["fields"]
    table = {row[0]: dict(zip(fields, row)) for row in raw["airports"]}
    return table, raw.get("attribution", "")


def all_airports() -> dict[str, dict[str, Any]]:
    return _loaded()[0]


def attribution() -> str:
    return _loaded()[1]


EARTH_RADIUS_KM = 6371.0088


def great_circle_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Kilometres between two points on the sphere, properly.

    geo.distance_km is a flat approximation, which is right for what it was
    written for — fault traces and stations tens of kilometres apart — and
    wrong here. A sector is thousands of kilometres and can cross the
    antimeridian, where the flat form reads the long way round the world:
    Tokyo to New York came out at 18,697 km instead of 10,850.
    """
    import math

    lat1, lon1 = (math.radians(v) for v in a)
    lat2, lon2 = (math.radians(v) for v in b)
    half = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(half)))


def find(code: str) -> dict[str, Any] | None:
    """One airport by its IATA code."""
    return all_airports().get(str(code or "").strip().upper())


#: The four letters Turkish spells with and English spells with one. Folding
#: them together is what lets "istanbul", "İstanbul" and the catalogue's own
#: "Istanbul" all find each other. Turkish casing rules are deliberately not
#: applied: they are right for Turkish text and wrong for a catalogue written
#: in English, where lowercasing I to ı would stop "istanbul" matching
#: "Istanbul" — which is the one search a buyer here is most likely to try.
_I_FORMS = str.maketrans({"İ": "i", "I": "i", "ı": "i", "i": "i"})


def fold(text: str) -> str:
    """Case, accents and the dot on an i off, for comparing names."""
    lowered = str(text or "").translate(_I_FORMS).lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", lowered)
        if not unicodedata.combining(ch)
    )


#: Busy airports, kept by hand and used only for ordering results. The
#: catalogue carries no traffic figures, so without this "istanbul" offers a
#: small field before Istanbul Airport, which is the wrong answer to a right
#: question. Nothing about a policy depends on being in this set: an airport
#: outside it is insured on exactly the same terms, it just appears lower.
MAJOR = frozenset("""
IST SAW ESB ADB AYT ADA TZX GZT DLM BJV
LHR LGW LCY STN MAN EDI DUB AMS CDG ORY BRU LUX
FRA MUC BER DUS HAM CGN STR TXL VIE ZRH GVA
MAD BCN AGP PMI LIS OPO FCO MXP LIN VCE NAP BLQ
ATH SKG CPH ARN OSL HEL KEF RIX TLL VNO
WAW KRK PRG BUD OTP SOF BEG ZAG LJU
SVO DME LED KBP
JFK EWR LGA BOS PHL IAD DCA BWI ATL MIA MCO FLL TPA
ORD MDW DTW MSP STL CLT RDU IAH DFW AUS DEN PHX LAS
LAX SFO SAN SJC SEA PDX SLC HNL
YYZ YUL YVR YYC MEX CUN GDL GRU CGH GIG BSB CNF POA
EZE AEP SCL LIM BOG UIO PTY SJO HAV
DXB AUH DOH RUH JED KWI BAH MCT AMM BEY TLV CAI
DEL BOM BLR MAA HYD CCU COK GOI
PEK PKX PVG SHA CAN SZX CTU CKG XIY HGH NKG
HKG TPE TSA ICN GMP NRT HND KIX NGO CTS FUK
SIN KUL BKK DMK CGK DPS MNL CEB HAN SGN RGN PNH
SYD MEL BNE PER ADL OOL CNS AKL CHC WLG
JNB CPT DUR NBO ADD LOS ABV ACC CMN RAK TUN ALG
""".split())


def search(query: str, *, limit: int = 8, country: str | None = None) -> list[dict[str, Any]]:
    """Airports matching a code, a city or a name.

    An exact IATA code first, because somebody typing three letters knows what
    they mean; then the city, then the name. Within each, the shorter match
    first, so "London" offers London Heathrow before London Biggin Hill.
    """
    wanted = fold(query).strip()
    if not wanted:
        return []
    where = country.upper() if country else None
    exact: list[dict[str, Any]] = []
    city: list[dict[str, Any]] = []
    named: list[dict[str, Any]] = []
    for airport in all_airports().values():
        if where and airport["country"] != where:
            continue
        if fold(airport["iata"]) == wanted:
            exact.append(airport)
            continue
        if fold(airport["city"]).startswith(wanted):
            city.append(airport)
            continue
        if wanted in fold(airport["name"]) or wanted in fold(airport["city"]):
            named.append(airport)
    for bucket in (city, named):
        bucket.sort(key=lambda a: (a["iata"] not in MAJOR, len(a["name"]), a["iata"]))
    return (exact + city + named)[:limit]
