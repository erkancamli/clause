"""A body the app cannot read must still be refused like everything else.

Reproduced: eleven bytes.

    POST /api/auth/register   {"a":1e999}      ->  500

Python's JSON reader accepts 1e999, -1e999, NaN and Infinity; json.dumps
cannot write any of them. FastAPI's validation answer quotes the body back
under "input", so the failure happened *inside* the error handler. What came
out was a 500 raised from outside the layer that sets no-store and the content
type rules, on every route that takes a body, on a path where guard() had
never run so nothing rate limited it, and each one wrote a full traceback to
the log: eleven bytes in, about three kilobytes of log out.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings

NOT_FINITE = ['{"a":1e999}', '{"a":-1e999}', '{"a":NaN}', '{"a":Infinity}',
              '{"a":-Infinity}', '{"public_key":1e999}',
              '{"amount":NaN,"account":"x"}', '{"a":[1e999]}',
              '{"a":{"b":{"c":NaN}}}']

WITH_A_BODY = ["/api/auth/register", "/api/auth/challenge", "/api/quote",
               "/api/contract", "/api/policies", "/api/pool/deposit"]


@pytest.fixture
def client():
    app = create_app(trials=50, seed=3, run_chain=False, seed_book=False,
                     settings=Settings(faucet=True))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def quiet():
    """The handler logs each one, and the point of the test is the volume."""
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.mark.parametrize("body", NOT_FINITE)
def test_a_float_json_cannot_write_is_refused_not_a_fault(client, body) -> None:
    reply = client.post("/api/auth/register", content=body,
                        headers={"content-type": "application/json"})
    assert reply.status_code == 422, (body, reply.status_code)


@pytest.mark.parametrize("route", WITH_A_BODY)
def test_every_route_that_takes_a_body_answers_the_same(client, route) -> None:
    reply = client.post(route, content='{"a":1e999}',
                        headers={"content-type": "application/json"})
    assert reply.status_code == 422, (route, reply.status_code)


def test_the_refusal_still_carries_the_headers_it_must(client) -> None:
    """A 500 raised inside the handler came out from outside the hardening
    layer, so the answer had none of them."""
    reply = client.post("/api/auth/register", content='{"a":1e999}',
                        headers={"content-type": "application/json"})
    assert reply.headers.get("cache-control") == "no-store"
    assert reply.headers.get("x-content-type-options") == "nosniff"


def test_the_body_is_still_described_in_the_answer(client) -> None:
    """Scrubbing must not turn the refusal into a blank: a page sending the
    wrong shape has to be able to see which field."""
    reply = client.post("/api/auth/register", content='{"a":1e999}',
                        headers={"content-type": "application/json"})
    said = reply.json()
    assert said["detail"], said
    assert "public_key" in repr(said), said


def test_an_ordinary_bad_body_is_unchanged(client) -> None:
    for body in ["not json", "", "[]", "{}", '{"public_key":5}',
                 '{"public_key":"' + "A" * 5000 + '"}']:
        reply = client.post("/api/auth/register", content=body,
                            headers={"content-type": "application/json"})
        assert reply.status_code == 422, (body[:40], reply.status_code)
