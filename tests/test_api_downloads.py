"""The name on a file the app hands back, which a caller was choosing.

Five responses built their content-disposition by interpolating a value into
a quoted string, and one of those values is a query parameter. Measured
against the running app before this:

    month='a"'      ->  filename="all-a".csv"       the quote closes it early
    month='"; x="'  ->  filename="all-"; x=".csv"   a second parameter
    month='ş'       ->  500

The 500 is the plainest: a header must be latin-1, and the encoding happens
inside the response after the route has returned, so nothing catches it and
nothing says why. The other two let a caller choose the name a browser saves
the file under, and add parameters of their own to the header.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from clause.api.app import attachment, create_app
from clause.api.security import Settings

TOKEN = "operator-token-for-tests"

#: Anything a caller could put in that is not a filename.
AWKWARD = ['a b', 'a"', '"; x="', 'ş', 'é', '../../etc/passwd', '...', '',
           'a;b', "a'b", 'a\tb', 'a\\b', 'a/b']


@pytest.fixture
def client():
    app = create_app(trials=100, seed=3, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def operator(client) -> dict:
    token = client.post("/api/operator/session", json={"reviewer": "R"},
                        headers={"x-operator-token": TOKEN}).json()["token"]
    return {"authorization": f"Bearer {token}"}


# -- the header itself ------------------------------------------------------

@pytest.mark.parametrize("given", AWKWARD + ["2026-09", "CLS-ABC123-contract.txt"])
def test_the_header_is_one_parameter_and_latin_one(given: str) -> None:
    header = attachment(f"all-{given}.csv")
    value = header["content-disposition"]
    assert value.startswith('attachment; filename="')
    assert value.endswith('.csv"') or value.endswith('"')
    # One quoted name, nothing after it.
    assert value.count('"') == 2, value
    assert ";" not in value[len("attachment; "):], value
    value.encode("latin-1")          # raises if a header could not carry it
    assert "/" not in value and "\\" not in value, value


def test_a_name_with_nothing_left_of_it_falls_back() -> None:
    for nothing in ("", "...", "---", '"', "ş", "..."):
        assert attachment(nothing)["content-disposition"] == \
            'attachment; filename="download.csv"'
    assert attachment("", named="contract.txt")["content-disposition"] == \
        'attachment; filename="contract.txt"'


def test_an_ordinary_name_is_left_alone() -> None:
    for plain in ("all-2026-09.csv", "CLS-ABC123-contract.txt", "c1-2026-01.csv"):
        assert attachment(plain)["content-disposition"] == \
            f'attachment; filename="{plain}"'


def test_a_long_name_is_cut_rather_than_sent() -> None:
    value = attachment("a" * 500 + ".csv")["content-disposition"]
    assert len(value) < 160, len(value)


# -- and through the routes -------------------------------------------------

@pytest.mark.parametrize("month", AWKWARD)
def test_the_statement_download_answers_rather_than_raising(client, month) -> None:
    reply = client.get("/api/operator/statements",
                       params={"format": "csv", "month": month},
                       headers=operator(client))
    assert reply.status_code in (200, 404, 422), (month, reply.status_code)
    said = reply.headers.get("content-disposition")
    if said is not None:
        assert said.count('"') == 2, said
        said.encode("latin-1")


def test_the_download_still_arrives_named(client) -> None:
    """Sanitising is not the same as removing: the file still has a name a
    browser will save it under."""
    reply = client.get("/api/operator/statements",
                       params={"format": "csv", "month": "2026-09"},
                       headers=operator(client))
    assert reply.status_code == 200, reply.text
    assert reply.headers["content-disposition"] == \
        'attachment; filename="all-2026-09.csv"'
    assert reply.headers["content-type"].startswith("text/csv")
