"""The two live feeds on the home page.

Nothing here is priced or settled on, so the tests are about the things that
would embarrass the page: showing an explosion as an earthquake, alarming people
about an airport closed only to light aircraft, going blank when a source
hiccups, or fetching once per visitor.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from clause.live import Feed, parse_faa, parse_quakes, quake_feed, flight_feed


def quake(mag, *, ago=600.0, kind="earthquake", place="10 km N of Somewhere"):
    return {
        "id": f"q{mag}{ago}", "type": "Feature",
        "properties": {"mag": mag, "place": place, "time": (time.time() - ago) * 1000,
                       "type": kind, "magType": "mb", "url": "https://example.org/q",
                       "tsunami": 0, "alert": None},
        "geometry": {"type": "Point", "coordinates": [139.7, 35.6, 10.0]},
    }


def geojson(*features) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": list(features)}).encode()


def test_only_earthquakes_are_shown() -> None:
    rows = parse_quakes(geojson(quake(4.5), quake(4.6, kind="quarry blast")))
    assert [r["magnitude"] for r in rows] == [4.5]


def test_the_ticker_leads_with_what_the_world_would_notice() -> None:
    """The day feed is mostly magnitude 2.5 in Alaska and California."""
    small = [quake(2.6, ago=60 + i) for i in range(30)]
    big = [quake(5.0 + i / 10, ago=3000 + i) for i in range(14)]
    rows = parse_quakes(geojson(*small, *big))
    assert all(r["magnitude"] >= 4.0 for r in rows)


def test_a_quiet_day_is_filled_with_the_most_recent_small_ones() -> None:
    rows = parse_quakes(geojson(quake(4.2), *[quake(2.6, ago=100 + i) for i in range(20)]))
    assert len(rows) == 12
    assert rows == sorted(rows, key=lambda r: r["at"], reverse=True)


def test_anything_older_than_a_day_is_dropped() -> None:
    assert parse_quakes(geojson(quake(6.0, ago=3 * 86400))) == []


FAA = b"""<AIRPORT_STATUS_INFORMATION><Update_Time>now</Update_Time>
<Delay_type><Name>Ground Stop Programs</Name><Ground_Stop_List><Program>
<ARPT>EWR</ARPT><Reason>thunderstorms</Reason><End_Time>9:30 pm EDT</End_Time>
</Program></Ground_Stop_List></Delay_type>
<Delay_type><Name>Ground Delay Programs</Name><Ground_Delay_List><Ground_Delay>
<ARPT>ORD</ARPT><Reason>WEATHER / LOW CEILINGS</Reason><Avg>1 hour and 12 minutes</Avg>
<Max>2 hours and 5 minutes</Max></Ground_Delay></Ground_Delay_List></Delay_type>
<Delay_type><Name>General Arrival/Departure Delay Info</Name><Arrival_Departure_Delay_List>
<Delay><ARPT>SFO</ARPT><Reason>VOL:Volume</Reason><Arrival_Departure Type="Arrival">
<Min>16 minutes</Min><Max>30 minutes</Max><Trend>Increasing</Trend></Arrival_Departure></Delay>
</Arrival_Departure_Delay_List></Delay_type>
<Delay_type><Name>Airport Closures</Name><Airport_Closure_List>
<Airport><ARPT>LGA</ARPT><Reason>!LGA 09/271 LGA AD AP CLSD EXC HEL</Reason><Start>Sep 19 at 04:01 UTC.</Start><Reopen>Sep 19 at 10:00 UTC.</Reopen></Airport>
<Airport><ARPT>LAX</ARPT><Reason>!LAX AD AP CLSD TO NON SKED TRANSIENT GA ACFT</Reason><Start>x</Start><Reopen>May 28 at 16:00 UTC.</Reopen></Airport>
</Airport_Closure_List></Delay_type></AIRPORT_STATUS_INFORMATION>"""


def test_every_kind_of_faa_disruption_is_read_and_ranked() -> None:
    rows = parse_faa(FAA)
    assert [r["kind"] for r in rows] == ["ground_stop", "ground_delay", "arrival_delay", "closed"]
    ord_ = rows[1]
    assert ord_["average_minutes"] == 72 and ord_["max_minutes"] == 125
    assert ord_["cause"] == "weather" and ord_["name"] == "Chicago O'Hare"
    assert rows[2]["cause"] == "volume" and rows[2]["max_minutes"] == 30
    assert rows[3]["airport"] == "LGA" and rows[3]["until_at"]


def test_a_closure_only_to_light_aircraft_is_not_an_alarm() -> None:
    assert "LAX" not in {r["airport"] for r in parse_faa(FAA)}


def test_a_feed_that_declares_entities_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_faa(b'<!DOCTYPE x [<!ENTITY a "b">]><AIRPORT_STATUS_INFORMATION/>')


def test_a_failure_keeps_the_last_good_answer_and_says_it_is_stale() -> None:
    calls = {"n": 0}

    def fetcher(url):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("down")
        return geojson(quake(5.1))

    feed = quake_feed(fetcher=fetcher)
    first = feed.read(now=time.time())
    assert first["items"] and not first["stale"]
    later = feed.read(now=time.time() + 120)
    assert later["items"] == first["items"]
    assert later["stale"] is True


def test_the_source_is_asked_at_most_once_per_interval() -> None:
    calls = {"n": 0}

    def fetcher(url):
        calls["n"] += 1
        return geojson(quake(5.1))

    feed = quake_feed(fetcher=fetcher)
    now = time.time()
    for i in range(50):
        feed.read(now=now + i)
    assert calls["n"] == 1


def test_the_api_serves_both_and_says_what_it_covers() -> None:
    from clause.api.app import create_app
    from clause.api.security import Settings

    def fetcher(url):
        return FAA if "faa" in url else geojson(quake(5.3))

    app = create_app(trials=200, run_chain=False, seed_book=False,
                     settings=Settings(), live_fetcher=fetcher)
    with TestClient(app) as client:
        quakes = client.get("/api/live/quakes").json()
        flights = client.get("/api/live/flights").json()
    assert quakes["items"][0]["magnitude"] == 5.3 and quakes["source"] == "USGS"
    assert flights["coverage"] == "United States airports"
    assert flights["items"][0]["kind"] == "ground_stop"


# ---------------------------------------------------------------------------
# One country at a time
# ---------------------------------------------------------------------------


def test_usgs_place_text_is_read_as_a_country() -> None:
    from clause.countries import code_for

    for text, code in (("40 km SW of Hualien City, Taiwan", "TW"), ("5 km NE of Ridgecrest, CA", "US"),
                       ("off the east coast of Honshu, Japan", "JP"), ("12 km S of Sındırgı, Turkey", "TR"),
                       ("south of the Kermadec Islands", "NZ"), ("10 km SW of Ensenada, B.C., MX", "MX"),
                       ("Mid-Atlantic Ridge", None)):
        assert code_for(text) == code, text


def live_client(fetcher, **env):
    from clause.api.app import create_app
    from clause.api.security import Settings

    return TestClient(create_app(trials=200, run_chain=False, seed_book=False,
                                 settings=Settings(), live_fetcher=fetcher))


def test_a_country_sees_only_its_own_earthquakes() -> None:
    day = geojson(quake(4.1, place="20 km E of Iwaki, Japan"), quake(3.0, ago=700, place="Hualien, Taiwan"),
                  *[quake(2.7, ago=800 + i, place="3 km N of Iwaki, Japan") for i in range(4)])
    with live_client(lambda url: day) as client:
        japan = client.get("/api/live/quakes", params={"country": "jp"}).json()
    assert japan["country"] == "JP" and japan["window"] == "day"
    assert len(japan["items"]) == 5
    assert all(q["country"] == "JP" for q in japan["items"])


def test_a_quiet_country_is_shown_its_week() -> None:
    day = geojson(quake(4.1, place="20 km E of Iwaki, Japan"))
    week = geojson(*[quake(3.1, ago=86400 * d, place="Kadıköy, Turkey") for d in (2, 3, 4, 5)])

    def fetcher(url):
        return week if "week" in url else day

    with live_client(fetcher) as client:
        turkey = client.get("/api/live/quakes", params={"country": "TR"}).json()
    assert turkey["window"] == "week" and len(turkey["items"]) == 4


def test_flights_outside_the_united_states_say_there_is_no_feed(monkeypatch) -> None:
    monkeypatch.delenv("CLAUSE_AEROAPI_KEY", raising=False)
    with live_client(lambda url: FAA) as client:
        japan = client.get("/api/live/flights", params={"country": "JP"}).json()
        usa = client.get("/api/live/flights", params={"country": "US"}).json()
    assert japan["available"] is False and japan["items"] == []
    assert usa["available"] is True and usa["items"]


def test_aeroapi_rows_are_placed_by_icao_prefix(monkeypatch) -> None:
    from clause.live import icao_country, parse_aeroapi

    assert icao_country("RJTT") == "JP" and icao_country("LTFM") == "TR"
    assert icao_country("KJFK") == "US" and icao_country("EGLL") == "GB"
    raw = json.dumps({"delays": [
        {"airport": "RJTT", "delay_secs": 2700, "reasons": [{"reason": "Weather / Wind"}]},
        {"airport": "LTFM", "delay_secs": 900, "reasons": []},
    ]}).encode()
    rows = parse_aeroapi(raw)
    assert [r["country"] for r in rows] == ["JP", "TR"]
    assert rows[0]["average_minutes"] == 45 and rows[0]["cause"] == "weather"

    monkeypatch.setenv("CLAUSE_AEROAPI_KEY", "test")
    with live_client(lambda url: raw if "aeroapi" in url else FAA) as client:
        japan = client.get("/api/live/flights", params={"country": "JP"}).json()
    assert japan["available"] is True and japan["source"] == "FlightAware"
    assert [r["airport"] for r in japan["items"]] == ["RJTT"]
