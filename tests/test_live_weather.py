"""The weather band on the home page, read from Open-Meteo in chunks.

The deployment read nothing for Türkiye for days: eighty one places in one
answer, over a slow line, inside one timeout, while five cities of Germany
came back at once. These tests are about that shape of failure: a chunk that
fails must cost its own places only, the page must be able to say why a feed
read nothing, and a subscription key must reach the customer host without
breaking the read when the host refuses it.
"""

from __future__ import annotations

import json
import time
import urllib.error

import pytest

from clause.live import (
    Feed, WEATHER_CHUNK, fetch_weather, parse_weather, subscribed_url, weather_feed, weather_points,
)


def places(n: int) -> list[tuple[str, float, float]]:
    return [(f"Place {i}", 36.0 + i * 0.1, 30.0 + i * 0.1) for i in range(n)]


def answer(n: int, rain: float = 1.0) -> bytes:
    return json.dumps([{"daily": {"precipitation_sum": [rain], "temperature_2m_max": [20.0],
                                  "temperature_2m_min": [10.0], "wind_gusts_10m_max": [30.0],
                                  "weather_code": [61]}} for _ in range(n)]).encode()


def count_places(url: str) -> int:
    lat = url.split("latitude=")[1].split("&")[0]
    return len(lat.split(","))


def test_turkiye_is_read_in_chunks_not_in_one_answer() -> None:
    asked: list[int] = []

    def fetcher(url: str) -> bytes:
        asked.append(count_places(url))
        return answer(asked[-1])

    points = weather_points("TR")
    rows = parse_weather(fetch_weather(points, fetcher, pause=0), points)
    assert len(points) == 81
    assert len(asked) == -(-81 // WEATHER_CHUNK) and max(asked) <= WEATHER_CHUNK
    assert sum(asked) == 81
    assert [r["place"] for r in rows] and len(rows) == 81


def test_a_chunk_that_fails_costs_only_its_own_places() -> None:
    calls = {"n": 0}

    def fetcher(url: str) -> bytes:
        calls["n"] += 1
        if calls["n"] == 2:
            raise TimeoutError("The read operation timed out")
        return answer(count_places(url))

    points = places(45)
    rows = parse_weather(fetch_weather(points, fetcher, pause=0), points)
    assert len(rows) == 45 - WEATHER_CHUNK
    assert all(r["rain_mm"] == 1.0 for r in rows)
    # The places of the failed chunk are missing, not shown as a dry day.
    missing = {p[0] for p in points[WEATHER_CHUNK:2 * WEATHER_CHUNK]}
    assert not missing & {r["place"] for r in rows}


def test_when_no_chunk_answers_the_feed_says_why() -> None:
    def fetcher(url: str) -> bytes:
        raise TimeoutError("The read operation timed out")

    feed = weather_feed("TR", fetcher=fetcher, background=False)
    reply = feed.read(now=5000.0)
    assert reply["items"] == [] and reply["stale"] is True and reply["fetched_at"] is None
    assert "TimeoutError" in reply["error"] and "timed out" in reply["error"]


def test_the_long_list_is_read_in_the_background_and_answers_at_once() -> None:
    import threading

    gate = threading.Event()
    served = threading.Event()

    def fetcher(url: str) -> bytes:
        gate.wait(5.0)
        served.set()
        return answer(count_places(url))

    feed = weather_feed("TR", fetcher=fetcher)
    assert feed.background is True
    first = feed.read(now=5000.0)
    assert first["items"] == [] and first["refreshing"] is True and first["stale"] is True
    # A second reader meanwhile does not start a second fetch and does not wait.
    assert feed.read(now=5001.0)["refreshing"] is True
    gate.set()
    for _ in range(200):
        if not feed.busy:
            break
        time.sleep(0.02)
    later = feed.read(now=5002.0)
    assert len(later["items"]) == 81 and "refreshing" not in later and later["stale"] is False


def test_the_short_lists_are_still_read_on_the_spot() -> None:
    feed = weather_feed("DE", fetcher=lambda url: answer(count_places(url)))
    assert feed.background is False
    assert len(feed.read(now=5000.0)["items"]) == 5


def test_a_feed_that_answers_carries_no_error_field() -> None:
    feed = Feed(name="x", url="u", parse=lambda raw: [{"a": 1}], interval=10.0,
                source="s", coverage="c", fetcher=lambda url: b"")
    reply = feed.read(now=1000.0)
    assert reply["items"] == [{"a": 1}] and "error" not in reply


def test_an_answer_that_does_not_line_up_with_the_places_is_refused() -> None:
    points = places(5)
    with pytest.raises(RuntimeError) as caught:
        fetch_weather(points, lambda url: answer(3), pause=0)
    assert "5 places" in str(caught.value) and "3 answers" in str(caught.value)


def test_the_big_lists_are_read_half_as_often() -> None:
    assert weather_feed("TR", fetcher=lambda url: b"[]").interval == 1800.0
    assert weather_feed("DE", fetcher=lambda url: b"[]").interval == 900.0


def test_a_subscription_key_moves_the_query_to_the_customer_host(monkeypatch) -> None:
    monkeypatch.delenv("CLAUSE_OPENMETEO_KEY", raising=False)
    url = "https://api.open-meteo.com/v1/forecast?latitude=1&longitude=2"
    assert subscribed_url(url) is None
    monkeypatch.setenv("CLAUSE_OPENMETEO_KEY", "abc/def")
    moved = subscribed_url(url)
    assert moved.startswith("https://customer-api.open-meteo.com/v1/forecast?")
    assert moved.endswith("&apikey=abc%2Fdef")


def test_a_refused_key_falls_back_to_the_free_host_for_that_chunk(monkeypatch) -> None:
    monkeypatch.setenv("CLAUSE_OPENMETEO_KEY", "wrong")
    seen: list[str] = []

    def fetcher(url: str) -> bytes:
        seen.append(url.split("/")[2])
        if "customer-" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        return answer(count_places(url))

    points = places(3)
    rows = parse_weather(fetch_weather(points, fetcher, pause=0), points)
    assert len(rows) == 3
    assert seen == ["customer-api.open-meteo.com", "api.open-meteo.com"]


def test_a_refused_chunk_is_asked_for_once_more_after_a_breath() -> None:
    calls = {"n": 0}
    naps: list[float] = []

    def fetcher(url: str) -> bytes:
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return answer(count_places(url))

    points = places(3)
    rows = parse_weather(fetch_weather(points, fetcher, pause=0.5, sleep=naps.append), points)
    assert len(rows) == 3 and calls["n"] == 2 and naps == [2.0]


def test_a_quota_refusal_on_the_customer_host_is_not_hidden(monkeypatch) -> None:
    monkeypatch.setenv("CLAUSE_OPENMETEO_KEY", "spent")

    def fetcher(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    with pytest.raises(RuntimeError) as caught:
        fetch_weather(places(2), fetcher, pause=0)
    assert "429" in str(caught.value)
