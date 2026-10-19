"""What is happening right now, from the sources the protocol settles against.

Two feeds for the home page: earthquakes recorded anywhere in the last day, and
flight delays in force at this moment. They are shown because a protocol whose
whole claim is "we pay on what the world measures" should let anyone see the
world being measured, not because they price anything. Nothing here enters a
premium or a settlement.

Both are fetched by the server rather than by each visitor's browser, and held
for a minute. One fetch a minute from here is a polite use of a public service;
a fetch per page view from every visitor is not, and the sources would be right
to block it.

Sources, and what they are
--------------------------
    Earthquakes     USGS real time feed, magnitude 2.5 and above, past day.
                    Worldwide, public domain, and the first of the sources the
                    earthquake oracle reads.

    Earthquakes     for one country: the same feed, read by the place text USGS
    by country      writes ("40 km SW of Hualien City, Taiwan"). A quiet
                    country is filled from the past week's feed instead, and
                    the reply says which window it shows.

    Flight delays   FAA National Airspace System status: ground stops, ground
                    delay programmes, arrival and departure delays and closures
                    at United States airports. It is the only live delay feed
                    that is both public and licensed for any use. It says
                    nothing about flights elsewhere, and the page says so,
                    rather than implying a worldwide view it does not have.

    Flight delays   AirLabs (CLAUSE_AIRLABS_KEY): every departure delayed by
    elsewhere       three quarters of an hour or more, worldwide, read once an
                    hour, which keeps a free key inside its monthly allowance.
                    Flights are grouped by departure airport into the same
                    rows the FAA feed makes: how many are late, by how much
                    on average and at most. Or FlightAware AeroAPI
                    (CLAUSE_AEROAPI_KEY), airport delays worldwide, a paid
                    feed whose licence tier has to permit showing the data
                    publicly. Airports are placed in a country by the ICAO
                    prefix of their code. Until a key is set, a country other
                    than the United States is told plainly that there is no
                    feed.

A failed fetch never empties the page: the last good answer is served, marked
stale with its age, which is the truthful state of a feed that has stopped
answering.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("clause.live")

USGS_DAY = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
USGS_WEEK = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson"
AEROAPI_DELAYS = "https://aeroapi.flightaware.com/aeroapi/airports/delays"
AIRLABS_DELAYS = "https://airlabs.co/api/v9/delays?delay=45&type=departures"
# Below this many events in a day, a country's band is filled from the week.
QUIET_DAY = 3
FAA_STATUS = "https://nasstatus.faa.gov/api/airport-status-information"
# What the chain this protocol runs on has published. There is no feed to
# subscribe to: the docs are behind a sign in, the blog serves nothing to a
# fetcher, and /blog/rss.xml answers with the home page. What there is, is the
# home page itself, which carries every piece of writing as a card. So that is
# what is read, once every few hours, which is a polite rate for a page that
# changes a few times a month.
RIALO_HOME = "https://www.rialo.io/"
USER_AGENT = "Clause/0.1 (+https://clause.insure)"
MAX_BYTES = 4_000_000          # the day feed is a few hundred kilobytes
QUAKE_LIMIT = 40
FLIGHT_LIMIT = 40


def fetch(url: str, *, timeout: float = 8.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310
        body = reply.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError(f"{url} answered with more than {MAX_BYTES} bytes")
    return body


# ---------------------------------------------------------------------------
# Earthquakes
# ---------------------------------------------------------------------------


def all_quakes(raw: bytes, *, now: float | None = None, window_days: float = 1.0) -> list[dict[str, Any]]:
    """Every earthquake in the feed's window, newest first, each with its country.

    Kept to what the ticker shows and what a reader might want to follow up:
    where, how large, how deep, when, and the USGS page that is the record.
    """
    from .countries import code_for

    now = time.time() if now is None else now
    data = json.loads(raw)
    out: list[dict[str, Any]] = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        geometry = (feature.get("geometry") or {}).get("coordinates") or []
        mag = props.get("mag")
        when = props.get("time")
        if mag is None or when is None or len(geometry) < 2:
            continue
        if props.get("type", "earthquake") != "earthquake":
            continue  # quarry blasts and explosions are in the feed too
        at = float(when) / 1000.0
        if now - at > 86_400 * window_days * 1.05:
            continue
        out.append({
            "id": str(feature.get("id", ""))[:40],
            "magnitude": round(float(mag), 1),
            "magnitude_type": str(props.get("magType") or "")[:8],
            "place": str(props.get("place") or "")[:120],
            "at": at,
            "longitude": round(float(geometry[0]), 3),
            "latitude": round(float(geometry[1]), 3),
            "depth_km": round(float(geometry[2]), 1) if len(geometry) > 2 and geometry[2] is not None else None,
            "tsunami": bool(props.get("tsunami")),
            "alert": props.get("alert") if props.get("alert") in ("green", "yellow", "orange", "red") else None,
            "url": str(props.get("url") or "")[:200],
            "country": code_for(str(props.get("place") or "")),
        })
    out.sort(key=lambda q: q["at"], reverse=True)
    return out


def select_quakes(items: list[dict[str, Any]], country: str | None = None) -> list[dict[str, Any]]:
    """What the band shows: one country's events, or the world's notable ones."""
    out = sorted(items, key=lambda q: q["at"], reverse=True)
    if country:
        return [q for q in out if q.get("country") == country][:QUAKE_LIMIT]
    # The day feed is dominated by small events in the places with the densest
    # networks, Alaska and California above all. A ticker that is meant to show
    # the world leads with what the world would notice, magnitude 4 and above
    # anywhere, and fills with the most recent smaller ones only if the day was
    # quiet.
    notable = [q for q in out if q["magnitude"] >= 4.0]
    if len(notable) < 12:
        rest = [q for q in out if q["magnitude"] < 4.0]
        notable = sorted(notable + rest[: 12 - len(notable)], key=lambda q: q["at"], reverse=True)
    return notable[:QUAKE_LIMIT]


def parse_quakes(raw: bytes, *, now: float | None = None) -> list[dict[str, Any]]:
    """The past day's earthquakes as the worldwide band shows them."""
    return select_quakes(all_quakes(raw, now=now))


# ---------------------------------------------------------------------------
# Flight delays
# ---------------------------------------------------------------------------

# Closures in the FAA list are mostly NOTAM text. Many are partial: closed to
# unscheduled light aircraft, closed except to helicopters overnight. Only a
# closure to everything that flies an airline schedule is a disruption a
# traveller would notice, so the rest are left out rather than shown as alarms.
_PARTIAL_CLOSURE = re.compile(r"\b(TO NON SKED|TRANSIENT|GA ACFT)\b")


# The busiest airports, so a row can say "Chicago O'Hare" rather than "ORD".
# Anything not listed is shown by its code, which is what the FAA gives.
AIRPORTS = {
    "ATL": "Atlanta", "BOS": "Boston", "BWI": "Baltimore", "CLT": "Charlotte",
    "DCA": "Washington National", "DEN": "Denver", "DFW": "Dallas Fort Worth",
    "DTW": "Detroit", "EWR": "Newark", "FLL": "Fort Lauderdale", "HNL": "Honolulu",
    "IAD": "Washington Dulles", "IAH": "Houston", "JFK": "New York JFK",
    "LAS": "Las Vegas", "LAX": "Los Angeles", "LGA": "New York LaGuardia",
    "MCO": "Orlando", "MDW": "Chicago Midway", "MIA": "Miami", "MSP": "Minneapolis",
    "ORD": "Chicago O'Hare", "PDX": "Portland", "PHL": "Philadelphia",
    "PHX": "Phoenix", "SAN": "San Diego", "SEA": "Seattle", "SFO": "San Francisco",
    "SLC": "Salt Lake City", "TPA": "Tampa", "AUS": "Austin", "BNA": "Nashville",
    "STL": "St. Louis", "MSY": "New Orleans", "RDU": "Raleigh Durham",
    "SJC": "San Jose", "OAK": "Oakland", "SNA": "Santa Ana", "CLE": "Cleveland",
    "PIT": "Pittsburgh", "IND": "Indianapolis", "CVG": "Cincinnati",
    "GSP": "Greenville Spartanburg", "TEB": "Teterboro",
}


def _text(node: ET.Element | None, tag: str) -> str:
    if node is None:
        return ""
    found = node.find(tag)
    return (found.text or "").strip() if found is not None and found.text else ""


def _minutes(text: str) -> int | None:
    """"1 hour and 15 minutes", "45 minutes", "16 minutes" into minutes."""
    if not text:
        return None
    hours = re.search(r"(\d+)\s*hour", text)
    mins = re.search(r"(\d+)\s*minute", text)
    if not hours and not mins:
        return None
    return (int(hours.group(1)) * 60 if hours else 0) + (int(mins.group(1)) if mins else 0)


_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _when(text: str, *, now: float | None = None) -> float | None:
    """"Sep 19 at 11:00 UTC" into a timestamp, so the page can show it in the
    reader's own clock and language rather than the FAA's English."""
    import calendar

    m = re.match(r"([A-Z][a-z]{2}) (\d{1,2}) at (\d{1,2}):(\d{2}) UTC", text or "")
    if not m or m.group(1) not in _MONTHS:
        return None
    now = time.time() if now is None else now
    year = time.gmtime(now).tm_year
    month, day = _MONTHS[m.group(1)], int(m.group(2))
    at = calendar.timegm((year, month, day, int(m.group(3)), int(m.group(4)), 0))
    # A reopening in January read in December belongs to next year.
    if at < now - 200 * 86400:
        at = calendar.timegm((year + 1, month, day, int(m.group(3)), int(m.group(4)), 0))
    return float(at)


def _cause(reason: str) -> str:
    """The FAA's reason text, reduced to something every language can say."""
    r = (reason or "").upper()
    if any(w in r for w in ("WX", "WEATHER", "THUNDER", "WIND", "FOG", "LOW CEIL", "SNOW", "ICE", "VIS")):
        return "weather"
    if any(w in r for w in ("VOL", "VOLUME", "DEMAND", "TRAFFIC")):
        return "volume"
    if any(w in r for w in ("RWY", "RUNWAY", "CONSTRUCTION")):
        return "runway"
    if any(w in r for w in ("EQUIP", "OUTAGE", "STAFF", "SECURITY")):
        return "equipment"
    return "other" if r else ""


def parse_faa(raw: bytes) -> list[dict[str, Any]]:
    """Delay programmes in force at US airports, most disruptive first.

    Four kinds, each normalised to the same row: which airport, what kind of
    disruption, how long the delay runs where the FAA says, and the stated
    reason. The reason is passed through as the FAA wrote it.
    """
    text = raw.decode("utf-8", "replace")
    if "<!ENTITY" in text or "<!DOCTYPE" in text:
        # Nothing legitimate in this feed declares entities, and a feed that
        # suddenly does is not one to hand to a parser.
        raise ValueError("unexpected declarations in the FAA feed")
    root = ET.fromstring(text)
    rows: list[dict[str, Any]] = []

    for delay_type in root.iter("Delay_type"):
        for program in delay_type.iter("Program"):          # ground stops
            rows.append({
                "airport": _text(program, "ARPT"), "kind": "ground_stop",
                "reason": _text(program, "Reason"),
                "until": _text(program, "End_Time"),
                "average_minutes": None, "max_minutes": None,
            })
        for delay in delay_type.iter("Ground_Delay"):       # ground delay programmes
            rows.append({
                "airport": _text(delay, "ARPT"), "kind": "ground_delay",
                "reason": _text(delay, "Reason"),
                "until": "",
                "average_minutes": _minutes(_text(delay, "Avg")),
                "max_minutes": _minutes(_text(delay, "Max")),
            })
        for delay in delay_type.iter("Delay"):              # arrival and departure delays
            direction = delay.find("Arrival_Departure")
            kind = "departure_delay"
            if direction is not None and (direction.get("Type") or "").lower().startswith("arr"):
                kind = "arrival_delay"
            rows.append({
                "airport": _text(delay, "ARPT"), "kind": kind,
                "reason": _text(delay, "Reason"),
                "until": "",
                "average_minutes": _minutes(_text(direction, "Min")) if direction is not None else None,
                "max_minutes": _minutes(_text(direction, "Max")) if direction is not None else None,
                "trend": _text(direction, "Trend").lower() if direction is not None else "",
            })
        for airport in delay_type.iter("Airport"):          # closures
            reason = _text(airport, "Reason")
            if _PARTIAL_CLOSURE.search(reason):
                continue
            rows.append({
                "airport": _text(airport, "ARPT"), "kind": "closed",
                "reason": "",   # the NOTAM text is not a reason anyone can read
                "until": _text(airport, "Reopen").rstrip("."),
                "average_minutes": None, "max_minutes": None,
            })

    order = {"ground_stop": 0, "ground_delay": 1, "arrival_delay": 2,
             "departure_delay": 3, "closed": 4}
    seen: set[tuple[str, str]] = set()
    unique = []
    for row in rows:
        if not row["airport"]:
            continue
        key = (row["airport"], row["kind"])
        if key in seen:
            continue
        seen.add(key)
        row["airport"] = row["airport"][:5].upper()
        row["name"] = AIRPORTS.get(row["airport"], "")
        row["reason"] = row["reason"][:80]
        row["until"] = row["until"][:40]
        row["until_at"] = _when(row["until"])
        row["cause"] = _cause(row["reason"])
        unique.append(row)
    unique.sort(key=lambda r: (order.get(r["kind"], 9), -(r.get("max_minutes") or 0)))
    return unique[:FLIGHT_LIMIT]


# ---------------------------------------------------------------------------
# Flight delays outside the United States
# ---------------------------------------------------------------------------

# ICAO location indicators begin with a region and, mostly, a country. Two
# letters where one country shares a first letter with others; one where a
# single country has the whole letter.
_ICAO_TWO = {
    "PA": "US", "PH": "US", "PG": "US", "TJ": "PR", "MM": "MX", "RJ": "JP", "RO": "JP",
    "LT": "TR", "EG": "GB", "ED": "DE", "ET": "DE", "LF": "FR", "LE": "ES", "GC": "ES",
    "LI": "IT", "LG": "GR", "EH": "NL", "EB": "BE", "LS": "CH", "LO": "AT", "EK": "DK",
    "EN": "NO", "ES": "SE", "EF": "FI", "EI": "IE", "LP": "PT", "EP": "PL", "LK": "CZ",
    "LH": "HU", "LR": "RO", "LB": "BG", "LY": "RS", "LD": "HR", "LJ": "SI", "LQ": "BA",
    "LW": "MK", "LA": "AL", "LU": "MD", "LC": "CY", "LM": "MT", "LZ": "SK", "EL": "LU",
    "EV": "LV", "EY": "LT", "EE": "EE", "BI": "IS", "UK": "UA", "UB": "AZ", "UG": "GE",
    "UA": "KZ", "UM": "BY", "OM": "AE", "OE": "SA", "OT": "QA", "OB": "BH", "OK": "KW",
    "OO": "OM", "OI": "IR", "OJ": "JO", "OL": "LB", "LL": "IL", "HE": "EG", "DA": "DZ",
    "DT": "TN", "GM": "MA", "FA": "ZA", "HK": "KE", "DN": "NG", "VT": "TH", "VV": "VN",
    "WS": "SG", "WM": "MY", "WB": "MY", "WI": "ID", "WA": "ID", "WR": "ID", "RP": "PH",
    "RK": "KR", "RC": "TW", "VH": "HK", "VM": "MO", "ZK": "KP", "ZM": "MN", "VA": "IN",
    "VE": "IN", "VI": "IN", "VO": "IN", "OP": "PK", "VC": "LK", "VG": "BD", "VN": "NP",
    "NZ": "NZ", "SB": "BR", "SD": "BR", "SN": "BR", "SS": "BR", "SW": "BR", "SA": "AR",
    "SC": "CL", "SK": "CO", "SP": "PE", "SE": "EC", "SV": "VE", "SU": "UY", "SG": "PY",
    "SL": "BO", "MP": "PA", "MR": "CR", "MD": "DO", "MK": "JM",
}
_ICAO_ONE = {"K": "US", "C": "CA", "Y": "AU", "Z": "CN", "U": "RU"}


# Rialo's own writing
# ---------------------------------------------------------------------------
# Two shapes on one page. The research is in cards that carry a number, a
# month, a title and an opening line; the shorter notes are in a list that
# carries a full date and a title. Both are read, because both are the chain
# saying what it has built, and a protocol that names a chain on its front
# page owes its readers a way to see what that chain is actually doing.


def _plain(html: str) -> str:
    """Tags out, entities in, whitespace folded."""
    text = re.sub(r"<[^>]+>", " ", html)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
        text = text.replace(entity, char)
    return " ".join(text.split())


def _absolute(href: str) -> str:
    if href.startswith("http"):
        return href
    return RIALO_HOME.rstrip("/") + "/" + href.lstrip("/")


def parse_rialo(raw: bytes) -> list[dict[str, Any]]:
    """What Rialo has published, from its own front page.

    A card whose title or link cannot be read is skipped rather than shown
    half empty; a page that changed shape produces a short list or an empty
    one, and an empty one reads as "the source did not answer" upstream,
    which is the truth.
    """
    html = raw.decode("utf-8", "replace")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for card in re.findall(r"<article class=\"docs-card[^\"]*\">(.*?)</article>", html, re.S):
        link = re.search(r'href="([^"]*?/posts/[^"]+)"', card)
        title = re.search(r'<h3 class="card-title">(.*?)</h3>', card, re.S)
        if not link or not title:
            continue
        url = _absolute(link.group(1))
        if url in seen:
            continue
        seen.add(url)
        when = re.search(r'<span class="card-date">(.*?)</span>', card, re.S)
        number = re.search(r'<span class="card-label">(.*?)</span>', card, re.S)
        summary = re.search(r'<p class="card-description">(.*?)</p>', card, re.S)
        out.append({
            "kind": "research",
            "number": _plain(number.group(1)) if number else "",
            "when": _plain(when.group(1)) if when else "",
            "title": _plain(title.group(1)),
            "summary": _plain(summary.group(1)) if summary else "",
            "url": url,
        })

    for entry in re.findall(r'<a href="([^"]+)" class="blog-entry">(.*?)</a>', html, re.S):
        href, body = entry
        title = re.search(r'<h3 class="entry-title">(.*?)</h3>', body, re.S)
        if not title:
            continue
        url = _absolute(href)
        if url in seen:
            continue
        seen.add(url)
        when = re.search(r'<time class="entry-date">(.*?)</time>', body, re.S)
        out.append({
            "kind": "note",
            "number": "",
            "when": _plain(when.group(1)) if when else "",
            "title": _plain(title.group(1)),
            "summary": "",
            "url": url,
        })
    return out


def icao_country(code: str) -> str | None:
    code = (code or "").strip().upper()
    if len(code) != 4 or not code.isalnum():
        return None
    return _ICAO_TWO.get(code[:2]) or _ICAO_ONE.get(code[0])


def parse_aeroapi(raw: bytes) -> list[dict[str, Any]]:
    """AeroAPI's airport delays, in the same row the FAA rows use.

    Written to the documented shape of GET /airports/delays: a list under
    "delays", each with an airport code, a delay in seconds and its reasons.
    Anything missing is left empty rather than guessed.
    """
    data = json.loads(raw)
    rows: list[dict[str, Any]] = []
    for item in data.get("delays") or []:
        airport = str(item.get("airport") or item.get("airport_code") or "")[:5].upper()
        if not airport:
            continue
        seconds = item.get("delay_secs")
        reasons = item.get("reasons") or []
        text = " ".join(str(r.get("reason") or r.get("category") or "") for r in reasons if isinstance(r, dict))
        rows.append({
            "airport": airport, "kind": "delays", "reason": text[:80], "until": "",
            "until_at": None,
            "average_minutes": round(seconds / 60) if isinstance(seconds, (int, float)) else None,
            "max_minutes": None, "name": "", "cause": _cause(text),
            "country": icao_country(airport),
        })
    rows.sort(key=lambda r: -(r["average_minutes"] or 0))
    return rows


def parse_airlabs(raw: bytes, *, now: float | None = None) -> list[dict[str, Any]]:
    """AirLabs' delayed departures, grouped by airport into the FAA row.

    Each flight comes with its departure airport (IATA and ICAO), the
    minutes it is late and its status. One row per airport: the count, the
    average and the worst, and the flights themselves (the first few) so
    the band can name them.
    """
    data = json.loads(raw)
    if isinstance(data, dict) and data.get("error"):
        raise ValueError(str(data["error"].get("message") or "AirLabs refused")[:80])
    by_airport: dict[str, dict[str, Any]] = {}
    for item in (data.get("response") if isinstance(data, dict) else data) or []:
        if not isinstance(item, dict):
            continue
        airport = str(item.get("dep_iata") or "")[:3].upper()
        icao = str(item.get("dep_icao") or "")[:4].upper()
        minutes = item.get("dep_delayed") or item.get("delayed")
        if not airport or not isinstance(minutes, (int, float)) or minutes <= 0:
            continue
        row = by_airport.setdefault(airport, {
            "airport": airport, "kind": "delays", "reason": "", "until": "", "until_at": None,
            "average_minutes": 0, "max_minutes": 0, "name": "", "cause": "other",
            "country": icao_country(icao), "flights": [], "count": 0, "_sum": 0.0,
        })
        row["count"] += 1
        row["_sum"] += float(minutes)
        row["max_minutes"] = max(row["max_minutes"], int(minutes))
        if len(row["flights"]) < 4:
            code = str(item.get("flight_iata") or item.get("flight_icao") or "")[:8]
            to = str(item.get("arr_iata") or "")[:3].upper()
            row["flights"].append({"flight": code, "to": to, "minutes": int(minutes)})
    rows = []
    for row in by_airport.values():
        row["average_minutes"] = round(row.pop("_sum") / row["count"])
        row["reason"] = f"{row['count']} departures late"
        rows.append(row)
    rows.sort(key=lambda r: (-r["count"], -(r["max_minutes"] or 0)))
    return rows[:FLIGHT_LIMIT * 3]


def airlabs_feed(key: str, **kw: Any) -> Feed:
    return Feed(
        name="flights_world", url=f"{AIRLABS_DELAYS}&api_key={key}", parse=parse_airlabs,
        interval=3600.0, source="AirLabs", coverage="departures 45 minutes late or more, worldwide, past hour",
        **kw,
    )


def aeroapi_fetcher(key: str) -> Callable[[str], bytes]:
    def fetch_with_key(url: str, *, timeout: float = 8.0) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "x-apikey": key,
                                                       "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310
            body = reply.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("AeroAPI answered with more than the limit")
        return body
    return fetch_with_key


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------


@dataclass
class Feed:
    """One source, fetched at most once per interval, never emptied by a failure."""

    name: str
    url: str
    parse: Callable[[bytes], list[dict[str, Any]]]
    interval: float
    source: str
    coverage: str
    fetcher: Callable[[str], bytes] = fetch
    items: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: float = 0.0
    last_attempt: float = 0.0
    error: str = ""
    #: A feed read in the background answers at once with what it last had and
    #: refreshes on a thread. For a source read in several pieces over a slow
    #: line, the alternative is the visitor who happens to trigger the refresh
    #: waiting out every piece, which the page gives up on before they arrive.
    background: bool = False
    busy: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def read(self, *, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        # The lock covers the decision and the bookkeeping, never the fetch:
        # readers of a slow source get the last answer at once rather than
        # queueing behind the network.
        with self.lock:
            due = now - self.last_attempt >= self.interval and not self.busy
            if due:
                self.last_attempt = now
                self.busy = True
        if due and self.background:
            threading.Thread(target=self.refresh, args=(now,), name=f"feed-{self.name}", daemon=True).start()
        elif due:
            self.refresh(now)
        with self.lock:
            age = now - self.fetched_at if self.fetched_at else None
            reply = {
                "items": list(self.items),
                "fetched_at": self.fetched_at or None,
                "age_seconds": round(age) if age is not None else None,
                "stale": bool(self.error) or age is None or age > self.interval * 5,
                "source": self.source,
                "coverage": self.coverage,
            }
            if self.error:
                reply["error"] = self.error
            if self.busy and self.background:
                reply["refreshing"] = True
            return reply

    def refresh(self, now: float) -> None:
        try:
            items = self.parse(self.fetcher(self.url))
            with self.lock:
                self.items = items
                self.fetched_at = now
                self.error = ""
        except Exception as error:  # a feed failing is a state, not a crash
            logger.warning("live feed %s failed: %s", self.name, error)
            with self.lock:
                # The kind and the words, not a stand in phrase: when the
                # deployment reads nothing for a country, the answer has to
                # say whether that was a timeout, a 429 or a parse, because
                # the log is on the server and the question is asked here.
                self.error = f"{type(error).__name__}: {error}"[:160]
        finally:
            with self.lock:
                self.busy = False


def quake_feed(**kw: Any) -> Feed:
    """Every event of the past day; the endpoint chooses what the band shows."""
    return Feed(
        name="quakes", url=USGS_DAY, parse=all_quakes, interval=60.0,
        source="USGS", coverage="worldwide, magnitude 2.5 and above, past 24 hours",
        **kw,
    )


def quake_week_feed(**kw: Any) -> Feed:
    """The past week, read only when a country had a quiet day."""
    return Feed(
        name="quakes_week", url=USGS_WEEK,
        parse=lambda raw: all_quakes(raw, window_days=7.0), interval=600.0,
        source="USGS", coverage="magnitude 2.5 and above, past 7 days",
        **kw,
    )


def aeroapi_feed(key: str, **kw: Any) -> Feed:
    kw.setdefault("fetcher", aeroapi_fetcher(key))
    return Feed(
        name="flights_world", url=AEROAPI_DELAYS, parse=parse_aeroapi, interval=300.0,
        source="FlightAware", coverage="airports with delays, worldwide", **kw,
    )


def rialo_feed(**kw: Any) -> Feed:
    """What the chain has published, read from its own front page.

    Six hours, not a minute: this is writing, not weather.
    """
    return Feed(
        name="rialo", url=RIALO_HOME, parse=parse_rialo, interval=6 * 3600.0,
        source="rialo.io", coverage="every piece of writing on Rialo's front page",
        **kw,
    )

def flight_feed(**kw: Any) -> Feed:
    return Feed(
        name="flights", url=FAA_STATUS, parse=parse_faa, interval=120.0,
        source="FAA", coverage="United States airports",
        **kw,
    )


# ---------------------------------------------------------------------------
# Weather today, from Open-Meteo
# ---------------------------------------------------------------------------

OPEN_METEO = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
              "&daily=precipitation_sum,temperature_2m_max,temperature_2m_min,wind_gusts_10m_max,weather_code"
              "&forecast_days=1&timezone=auto")

# A few large cities per country the site prices in, and the capitals of the
# rest a visitor is likely to pick. Türkiye uses its 81 provincial centres.
WEATHER_CITIES: dict[str, list[tuple[str, float, float]]] = {
    "JP": [("Tokyo", 35.68, 139.69), ("Osaka", 34.69, 135.50), ("Nagoya", 35.18, 136.91),
           ("Sapporo", 43.06, 141.35), ("Fukuoka", 33.59, 130.40), ("Sendai", 38.27, 140.87)],
    "CL": [("Santiago", -33.45, -70.67), ("Valparaíso", -33.05, -71.62), ("Concepción", -36.83, -73.05),
           ("Antofagasta", -23.65, -70.40), ("Puerto Montt", -41.47, -72.94)],
    "MX": [("Mexico City", 19.43, -99.13), ("Guadalajara", 20.66, -103.35), ("Monterrey", 25.67, -100.31),
           ("Oaxaca", 17.07, -96.73), ("Acapulco", 16.86, -99.88), ("Mérida", 20.97, -89.62)],
    "NZ": [("Auckland", -36.85, 174.76), ("Wellington", -41.29, 174.78), ("Christchurch", -43.53, 172.64),
           ("Dunedin", -45.87, 170.50)],
    "TW": [("Taipei", 25.03, 121.57), ("Taichung", 24.15, 120.67), ("Kaohsiung", 22.63, 120.30),
           ("Hualien", 23.99, 121.60)],
    "DE": [("Berlin", 52.52, 13.41), ("Hamburg", 53.55, 9.99), ("Munich", 48.14, 11.58),
           ("Cologne", 50.94, 6.96), ("Frankfurt", 50.11, 8.68)],
    "GB": [("London", 51.51, -0.13), ("Manchester", 53.48, -2.24), ("Glasgow", 55.86, -4.25),
           ("Cardiff", 51.48, -3.18), ("Belfast", 54.60, -5.93)],
    "US": [("New York", 40.71, -74.01), ("Los Angeles", 34.05, -118.24), ("Chicago", 41.88, -87.63),
           ("Houston", 29.76, -95.37), ("Miami", 25.76, -80.19), ("Seattle", 47.61, -122.33)],
    "GR": [("Athens", 37.98, 23.73), ("Thessaloniki", 40.64, 22.94), ("Heraklion", 35.34, 25.13)],
    "IT": [("Rome", 41.90, 12.50), ("Milan", 45.46, 9.19), ("Naples", 40.85, 14.27), ("Palermo", 38.12, 13.36)],
    "ES": [("Madrid", 40.42, -3.70), ("Barcelona", 41.39, 2.17), ("Valencia", 39.47, -0.38), ("Seville", 37.39, -5.99)],
    "FR": [("Paris", 48.86, 2.35), ("Marseille", 43.30, 5.37), ("Lyon", 45.76, 4.84), ("Toulouse", 43.60, 1.44)],
    "KE": [("Nairobi", -1.29, 36.82), ("Mombasa", -4.04, 39.67), ("Kisumu", -0.09, 34.77)],
    "ID": [("Jakarta", -6.21, 106.85), ("Surabaya", -7.25, 112.75), ("Medan", 3.60, 98.67), ("Denpasar", -8.65, 115.22)],
    "PH": [("Manila", 14.60, 120.98), ("Cebu", 10.32, 123.89), ("Davao", 7.19, 125.46)],
    "IN": [("Mumbai", 19.08, 72.88), ("Delhi", 28.61, 77.21), ("Chennai", 13.08, 80.27), ("Kolkata", 22.57, 88.36)],
    "BR": [("São Paulo", -23.55, -46.63), ("Rio de Janeiro", -22.91, -43.17), ("Salvador", -12.97, -38.51)],
}

WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
       51: "drizzle", 53: "drizzle", 55: "drizzle", 61: "rain", 63: "rain", 65: "heavy rain",
       71: "snow", 73: "snow", 75: "heavy snow", 80: "showers", 81: "showers", 82: "violent showers",
       95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}


WORLD_CITIES: list[tuple[str, float, float]] = [
    ("Istanbul", 41.01, 28.98), ("Tokyo", 35.68, 139.69), ("London", 51.51, -0.13), ("New York", 40.71, -74.01),
    ("Berlin", 52.52, 13.41), ("Madrid", 40.42, -3.70), ("Paris", 48.86, 2.35), ("Mexico City", 19.43, -99.13),
    ("São Paulo", -23.55, -46.63), ("Nairobi", -1.29, 36.82), ("Jakarta", -6.21, 106.85), ("Manila", 14.60, 120.98),
    ("Mumbai", 19.08, 72.88), ("Santiago", -33.45, -70.67), ("Sydney", -33.87, 151.21), ("Cairo", 30.04, 31.24),
]


def weather_points(country: str | None) -> list[tuple[str, float, float]]:
    code = (country or "").upper()
    if not code:
        return WORLD_CITIES
    if code == "TR":
        from .perils.places import PLACES
        return [(p.name, p.latitude, p.longitude) for p in PLACES if p.kind == "province"]
    return WEATHER_CITIES.get(code, [])


def parse_weather(raw: bytes, points: list[tuple[str, float, float]]) -> list[dict[str, Any]]:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    out = []
    for (name, lat, lon), row in zip(points, data):
        daily = (row or {}).get("daily") or {}
        if not daily:
            # A place whose chunk did not come back is left out, not shown
            # with blanks: the page sorts by rain, and a row of nothing would
            # sit among real readings looking like a dry day.
            continue
        rain = (daily.get("precipitation_sum") or [0])[0] or 0.0
        temp = (daily.get("temperature_2m_max") or [None])[0]
        low = (daily.get("temperature_2m_min") or [None])[0]
        gust = (daily.get("wind_gusts_10m_max") or [None])[0]
        code = (daily.get("weather_code") or [None])[0]
        out.append({"place": name, "latitude": lat, "longitude": lon, "rain_mm": round(float(rain), 1),
                    "temp_max": temp, "temp_min": low, "gust_kmh": gust, "code": code,
                    "sky": WMO.get(int(code), "") if code is not None else ""})
    # Most rain first, then the strongest gusts: the days that matter to cover.
    out.sort(key=lambda w: (-(w["rain_mm"] or 0), -(w["gust_kmh"] or 0)))
    return out


#: Open-Meteo answers one forecast request for many places, but a single
#: answer for eighty one of them is forty kilobytes that has to arrive whole
#: inside one timeout, over whatever line the server has that minute. The
#: deployment read nothing for Türkiye for days that way while five cities of
#: Germany came back at once. So places are asked for in chunks, and a chunk
#: that fails costs its own places only.
WEATHER_CHUNK = 20
#: A subscription (CLAUSE_OPENMETEO_KEY) sends the same query to the customer
#: host, which has its own quota instead of the one shared by everybody behind
#: the server's address. A key the host does not accept falls back to the free
#: host for that chunk, so a wrong key reads slower rather than reading nothing.
OPENMETEO_FORECAST_FREE = "api.open-meteo.com"
OPENMETEO_FORECAST_PAID = "customer-api.open-meteo.com"


def weather_url(points: list[tuple[str, float, float]]) -> str:
    return OPEN_METEO.format(lat=",".join(f"{p[1]:.2f}" for p in points),
                             lon=",".join(f"{p[2]:.2f}" for p in points))


def subscribed_url(url: str) -> str | None:
    """The same query on the customer host with the key, or None without one."""
    import os
    import urllib.parse
    key = os.environ.get("CLAUSE_OPENMETEO_KEY", "").strip()
    if not key or OPENMETEO_FORECAST_FREE not in url:
        return None
    moved = url.replace(OPENMETEO_FORECAST_FREE, OPENMETEO_FORECAST_PAID, 1)
    join = "&" if "?" in moved else "?"
    return f"{moved}{join}apikey={urllib.parse.quote(key, safe='')}"


def fetch_weather(points: list[tuple[str, float, float]], fetcher: Callable[[str], bytes],
                  *, chunk: int = WEATHER_CHUNK, pause: float = 0.5,
                  sleep: Callable[[float], None] = time.sleep) -> bytes:
    """Every place's forecast as one JSON list, read a chunk at a time.

    Places whose chunk failed are present as empty objects, so the list lines
    up with the points and parse_weather can leave them out. Only when no
    chunk came back at all does this raise, carrying the last reason.

    The free host counts every place as a call and refuses a burst with 429:
    measured from a shared address, the fourth chunk of five was refused when
    they went out back to back. So chunks are paced, and a refused chunk is
    asked for once more after a breath before its places are given up.
    """
    rows: list[Any] = []
    failures: list[str] = []

    def read(url: str) -> bytes:
        try:
            return fetcher(url)
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            sleep(pause * 4)
            return fetcher(url)

    for start in range(0, len(points), chunk):
        if start and pause:
            sleep(pause)
        part = points[start:start + chunk]
        url = weather_url(part)
        try:
            raw = None
            paid = subscribed_url(url)
            if paid:
                try:
                    raw = read(paid)
                except urllib.error.HTTPError as error:
                    if error.code not in (400, 401, 403):
                        raise
                    logger.warning("open-meteo refused the subscription key (%s); reading the free host", error.code)
            if raw is None:
                raw = read(url)
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            if len(data) != len(part):
                raise ValueError(f"asked for {len(part)} places and got {len(data)} answers")
            rows.extend(data)
        except Exception as error:
            failures.append(f"{type(error).__name__}: {error}"[:120])
            rows.extend({} for _ in part)
    if failures and len(failures) * chunk >= len(points):
        raise RuntimeError(f"no chunk of {len(points)} places answered; last: {failures[-1]}")
    if failures:
        logger.warning("open-meteo: %s of %s chunks failed: %s", len(failures),
                       -(-len(points) // chunk), failures[-1])
    return json.dumps(rows).encode()


def weather_feed(country: str | None, **kw: Any) -> Feed | None:
    points = weather_points(country)
    if not points:
        return None
    # The fetcher a caller hands in (tests, mostly) reads one URL; the feed's
    # own reads the chunks through it. Each chunk gets a wait of its own.
    one = kw.pop("fetcher", None) or (lambda url: fetch(url, timeout=25.0))
    # Today's forecast does not change by the quarter hour, and every place
    # asked for counts against the day's quota: the big lists read half as often.
    interval = 1800.0 if len(points) > 30 else 900.0
    # Read in the background once the list is long enough to be read in
    # pieces: the page asks again every minute and shows the pieces that came.
    kw.setdefault("background", len(points) > WEATHER_CHUNK)
    return Feed(name=f"weather-{country}", url=weather_url(points),
                parse=lambda raw: parse_weather(raw, points),
                fetcher=lambda _url: fetch_weather(points, one),
                interval=interval, source="Open-Meteo", coverage="today's forecast, by place", **kw)
