"""Two endpoints that are meant not to exist, on a deployment that has them off.

deploy/README.md says of POST /api/chain/inject and POST /api/chain/silence
that "with CLAUSE_DEMO unset they return 404, so they do not [exist]", and
require_operator answers 404 for exactly that reason. FastAPI validates query
parameters before the route runs, so an anonymous caller who left them out
was told their names and their types instead:

    POST /api/chain/inject  ->  422  query.reference, query.field, query.value
    POST /api/chain/inject?reference=x&field=y&value=1  ->  404

Nothing was reachable either way. What leaked was that the doors are there,
and what to send them.

The parameters are optional now and the operator check is the first thing in
each route, so every shape of the request answers 404. With the switch on
and the right token, a request that is actually missing something still gets
the same 422 it always did.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings

TOKEN = "t" * 40
OP = {"x-operator-token": TOKEN}
SHAPES = ("/api/chain/inject",
          "/api/chain/inject?reference=x",
          "/api/chain/inject?reference=x&field=y&value=1",
          "/api/chain/silence",
          "/api/chain/silence?reference=x")


@pytest.fixture
def shut():
    """A deployment with the demonstration switch off, which is a real one."""
    app = create_app(trials=20, seed=1, run_chain=False, seed_book=False,
                     settings=Settings())
    with TestClient(app) as c:
        yield c


@pytest.fixture
def open_for_the_demo():
    app = create_app(trials=20, seed=1, run_chain=False, seed_book=True,
                     settings=Settings(demo_endpoints=True, operator_token=TOKEN))
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", SHAPES)
def test_every_shape_of_the_request_answers_the_same(shut, path) -> None:
    reply = shut.post(path)
    assert reply.status_code == 404, (path, reply.status_code, reply.text[:160])
    assert reply.json() == {"detail": "not found"}


@pytest.mark.parametrize("path", SHAPES)
def test_a_wrong_token_learns_nothing_either(shut, path) -> None:
    reply = shut.post(path, headers={"x-operator-token": "f" * 40})
    assert reply.status_code == 404, (path, reply.status_code)


def test_the_parameters_are_still_required_where_the_doors_are_open(open_for_the_demo) -> None:
    reply = open_for_the_demo.post("/api/chain/inject", headers=OP)
    assert reply.status_code == 422
    missing = {tuple(d["loc"]) for d in reply.json()["detail"]}
    assert missing == {("query", "reference"), ("query", "field"), ("query", "value")}

    reply = open_for_the_demo.post("/api/chain/silence", headers=OP)
    assert reply.status_code == 422
    assert [tuple(d["loc"]) for d in reply.json()["detail"]] == [("query", "reference")]


def test_and_they_still_do_what_they_are_for() -> None:
    """The same source the older test attests against, through the same door."""
    from urllib.parse import quote as urlquote

    app = create_app(trials=300, seed=5, run_chain=False, seed_book=True,
                     settings=Settings(demo_endpoints=True, operator_token=TOKEN))
    with TestClient(app) as c:
        reference = urlquote(
            "api.seismic.example/v1/max-magnitude?lat=40.99&lon=29.03&radius_km=50",
            safe="")
        done = c.post(f"/api/chain/inject?reference={reference}&field=max_magnitude&value=7.2",
                      headers=OP)
        assert done.status_code == 200, done.text[:200]
        # Near 7.2 rather than 7.2: what comes back is the validators' median
        # of what they each reported, which is the whole point of the route.
        assert 6.9 < done.json()["fields"]["max_magnitude"] < 7.5, done.json()["fields"]
        assert c.post("/api/chain/inject?reference=nope&field=y&value=1",
                      headers=OP).status_code == 404
        assert c.post("/api/chain/silence?reference=nope", headers=OP).status_code == 404
