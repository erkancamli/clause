"""The three agencies that measure an earthquake in Turkiye, and what to ask them.

Each parser was written against a response actually fetched from the agency,
not from memory of its documentation, and the responses are kept in
tests/feeds so the tests read the same bytes the agencies sent.

The three do not agree, and the point of reading all three is to know that
rather than to hide it. See agreement.py.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request

from . import access
from .observation import Observation, digest_of

USER_AGENT = "Clause/0.1 (+https://clause.insure)"
MAX_BYTES = 8_000_000
TIMEOUT = 12.0

USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
EMSC = "https://www.seismicportal.eu/fdsnws/event/1/query"
AFAD = "https://deprem.afad.gov.tr/apiv2/event/filter"


def address(url: str) -> str:
    """One reference as an address a fetcher can open.

    References are written without a scheme, because that is the form a policy
    carries and the form the host checks are made against. A fetcher needs
    one, and this is the only place it is added -- the weather references were
    schemeless, nothing added a scheme, and every read of them failed with
    "unknown url type" into a log nobody watched, so rain, storm and drought
    policies read nothing and settled as though the sky had been dry.

    Only https is opened. A reference naming file:// or plain http is not a
    source that can be checked by somebody else, which is the whole of what a
    reference is for.
    """
    text = str(url or "").strip()
    if "://" not in text:
        return f"https://{text}"
    if not text.lower().startswith("https://"):
        raise ValueError(f"{text} is not an https address")
    return text


def fetch(url: str, *, timeout: float = TIMEOUT) -> tuple[bytes, str]:
    """The bytes a source sent, and the exact address they were asked for.

    Both are returned because the address is half the evidence: a reading
    somebody else cannot reproduce the query for is a reading they have to
    take on trust. Where this deployment's subscription sent the query
    somewhere else, or where a scheme had to be added to open it, what comes
    back is the public query the caller gave rather than the one that was
    made: a reader has to be able to repeat it without this machine's key.
    """
    asked = access.reaching(address(url))
    request = urllib.request.Request(asked, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310
        body = reply.read(MAX_BYTES + 1)
        final = reply.geturl()
    if len(body) > MAX_BYTES:
        raise ValueError(f"{url} answered with more than {MAX_BYTES} bytes")
    return body, (final if asked == url else url)


def _epoch(text: str, *, assume_utc: bool = True) -> float:
    """A source's timestamp as seconds. Each of the three writes its own way."""
    raw = str(text or "").strip().replace("Z", "+00:00")
    if not raw:
        return 0.0
    try:
        when = dt.datetime.fromisoformat(raw)
    except ValueError:
        return 0.0
    if when.tzinfo is None and assume_utc:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.timestamp()


# ---------------------------------------------------------------- USGS

def usgs_query(*, latitude: float, longitude: float, radius_km: float,
               since: float, until: float, minimum: float = 4.0) -> str:
    terms = {
        "format": "geojson", "latitude": f"{latitude:.4f}", "longitude": f"{longitude:.4f}",
        "maxradiuskm": f"{radius_km:g}", "minmagnitude": f"{minimum:g}",
        "starttime": dt.datetime.fromtimestamp(since, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": dt.datetime.fromtimestamp(until, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return f"{USGS}?{urllib.parse.urlencode(terms)}"


def read_usgs(body: bytes, url: str, *, now: float | None = None,
              field: str = "magnitude") -> list[Observation]:
    """Every earthquake USGS reports in the window, largest first.

    ``mmi`` is the shaking USGS's ShakeMap estimates at the site, which is a
    different quantity from the magnitude and is what an intensity cover reads.
    It is absent on small events and on events too new to have a ShakeMap, and
    an absent reading is not a zero.
    """
    now = time.time() if now is None else now
    stamp = digest_of(body)
    out: list[Observation] = []
    for feature in json.loads(body).get("features", []):
        props = feature.get("properties") or {}
        if props.get("type", "earthquake") != "earthquake":
            continue    # quarry blasts and explosions are in this feed too
        value = props.get("mag") if field == "magnitude" else props.get("mmi")
        when = props.get("time")
        if value is None or when is None:
            continue
        where = (feature.get("geometry") or {}).get("coordinates") or []
        out.append(Observation(
            source="USGS", value=float(value),
            unit="magnitude" if field == "magnitude" else "MMI",
            measured_at=float(when) / 1000.0, retrieved_at=now, url=url, digest=stamp,
            record_id=str(feature.get("id") or ""),
            revised_at=float(props.get("updated") or 0) / 1000.0,
            scale=str(props.get("magType") or "") if field == "magnitude" else "MMI",
            reviewed=str(props.get("status") or "").lower() == "reviewed",
            latitude=float(where[1]) if len(where) > 1 else 0.0,
            longitude=float(where[0]) if len(where) > 0 else 0.0,
            note=str(props.get("place") or "")[:120],
        ))
    return sorted(out, key=lambda o: -o.value)


# ---------------------------------------------------------------- AFAD

def afad_query(*, since: float, until: float, minimum: float = 4.0) -> str:
    terms = {
        "start": dt.datetime.fromtimestamp(since, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "end": dt.datetime.fromtimestamp(until, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "minmag": f"{minimum:g}",
    }
    return f"{AFAD}?{urllib.parse.urlencode(terms)}"


def read_afad(body: bytes, url: str, *, now: float | None = None) -> list[Observation]:
    """Turkiye's own agency, and the only one of the three that admits to revising.

    AFAD writes its times without a zone, which invites the assumption that
    they are Turkish local. They are not: AFAD's own record of the Pazarcik
    earthquake reads 2023-02-06T01:17:32, and USGS independently puts it at
    01:17:32 UTC. They are UTC, and reading them as local would move every
    Turkish settlement three hours and break the waiting period on the exact
    perils that need it most.

    ``isEventUpdate`` says this record has already been corrected at least
    once and ``lastUpdateDate`` says when. That is a revision marker, not a
    review status: AFAD does not publish whether a person checked the number,
    so ``reviewed`` stays false here and says so rather than implying more than
    the agency claimed.
    """
    now = time.time() if now is None else now
    stamp = digest_of(body)
    out: list[Observation] = []
    for row in json.loads(body):
        value, when = row.get("magnitude"), row.get("date")
        if value in (None, "") or not when:
            continue
        measured = _epoch(str(when).strip())
        if not measured:
            continue
        where = " ".join(str(row.get(k) or "") for k in ("location", "province")).strip()
        revised = _epoch(str(row.get("lastUpdateDate") or "").split(".")[0])
        out.append(Observation(
            source="AFAD", value=float(value), unit="magnitude",
            measured_at=measured, retrieved_at=now, url=url, digest=stamp,
            record_id=str(row.get("eventID") or ""),
            scale=str(row.get("type") or ""),
            revised_at=revised,
            reviewed=False,
            latitude=float(row.get("latitude") or 0.0),
            longitude=float(row.get("longitude") or 0.0),
            note=where[:120],
        ))
    return sorted(out, key=lambda o: -o.value)


# ---------------------------------------------------------------- EMSC

def emsc_query(*, latitude: float, longitude: float, radius_km: float,
               since: float, until: float, minimum: float = 4.0) -> str:
    terms = {
        "format": "json", "lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}",
        "maxradius": f"{radius_km / 111.0:.3f}",     # the portal takes degrees
        "minmag": f"{minimum:g}",
        "starttime": dt.datetime.fromtimestamp(since, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": dt.datetime.fromtimestamp(until, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return f"{EMSC}?{urllib.parse.urlencode(terms)}"


def read_emsc(body: bytes, url: str, *, now: float | None = None) -> list[Observation]:
    now = time.time() if now is None else now
    stamp = digest_of(body)
    out: list[Observation] = []
    for feature in json.loads(body).get("features", []):
        props = feature.get("properties") or {}
        value, when = props.get("mag"), props.get("time")
        if value is None or not when:
            continue
        out.append(Observation(
            source="EMSC", value=float(value), unit="magnitude",
            measured_at=_epoch(str(when)), retrieved_at=now, url=url, digest=stamp,
            record_id=str(props.get("source_id") or feature.get("id") or ""),
            scale=str(props.get("magtype") or ""),
            latitude=float(props.get("lat") or 0.0),
            longitude=float(props.get("lon") or 0.0),
            note=str(props.get("flynn_region") or "")[:120],
        ))
    return sorted(out, key=lambda o: -o.value)
