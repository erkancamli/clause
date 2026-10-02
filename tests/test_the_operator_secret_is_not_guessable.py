"""A wrong operator token is counted wherever it is tried.

POST /api/operator/session says in its own comment that it is limited "hard
and on every attempt rather than on failures, because a token guessed at a
thousand tries a second is not a token". It was the only one of twenty five
routes taking that header that was limited at all. Measured before the fix:

    POST /api/operator/session,  20 wrong tokens -> 401 x8 then 429
    GET  /api/operator/carriers, 400 wrong tokens -> 401 x400, 705 a second
    POST /api/carriers/x/activate, 200 wrong tokens -> 401 x200

so the one door with a lock stood beside twenty four without one, and the
secret behind all of them activates insurers, writes the denylist and reads
every buyer's cover.

Counted in one middleware rather than on each route, so a route added later
is covered without anybody remembering to cover it, and counted rather than
answered: several of these routes answer 404 instead of 401 by design, and a
401 from the middleware would tell a stranger they exist.
"""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import OPERATOR_TOKEN_LEAST, Settings

TOKEN = "operator-token-for-tests"
WRONG = {"x-operator-token": "f" * 48}


@pytest.fixture
def client():
    app = create_app(trials=50, seed=11, run_chain=False, seed_book=False,
                     settings=Settings(operator_token=TOKEN))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def operator_headers():
    return {"x-operator-token": TOKEN}


def test_a_wrong_token_is_refused_and_then_not_even_tried(client) -> None:
    seen = [client.get("/api/operator/carriers", headers=WRONG).status_code
            for _ in range(14)]
    assert 429 in seen, seen
    assert seen[0] == 401, "the first guess is answered like any other refusal"
    assert seen.index(429) <= 11, f"too many guesses before the door shut: {seen}"


def test_the_count_is_shared_by_every_door(client) -> None:
    """Guessing on a different route is the same guessing."""
    doors = ["/api/operator/carriers", "/api/operator/statements",
             "/api/review/applications", "/api/operator/denylist"]
    seen = []
    for _ in range(4):
        for door in doors:
            seen.append(client.get(door, headers=WRONG).status_code)
    assert 429 in seen, seen
    assert seen.index(429) <= 11, seen


def test_a_post_is_counted_too(client) -> None:
    seen = [client.post("/api/carriers/anything/activate", headers=WRONG,
                        json={}).status_code for _ in range(14)]
    assert 429 in seen, seen


def test_the_right_token_is_never_counted(client, operator_headers) -> None:
    """A reviewer working through a list of applications is not an attack."""
    seen = [client.get("/api/operator/carriers", headers=operator_headers).status_code
            for _ in range(30)]
    assert set(seen) == {200}, sorted(set(seen))


def test_a_request_with_no_token_is_not_counted(client) -> None:
    """The header is absent on every ordinary call the site makes."""
    seen = [client.get("/api/health").status_code for _ in range(30)]
    assert set(seen) == {200}


def test_the_refusal_says_how_long_to_wait(client) -> None:
    for _ in range(14):
        reply = client.get("/api/operator/carriers", headers=WRONG)
        if reply.status_code == 429:
            assert "Retry-After" in reply.headers
            assert int(reply.headers["Retry-After"]) > 0
            assert "too many requests" in reply.json()["detail"]
            return
    pytest.fail("the door never shut")


def test_a_short_token_is_said_to_be_short(monkeypatch, capsys) -> None:
    """Said, not refused: a deployment already running on a short token would
    be taken off the air by the release that started refusing it."""
    monkeypatch.setenv("CLAUSE_OPERATOR_TOKEN", "letmein")
    settings = Settings.from_env()
    assert settings.operator_token == "letmein", "it still starts"
    said = capsys.readouterr().err
    assert "WARNING" in said and "7 characters" in said
    assert "openssl rand -hex 32" in said


def test_a_long_enough_token_says_nothing(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CLAUSE_OPERATOR_TOKEN", "a" * OPERATOR_TOKEN_LEAST)
    Settings.from_env()
    assert capsys.readouterr().err == ""


def test_the_token_is_compared_without_refusing_anything() -> None:
    settings = Settings(operator_token="x" * 40)
    assert settings.is_operator_token("x" * 40) is True
    assert settings.is_operator_token("y" * 40) is False
    assert settings.is_operator_token(None) is False
    assert settings.is_operator_token("") is False
    # And a deployment with no token says no to everything, rather than yes
    # to nothing supplied.
    assert Settings().is_operator_token(None) is False
    assert Settings().is_operator_token("anything") is False
