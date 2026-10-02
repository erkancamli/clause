"""Signing in to review registrations, and what a review leaves behind.

Activation is the one step in this protocol a human performs, and it is the step
that decides whether a company may issue insurance to people. Two things follow,
and this file is about both.

The first is that the credential guarding it is the most valuable secret the
service holds, so it is presented once and exchanged for something that expires,
rather than travelling on every click and living in a form field. The second is
that a decision of that weight with no record of who took it is not a review.
Both were true of the version this replaced, where the step was a curl command
with a token pasted into it.
"""

from __future__ import annotations

import time

import json

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings

TOKEN = "operator-token-for-tests"
YEAR = 365 * 86400


def app_with(**kw):
    book = kw.pop("seed_book", False)
    settings = Settings(operator_token=kw.pop("token", TOKEN), **kw)
    return create_app(
        trials=200, seed=5, run_chain=False, seed_book=book, settings=settings,
    )


@pytest.fixture
def client():
    with TestClient(app_with()) as c:
        yield c


@pytest.fixture
def client_with_a_book():
    """An operator console with policies in it.

    The fixture above buys nothing, and the rule that the console never shows
    a buyer's full address was asserted inside a loop over those policies: it
    ran zero times. Measured by an independent pass: with shorten() removed
    from the endpoint and the function left intact, 99 tests passed. The suite
    tested that shorten() shortens and never that the endpoint calls it.
    """
    with TestClient(app_with(faucet=True, seed_book=True)) as c:
        yield c


def registration(name: str = "Specimen Carrier D, Japan (not a real company)") -> dict:
    return {
        "name": name, "role": "carrier", "domicile": "JP",
        "perils": ["earthquake"], "max_limit": 300_000, "max_term_days": 400,
        "capacity": 5_000_000, "fronting_fee": 0.05,
        "contact": "underwriting@example.com",
        "licences": [{
            "country": "JP", "authority": "Financial Services Agency",
            "reference": "SPECIMEN, no licence exists", "perils": ["earthquake"],
            "reach": "retail", "settlement": ["fiat"],
            "expires_at": time.time() + YEAR,
        }],
    }


def sign_in(client, reviewer: str = "Reviewer") -> str:
    reply = client.post(
        "/api/operator/session", json={"reviewer": reviewer},
        headers={"x-operator-token": TOKEN},
    )
    assert reply.status_code == 200, reply.text
    return reply.json()["token"]


def auth(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


def vet(client, carrier_id: str, headers: dict) -> None:
    """Confirm every required item on the operator's checklist, the way a
    reviewer would before activating; the checklist itself is tested in
    test_vetting.py."""
    items = client.get(f"/api/carriers/{carrier_id}/vetting", headers=headers).json()["items"]
    for item in items:
        if item["required"]:
            assert client.post(f"/api/carriers/{carrier_id}/vetting", headers=headers,
                               json={"key": item["key"], "ok": True, "source": "the register", "note": "seen"}).status_code == 200


# ---------------------------------------------------------------------------
# Getting in
# ---------------------------------------------------------------------------


def test_signing_in_needs_the_operator_token(client) -> None:
    assert client.post("/api/operator/session", json={}).status_code == 401
    assert client.post(
        "/api/operator/session", json={}, headers={"x-operator-token": "guess"}
    ).status_code == 401


def test_a_deployment_with_no_token_has_nothing_to_sign_in_to() -> None:
    """404 rather than 401, because a deployment that set no operator token has
    no reviewer screen at all, and saying "wrong password" would imply there is
    a right one."""
    with TestClient(app_with(token=None)) as bare:
        reply = bare.post(
            "/api/operator/session", json={}, headers={"x-operator-token": "anything"}
        )
        assert reply.status_code == 404


def test_the_session_is_not_the_operator_token(client) -> None:
    token = sign_in(client)
    assert token != TOKEN
    assert len(token) > 24


def test_the_session_opens_the_review_list_and_the_raw_token_still_does(client) -> None:
    """Both, because both are real: a person reviewing in a browser holds a
    session, and a deployment script activating the first carrier holds only the
    token."""
    token = sign_in(client)
    assert client.get("/api/operator/carriers", headers=auth(token)).status_code == 200
    assert client.get(
        "/api/operator/carriers", headers={"x-operator-token": TOKEN}
    ).status_code == 200
    assert client.get("/api/operator/carriers").status_code == 401


def test_signing_out_ends_it_immediately(client) -> None:
    token = sign_in(client)
    assert client.delete("/api/operator/session", headers=auth(token)).status_code == 200
    assert client.get("/api/operator/carriers", headers=auth(token)).status_code == 401


def test_a_session_expires_on_its_own(client) -> None:
    """The reason to have sessions at all. A token left in a browser on a
    borrowed laptop stops working without anyone doing anything."""
    from clause.api.security import Sessions

    sessions = Sessions()
    session = sessions.open("Reviewer", now=1000.0)
    assert sessions.of(session.token, now=1000.0) is session
    assert sessions.of(session.token, now=1000.0 + Sessions.TTL + 1) is None
    # And it is gone rather than merely refused, so an expired session cannot be
    # accumulated by an attacker filling the table.
    assert sessions.of(session.token, now=1000.0) is None


def test_a_forged_session_token_is_not_a_session(client) -> None:
    sign_in(client)
    assert client.get(
        "/api/operator/carriers", headers=auth("x" * 43)
    ).status_code == 401


def test_repeated_attempts_are_rate_limited(client) -> None:
    """A token guessed at a thousand tries a second is not a token. Counted on
    every attempt rather than on failures, so a correct guess mixed into the
    stream does not reset anything."""
    codes = [
        client.post(
            "/api/operator/session", json={}, headers={"x-operator-token": "guess"}
        ).status_code
        for _ in range(12)
    ]
    assert 429 in codes


# ---------------------------------------------------------------------------
# What the reviewer sees
# ---------------------------------------------------------------------------


def test_the_review_list_carries_what_a_decision_needs(client) -> None:
    client.post("/api/carriers", json=registration())
    payload = client.get("/api/operator/carriers", headers=auth(sign_in(client))).json()
    assert payload["pending"] == 1
    company = payload["companies"][0]
    assert company["status"] == "pending"
    assert company["contact"] == "underwriting@example.com"
    assert company["licences"][0]["reference"] == "SPECIMEN, no licence exists"
    assert company["licences"][0]["verified_at"] is None
    assert payload["instruction"]


def test_the_public_list_carries_none_of_it(client) -> None:
    """A company's contact details and the trail of decisions about it are for
    the person deciding, not for everyone who opens the page."""
    client.post("/api/carriers", json=registration())
    company = client.get("/api/carriers").json()["companies"][0]
    assert "contact" not in company
    assert "address" not in company
    assert "reviews" not in company


# ---------------------------------------------------------------------------
# What a decision leaves behind
# ---------------------------------------------------------------------------


def test_activating_records_who_did_it_and_what_they_checked(client) -> None:
    carrier_id = client.post(
        "/api/carriers", json=registration()
    ).json()["carrier"]["carrier_id"]
    token = sign_in(client, "Erkan")
    vet(client, carrier_id, auth(token))

    reply = client.post(
        f"/api/carriers/{carrier_id}/activate",
        json={"note": "checked on the FSA register, 18 September"},
        headers=auth(token),
    )
    assert reply.status_code == 200
    carrier = reply.json()["carrier"]
    assert carrier["status"] == "active"
    assert len(carrier["reviews"]) == 1
    review = carrier["reviews"][0]
    assert review["action"] == "activated"
    assert review["reviewer"] == "Erkan"
    assert review["note"] == "checked on the FSA register, 18 September"
    # And it does not pretend the name was proved. One shared token cannot say
    # which person was holding it.
    assert review["reviewer_self_declared"] is True


def test_suspending_appends_rather_than_erasing(client) -> None:
    """The record of who let a company in survives the decision to remove it,
    which is the only reason the record is worth keeping."""
    carrier_id = client.post(
        "/api/carriers", json=registration()
    ).json()["carrier"]["carrier_id"]
    token = sign_in(client, "Erkan")
    vet(client, carrier_id, auth(token))
    client.post(
        f"/api/carriers/{carrier_id}/activate", json={"note": "checked"},
        headers=auth(token),
    )
    reply = client.post(
        f"/api/carriers/{carrier_id}/suspend",
        json={"note": "licence lapsed, confirmed with the authority"},
        headers=auth(token),
    )
    reviews = reply.json()["carrier"]["reviews"]
    assert [r["action"] for r in reviews] == ["activated", "suspended"]
    assert reviews[0]["note"] == "checked"


def test_a_decision_taken_with_the_raw_token_is_still_attributed(client) -> None:
    carrier_id = client.post(
        "/api/carriers", json=registration()
    ).json()["carrier"]["carrier_id"]
    vet(client, carrier_id, {"x-operator-token": TOKEN})
    reply = client.post(
        f"/api/carriers/{carrier_id}/activate",
        headers={"x-operator-token": TOKEN},
    )
    assert reply.status_code == 200
    assert reply.json()["carrier"]["reviews"][0]["reviewer"] == "operator"


def test_nobody_without_the_token_can_activate_anything(client) -> None:
    """The whole point of the pending state."""
    carrier_id = client.post(
        "/api/carriers", json=registration()
    ).json()["carrier"]["carrier_id"]
    assert client.post(f"/api/carriers/{carrier_id}/activate").status_code == 401
    assert client.post(
        f"/api/carriers/{carrier_id}/activate", headers=auth("not-a-session")
    ).status_code == 401
    assert client.get("/api/carriers").json()["companies"][0]["status"] == "pending"


def test_registering_needs_nothing_at_all(client) -> None:
    """The question this screen answers: a company registering never touches the
    operator's server or credentials. It posts a claim, publicly, and waits."""
    reply = client.post("/api/carriers", json=registration())
    assert reply.status_code == 200
    assert reply.json()["carrier"]["status"] == "pending"


def reinsurer() -> dict:
    return {
        "name": "Specimen Reinsurer (not a real company)", "role": "reinsurer",
        "domicile": "BM", "perils": ["earthquake", "flight_delay"],
        "max_limit": 1_000_000, "capacity": 20_000_000, "licences": [],
    }


def test_a_country_opens_only_after_the_review(client) -> None:
    """End to end, the thing the screen is for, as the live test ran it: a
    Japanese carrier and a reinsurer, each reviewed. Japan opens for the cover
    the protocol can price there: flight delay, and earthquake now that the
    Japanese catalogue model has passed its backtest."""
    def japan() -> dict | None:
        payload = client.get("/api/compliance").json()
        for row in payload["coverage"] + payload["waiting"]:
            if row["country"] == "JP":
                return row
        return None

    body = registration()
    body["perils"] = ["earthquake", "flight_delay"]
    body["licences"][0]["perils"] = ["earthquake", "flight_delay"]
    carrier_id = client.post("/api/carriers", json=body).json()["carrier"]["carrier_id"]
    re_id = client.post("/api/carriers", json=reinsurer()).json()["carrier"]["carrier_id"]
    assert japan() is None, "pending is not licensed"

    token = sign_in(client, "Erkan")
    vet(client, carrier_id, auth(token))
    client.post(f"/api/carriers/{carrier_id}/activate", json={"note": "checked"},
                headers=auth(token))
    row = japan()
    assert row is not None and row["open"] is False
    assert "a reinsurer to stand behind it" in row["waiting_on"]

    vet(client, re_id, auth(token))
    client.post(f"/api/carriers/{re_id}/activate", json={"note": "checked"},
                headers=auth(token))
    row = japan()
    assert row["open"] is True
    assert row["perils"] == ["earthquake", "flight_delay"]
    assert row["unpriced"] == []

    client.post(f"/api/carriers/{carrier_id}/suspend", json={"note": "withdrawn"},
                headers=auth(token))
    assert japan() is None


def test_an_empty_request_is_answered_by_the_token_check_not_the_schema() -> None:
    """A body is optional, so the first thing a caller learns is whether they
    hold the token. Otherwise a 422 would reveal the screen exists on a
    deployment that set no token, which the 404 is there to hide."""
    with TestClient(app_with(token=None)) as bare:
        assert bare.post("/api/operator/session").status_code == 404
    with TestClient(app_with()) as c:
        assert c.post("/api/operator/session").status_code == 401


# ---------------------------------------------------------------------------
# A company's own page, and the operator's view of both sides
# ---------------------------------------------------------------------------


def _signed_registration(client, body):
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from test_privy import device, sign

    key, public = device()
    address = client.post("/api/auth/register", json={"public_key": public}).json()["address"]
    terms = {"name": body["name"], "role": body["role"], "domicile": body["domicile"]}
    challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "register",
                                                         "terms": terms}).json()
    body = {**body, "address": address, "nonce": challenge["nonce"],
            "signature": sign(key, challenge["message"])}
    reply = client.post("/api/carriers", json=body)
    assert reply.status_code == 200, reply.text
    challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "sign-in"}).json()
    session = client.post("/api/auth/verify", json={"address": address, "nonce": challenge["nonce"],
                                                     "signature": sign(key, challenge["message"])}).json()
    return reply.json()["carrier"]["carrier_id"], session["session"]["token"]


def test_a_company_sees_its_own_registration_and_nobody_elses(client) -> None:
    mine, token = _signed_registration(client, registration("Specimen Carrier M (not a real company)"))
    _other, other_token = _signed_registration(client, registration("Specimen Carrier N (not a real company)"))
    page = client.get("/api/company", headers=auth(token)).json()
    assert [c["carrier_id"] for c in page["companies"]] == [mine]
    assert page["companies"][0]["status"] == "pending"
    assert set(page["companies"][0]["book"]) >= {"policies", "in_force", "premiums", "fees", "recent"}
    assert client.get("/api/company").status_code == 401


def test_the_operator_sees_companies_and_buyers(client) -> None:
    token = sign_in(client, "Erkan")
    overview = client.get("/api/operator/overview", headers=auth(token)).json()
    assert set(overview["totals"]) >= {"buyers", "policies", "premiums", "companies", "pending"}
    assert isinstance(overview["policies"], list) and isinstance(overview["companies"], list)
    assert client.get("/api/operator/overview").status_code == 401


def test_the_operator_console_never_shows_a_buyers_whole_address(
        client_with_a_book) -> None:
    """The assertion this used to make inside an empty loop.

    It is asked twice over: that every holder on the page is shortened, and
    that the address the pool holds for that policy does not appear in the
    page at all. The second is the one a reader of the page would notice, and
    the one a shortening that forgets a case would still fail.
    """
    client = client_with_a_book
    token = sign_in(client, "Erkan")
    overview = client.get("/api/operator/overview", headers=auth(token)).json()
    rows = overview["policies"]
    assert rows, "the console has no policies, so this test proves nothing"

    said = json.dumps(overview, ensure_ascii=False)
    pool = client.app.state.pool
    whole = {p.holder for p in pool.policies.values() if p.holder}
    assert whole, "the book has no holders, so this test proves nothing"
    for address in whole:
        assert address not in said, f"{address} is on the operator console whole"
    for row in rows:
        holder = row["holder"]
        assert "…" in holder or len(holder) <= 13, holder
