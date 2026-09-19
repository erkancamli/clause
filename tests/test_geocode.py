"""Addresses from OpenStreetMap, through this server, cached and spaced out."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.geocode import GeocodeError, Geocoder

PHOTON = {"features": [
    {"properties": {"name": "Küçükçekmece", "state": "İstanbul", "country": "Türkiye",
                    "countrycode": "TR", "type": "city"},
     "geometry": {"coordinates": [28.7711956, 40.9918737]}},
    {"properties": {"name": "Küçükçekmece", "street": "İstanbul Caddesi", "district": "Fatih",
                    "city": "Küçükçekmece", "state": "İstanbul", "country": "Türkiye",
                    "countrycode": "TR"},
     "geometry": {"coordinates": [28.7729609, 40.9885367]}},
]}
NOMINATIM = {"address": {"road": "706. Sokak", "suburb": "Cumhuriyet Mahallesi",
                         "town": "Küçükçekmece", "province": "İstanbul",
                         "country": "Türkiye", "country_code": "tr"},
             "display_name": "706. Sokak, Cumhuriyet Mahallesi, Küçükçekmece"}


def fake(calls):
    def fetch(url):
        calls.append(url)
        return json.dumps(PHOTON if "photon" in url else NOMINATIM).encode()
    return fetch


def test_search_finds_a_district_and_caches_it(monkeypatch) -> None:
    monkeypatch.setattr("clause.geocode.MIN_INTERVAL", 0.0)
    calls = []
    geo = Geocoder(fetch=fake(calls))
    places = geo.search("istanbul küçükçekmece")
    assert places[0]["name"].startswith("Küçükçekmece")
    assert places[0]["country"] == "TR" and abs(places[0]["latitude"] - 40.99187) < 1e-4
    assert "photon.komoot.io" in calls[0]
    geo.search("istanbul küçükçekmece")
    assert len(calls) == 1, "the same question is answered from the cache"
    assert geo.search("ab") == [], "too short to be worth asking"


def test_reverse_names_where_a_phone_is(monkeypatch) -> None:
    monkeypatch.setattr("clause.geocode.MIN_INTERVAL", 0.0)
    calls = []
    place = Geocoder(fetch=fake(calls)).reverse(41.0002615, 28.7800402, lang="tr")
    assert "Küçükçekmece" in place["name"] and place["country"] == "TR"
    assert "nominatim.openstreetmap.org/reverse" in calls[0] and "accept-language=tr" in calls[0]


def test_a_geocoder_that_is_down_says_so() -> None:
    def down(url):
        raise OSError("no route")
    with pytest.raises(GeocodeError, match="not reachable"):
        Geocoder(fetch=down).search("küçükçekmece")


def test_the_api_passes_through(monkeypatch) -> None:
    monkeypatch.setattr("clause.geocode.MIN_INTERVAL", 0.0)
    app = create_app(trials=200, seed=1, run_chain=False, seed_book=False,
                     settings=Settings(), geocoder=Geocoder(fetch=fake([])))
    with TestClient(app) as client:
        found = client.get("/api/geocode", params={"q": "istanbul küçükçekmece"}).json()
        assert found["places"] and "OpenStreetMap" in found["attribution"]
        here = client.get("/api/reverse", params={"latitude": 41.0, "longitude": 28.78}).json()
        assert here["place"]["country"] == "TR"
        assert client.get("/api/reverse", params={"latitude": 99, "longitude": 0}).status_code == 422
