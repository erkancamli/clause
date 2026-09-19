"""Addresses to coordinates and back, from OpenStreetMap.

The built in gazetteer knows provinces and the larger districts. A person
types their own address, "İstanbul Küçükçekmece" or a street, and expects it
to be found; and a phone can say where it is before anything is typed. Both
need a real geocoder.

Two public services, each used the way its operators ask:

    search      Photon (photon.komoot.io), built for search as you type over
                OpenStreetMap data
    reverse     Nominatim (nominatim.openstreetmap.org), for turning the
                coordinates a browser reports into a readable place; its usage
                policy allows this and forbids using it for as you type search,
                which is why search goes to Photon

Every request goes through this server, never from the visitor's browser, so
the services see one identified client (a User-Agent naming this site) rather
than every visitor, answers are cached, and requests are spaced out: at most
one a second to each. Data is OpenStreetMap's, under the ODbL, and the page
says so wherever it shows a result.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Any, Callable

PHOTON = "https://photon.komoot.io/api/"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "Clause/1.0 (+https://clause.insure)"
ATTRIBUTION = "© OpenStreetMap contributors, ODbL"
CACHE_SIZE = 4000
CACHE_SECONDS = 7 * 86400
MIN_INTERVAL = 1.0

# Photon speaks these; anything else gets the local names, which for a
# Turkish address is what a Turkish reader wants anyway.
PHOTON_LANGS = {"en", "de", "fr"}


MAX_BYTES = 2_000_000


class GeocodeError(RuntimeError):
    """The geocoder could not answer. Safe to show."""


def _default_fetch(url: str) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=8) as reply:  # noqa: S310
        body = reply.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise GeocodeError("the geocoder answered with more than expected")
    return body


class Geocoder:
    def __init__(self, fetch: Callable[[str], bytes] | None = None) -> None:
        self.fetch = fetch or _default_fetch
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}
        self.email = os.environ.get("CLAUSE_GEOCODER_EMAIL", "").strip()

    # -- plumbing ----------------------------------------------------------

    def _cached(self, key: str) -> Any:
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                self._cache.move_to_end(key)
                return hit[1]
        return None

    def _keep(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = (time.time(), value)
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)

    def _get(self, service: str, url: str) -> Any:
        # One request a second to each service, from this whole server. A
        # request that is refused takes no slot, so a burst does not push
        # everyone behind it further back.
        with self._lock:
            now = time.time()
            slot = max(now, self._last.get(service, 0.0) + MIN_INTERVAL)
            wait = slot - now
            if wait > 4:
                raise GeocodeError("address search is busy; try again in a moment")
            self._last[service] = slot
        if wait > 0:
            time.sleep(wait)
        try:
            return json.loads(self.fetch(url) or b"null")
        except Exception as error:  # the page falls back to the built in list
            raise GeocodeError("address search is not reachable right now") from error

    # -- search ------------------------------------------------------------

    def search(self, query: str, *, lang: str = "", near: tuple[float, float] | None = None,
               limit: int = 6) -> list[dict[str, Any]]:
        query = " ".join(str(query).split())[:120]
        if len(query) < 3:
            return []
        key = f"s|{query.lower()}|{lang}|{near}|{limit}"
        cached = self._cached(key)
        if cached is not None:
            return cached
        params: dict[str, Any] = {"q": query, "limit": limit}
        if lang in PHOTON_LANGS:
            params["lang"] = lang
        if near:
            params["lat"], params["lon"] = round(near[0], 3), round(near[1], 3)
        data = self._get("photon", PHOTON + "?" + urllib.parse.urlencode(params))
        out = []
        for feature in (data or {}).get("features", [])[:limit]:
            place = _from_photon(feature)
            if place:
                out.append(place)
        self._keep(key, out)
        return out

    def reverse(self, latitude: float, longitude: float, *, lang: str = "") -> dict[str, Any] | None:
        lat, lon = round(float(latitude), 5), round(float(longitude), 5)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise GeocodeError("that is not a place on Earth")
        key = f"r|{round(lat, 4)}|{round(lon, 4)}|{lang}"
        cached = self._cached(key)
        if cached is not None:
            return cached or None          # {} is a remembered "no place here"
        params: dict[str, Any] = {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 16,
                                  "addressdetails": 1}
        if lang:
            params["accept-language"] = lang
        if self.email:
            params["email"] = self.email
        data = self._get("nominatim", NOMINATIM + "?" + urllib.parse.urlencode(params))
        place = _from_nominatim(data, lat, lon)
        self._keep(key, place or {})
        return place


def _label(parts: list[str | None]) -> str:
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def _from_photon(feature: dict[str, Any]) -> dict[str, Any] | None:
    props = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coords) != 2:
        return None
    street = " ".join(p for p in (props.get("street"), props.get("housenumber")) if p) or None
    name = props.get("name")
    local = props.get("district") or props.get("locality")
    town = props.get("city") or props.get("county")
    state = props.get("state")
    title = _label([name or street, local if local != (name or street) else None,
                    town if town != name else None])
    region = _label([state if state not in (town, name) else None, props.get("country")])
    return {
        "name": title or _label([town, state]) or "?",
        "region": region,
        "latitude": round(float(coords[1]), 5),
        "longitude": round(float(coords[0]), 5),
        "country": str(props.get("countrycode") or "").upper() or None,
        "kind": "address",
    }


def _from_nominatim(data: Any, lat: float, lon: float) -> dict[str, Any] | None:
    if not isinstance(data, dict) or data.get("error"):
        return None
    address = data.get("address") or {}
    street = " ".join(p for p in (address.get("road"), address.get("house_number")) if p) or None
    local = address.get("suburb") or address.get("neighbourhood") or address.get("quarter")
    town = (address.get("town") or address.get("city_district") or address.get("city")
            or address.get("county") or address.get("village"))
    province = address.get("province") or address.get("state") or address.get("city")
    return {
        "name": _label([street, local, town]) or data.get("display_name", "")[:80],
        "region": _label([province if province != town else None, address.get("country")]),
        "latitude": lat,
        "longitude": lon,
        "country": str(address.get("country_code") or "").upper() or None,
        "kind": "address",
    }
