"""The tally, and the three things that keep it a tally rather than a record.

A funnel is normally built by following people. That is not possible here and
not wanted: no name, no email address, no cookie, no session. What is kept is
how many prices were asked for and how many purchases followed. Each test
below names a way such a count stops being safe or stops being honest.
"""

from __future__ import annotations

import datetime as dt
import inspect

from clause.protocol import counting
from clause.protocol.counting import KEEP_DAYS, STAGES, Counting, Day, day_of


def at(day: str, hour: int = 12) -> float:
    return dt.datetime.fromisoformat(day).replace(hour=hour, tzinfo=dt.timezone.utc).timestamp()


def test_nothing_that_identifies_anybody_can_be_counted() -> None:
    """The argument list is the guarantee: there is nowhere to put a person,
    so nothing about one can reach the tally even by mistake."""
    taken = set(inspect.signature(Counting.count).parameters)
    assert taken == {"self", "stage", "peril", "when"}, taken

    # And nothing about a person can come out of it either: whatever is
    # counted, a day holds stage names and stage/peril pairs and nothing else.
    book = Counting()
    book.count("priced", "earthquake", when=at("2026-09-23"))
    book.count("bought", when=at("2026-09-23"))
    for key in book.days["2026-09-23"].counts:
        stage, _, peril = key.partition("/")
        assert stage in STAGES, key
        assert peril in ("", "earthquake"), key
    # A day is two fields: which day, and the numbers. Nowhere to hide a person.
    assert set(Day.__slots__) == {"day", "counts"}


def test_a_day_is_the_finest_time_it_holds() -> None:
    book = Counting()
    morning, evening = at("2026-09-23", 1), at("2026-09-23", 23)
    book.count("priced", when=morning)
    book.count("priced", when=evening)
    assert list(book.days) == ["2026-09-23"]
    assert book.days["2026-09-23"].counts["priced"] == 2
    assert day_of(morning) == day_of(evening) == "2026-09-23"


def test_addition_is_the_only_thing_it_does() -> None:
    """A tally that could be rewritten backwards would be worse than none."""
    for name in dir(Counting):
        assert not name.startswith(("set", "remove", "delete", "reset", "clear", "adjust")), \
            f"Counting.{name} would let the record be rewritten"
    book = Counting()
    book.count("bought", when=at("2026-09-01"))
    book.count("not a stage", when=at("2026-09-01"))      # ignored, never raised
    assert book.totals(400) == {"bought": 1}


def test_the_share_is_of_requests_and_says_so() -> None:
    book = Counting()
    for _ in range(10):
        book.count("priced", "earthquake", when=at("2026-09-23"))
    for _ in range(2):
        book.count("bought", "earthquake", when=at("2026-09-23"))
    funnel = book.funnel(30)
    rows = {r["stage"]: r for r in funnel["stages"]}
    assert [r["stage"] for r in funnel["stages"]] == list(STAGES)
    assert rows["priced"]["count"] == 10 and rows["bought"]["of_priced"] == 0.2
    assert rows["applied"]["count"] == 0
    assert "not of people" in funnel["note"]
    assert funnel["by_peril"] == {"bought/earthquake": 2, "priced/earthquake": 10}


def test_an_empty_tally_does_not_invent_a_ratio() -> None:
    book = Counting()
    assert all(r["of_priced"] is None for r in book.funnel(30)["stages"])


def test_old_days_fall_off_and_recent_ones_do_not() -> None:
    book = Counting()
    start = dt.date(2024, 1, 1)
    for n in range(KEEP_DAYS + 30):
        book.count("priced", when=at((start + dt.timedelta(days=n)).isoformat()))
    assert len(book.days) == KEEP_DAYS
    assert (start + dt.timedelta(days=KEEP_DAYS + 29)).isoformat() in book.days
    assert start.isoformat() not in book.days


def test_the_last_thirty_days_are_the_last_thirty_written() -> None:
    book = Counting()
    start = dt.date(2026, 1, 1)
    for n in range(60):
        book.count("priced", when=at((start + dt.timedelta(days=n)).isoformat()))
    recent = book.since(30)
    assert len(recent) == 30
    assert recent[0].day == (start + dt.timedelta(days=30)).isoformat()
    assert recent[-1].day == (start + dt.timedelta(days=59)).isoformat()


def test_the_tally_is_the_operator_s_and_carries_nothing_about_anybody() -> None:
    from fastapi.testclient import TestClient
    from clause.api.app import create_app
    from clause.api.security import Settings

    app = create_app(trials=200, run_chain=False, seed_book=False,
                     settings=Settings(operator_token="op-token"))
    with TestClient(app) as client:
        assert client.get("/api/operator/funnel").status_code == 401
        assert client.get("/api/operator/funnel", headers={"x-operator-token": "wrong"}).status_code == 401

        subject = {"location": "IST-KADIKOY", "radius_km": 50}
        priced = client.post("/api/quote", json={"peril": "earthquake", "subject": subject,
                                                 "limit": 50_000, "term_days": 365})
        assert priced.status_code == 200, priced.text

        seen = client.get("/api/operator/funnel", headers={"x-operator-token": "op-token"})
        assert seen.status_code == 200, seen.text
        report = seen.json()
        rows = {r["stage"]: r for r in report["stages"]}
        assert rows["priced"]["count"] == 1
        assert rows["bought"]["count"] == 0 and rows["bought"]["of_priced"] == 0.0
        assert report["by_peril"] == {"priced/earthquake": 1}
        # One day, two fields, numbers only.
        assert [set(d) for d in report["by_day"]] == [{"day", "counts"}]
        assert all(isinstance(v, int) for v in report["by_day"][0]["counts"].values())
