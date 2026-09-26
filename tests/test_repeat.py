"""Asking twice, when the first answer went missing.

The hole this closes is the one a buyer meets most often and can do least
about. A purchase is one POST. If its reply is lost on the way back -- a phone
changing network, a proxy dropping the connection, the protocol being replaced
mid-request -- the browser cannot tell a request that was never read from one
that was read and acted on. It used to have to assume the worst and say so, and
the worst was usually wrong: the cover was already theirs.
"""

from __future__ import annotations

import pytest

from clause.api.repeat import Answers


# ---------------------------------------------------------------------------
# The store on its own
# ---------------------------------------------------------------------------


def test_the_same_request_gets_the_answer_it_already_got() -> None:
    kept = Answers()
    kept.keep("nonce-1", "signature-1", status=200, body={"application": {"app_id": "APP-1"}})
    again = kept.recall("nonce-1", "signature-1")
    assert again is not None and again.status == 200
    assert again.body["application"]["app_id"] == "APP-1"


def test_a_different_request_gets_nothing() -> None:
    kept = Answers()
    kept.keep("nonce-1", "signature-1", status=200, body={"application": {}})
    assert kept.recall("nonce-2", "signature-1") is None


def test_a_spent_nonce_beside_a_guessed_signature_reads_nothing() -> None:
    """A nonce is public the moment it is presented. It must not become a way
    to read somebody's application by guessing at the signature beside it."""
    kept = Answers()
    kept.keep("nonce-1", "signature-1", status=200, body={"application": {"app_id": "APP-1"}})
    assert kept.recall("nonce-1", "signature-2") is None
    assert kept.recall("nonce-1", "") is None
    assert kept.recall("nonce-1", "signature-11") is None


def test_the_first_answer_stands() -> None:
    """If a repeat somehow reached the work, it must not overwrite the answer
    it was supposed to be given."""
    kept = Answers()
    kept.keep("n", "s", status=200, body={"application": {"app_id": "APP-1"}})
    kept.keep("n", "s", status=409, body="no")
    assert kept.recall("n", "s").status == 200


def test_an_answer_is_not_kept_for_ever() -> None:
    """It exists to cover the seconds after a lost reply, not to be a record."""
    kept = Answers(seconds=60.0)
    kept.keep("n", "s", status=200, body={}, now=1_000.0)
    assert kept.recall("n", "s", now=1_050.0) is not None
    assert kept.recall("n", "s", now=1_100.0) is None
    assert len(kept) == 0


def test_a_flood_of_purchases_cannot_grow_it_without_bound() -> None:
    kept = Answers(most=8)
    for i in range(50):
        kept.keep(f"n{i}", "s", status=200, body={"i": i}, now=1_000.0 + i)
    assert len(kept) <= 8
    # The oldest went first, so the most recent purchases are the recoverable ones.
    assert kept.recall("n49", "s", now=1_050.0) is not None
    assert kept.recall("n0", "s", now=1_050.0) is None


def test_nothing_is_kept_for_a_request_with_no_nonce() -> None:
    kept = Answers()
    kept.keep("", "s", status=200, body={})
    kept.keep("n", "", status=200, body={})
    assert len(kept) == 0


# ---------------------------------------------------------------------------
# Through the door a buyer uses
# ---------------------------------------------------------------------------


WHERE = {"location": "IST-KADIKOY", "radius_km": 50}
HOME = {"kind": "home", "building": "flat", "area_m2": 120, "built": 2010}
ADDRESS = {"street": "Atakent Mah 223 Cadde", "number": "A2", "flat": "49",
           "postcode": "34307", "city": "Istanbul"}


@pytest.fixture()
def buying():
    from fastapi.testclient import TestClient

    from clause.api.app import Settings, create_app

    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token="devtoken"))
    with TestClient(app) as client:
        yield client, app


def body_for(client, address, device, *, limit=50_000.0, risk=60_000.0, at=ADDRESS,
             quote_id=None):
    """The application a page sends, signed, ready to be sent more than once.

    `quote_id` is a price promised for ten minutes. It goes to the contract as
    well as into the body, because the contract text carries the premium: asking
    for the contract at one price and then buying at another is a contract the
    buyer did not read.
    """
    from test_api_security import statements

    terms = {"peril": "earthquake", "limit": limit, "term_days": 365.0,
             "subject": WHERE, "country": "TR", "value_at_risk": risk, "size": HOME}
    interest = {"what": "evim", "country": "TR", "inside_trigger_area": True,
                "value_at_risk": risk, "size": HOME, "address": at}
    # The contract the buyer read, as the page fetches it: its hash is signed
    # over, so nobody is bound to text they were not shown.
    asked = {**terms, "interest": interest, "settlement": "fiat"}
    if quote_id:
        asked["quote_id"] = quote_id
    shown = client.post("/api/contract", json=asked)
    digest = shown.json().get("hash", "") if shown.status_code == 200 else ""
    if digest:
        terms["contract_hash"] = digest
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms}).json()
    return {
        "peril": "earthquake", "subject": WHERE, "limit": limit, "term_days": 365.0,
        "holder": address, "nonce": challenge["nonce"],
        "signature": device.sign(challenge["message"]), "settlement": "fiat",
        "contract_hash": digest or None,
        "quote_id": quote_id,
        "attestations": statements(client, address, "sanctions_clear", "identity_basic"),
        "interest": interest,
    }


def joins(client):
    from test_api_security import Device

    device = Device()
    address = client.post("/api/auth/register",
                          json={"public_key": device.public}).json()["address"]
    return device, address


def test_a_lost_reply_is_asked_for_again_and_buys_nothing_more(buying) -> None:
    client, app = buying
    device, me = joins(client)
    body = body_for(client, me, device)

    first = client.post("/api/applications", json=body)
    assert first.status_code == 200, first.text
    app_id = first.json()["application"]["app_id"]
    held = len(app.state.applications.applications)

    # The same request, as a page that heard nothing would send it.
    second = client.post("/api/applications", json=body)
    assert second.status_code == 200, second.text
    assert second.json()["application"]["app_id"] == app_id
    assert len(app.state.applications.applications) == held, (
        "asking again must not write a second application")


def test_asking_again_is_given_no_new_way_in(buying) -> None:
    """A signature that travelled once may have been captured, and holding a
    captured signature is not holding the key that made it. The repeat reads
    back the application; it is not handed a session."""
    client, app = buying
    device, me = joins(client)
    body = body_for(client, me, device)
    assert "session" in client.post("/api/applications", json=body).json()
    again = client.post("/api/applications", json=body).json()
    assert "application" in again and "session" not in again


def test_a_refusal_is_the_answer_the_second_time_too(buying) -> None:
    """Without this, the second ask reports an authentication failure about a
    challenge the buyer spent legitimately, and the reason they were actually
    refused for is lost."""
    client, app = buying
    device, me = joins(client)
    # Cover above what is at risk is a wager, and refused on those grounds.
    body = body_for(client, me, device, limit=90_000.0, risk=50_000.0)
    first = client.post("/api/applications", json=body)
    assert first.status_code == 409, first.text
    # Named, so this cannot start passing on some other refusal later.
    assert "more than it is worth" in first.json()["detail"]
    second = client.post("/api/applications", json=body)
    assert second.status_code == 409
    assert second.json()["detail"] == first.json()["detail"]


def test_a_second_purchase_is_still_a_second_purchase(buying) -> None:
    """The recall is keyed to one challenge. Buying again, properly signed over
    a new one, is a new application and must go through on its own merits."""
    client, app = buying
    device, me = joins(client)
    first = client.post("/api/applications", json=body_for(client, me, device, limit=20_000.0))
    assert first.status_code == 200, first.text
    other, stranger = joins(client)
    second = client.post("/api/applications", json=body_for(
        client, stranger, other, limit=20_000.0, at={**ADDRESS, "flat": "50"}))
    assert second.status_code == 200, second.text
    assert second.json()["application"]["app_id"] != first.json()["application"]["app_id"]


def test_the_repeats_are_counted(buying) -> None:
    client, app = buying
    device, me = joins(client)
    body = body_for(client, me, device)
    client.post("/api/applications", json=body)
    client.post("/api/applications", json=body)
    counts = app.state.counting.since(1)[-1].counts
    assert counts.get("asked again") == 1


def test_a_request_still_being_decided_is_not_reported_as_unauthorised(buying) -> None:
    """The first ask lost on its way out, not on its way back.

    The challenge is spent the moment the signature is checked, and a spent
    challenge is indistinguishable from a forged one to everything except the
    note this leaves. Without it, somebody whose cover was about to exist was
    told they were not authorised.
    """
    client, app = buying
    device, me = joins(client)
    body = body_for(client, me, device)
    # Authorised and being decided, with no answer recorded yet.
    app.state.repeats.begin(body["nonce"], body["signature"])

    answer = client.post("/api/applications", json=body)
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"]["deciding"] is True
    assert "still being decided" in answer.json()["detail"]["message"]
    # And nothing was written for it.
    assert not app.state.applications.applications


def test_the_real_answer_replaces_the_note_that_one_was_coming(buying) -> None:
    client, app = buying
    device, me = joins(client)
    body = body_for(client, me, device)
    first = client.post("/api/applications", json=body)
    assert first.status_code == 200, first.text
    # The marker begin() left inside the route is gone; what is held is the
    # application, so a repeat gets that and not "still deciding".
    second = client.post("/api/applications", json=body)
    assert second.status_code == 200
    assert second.json()["application"]["app_id"] == first.json()["application"]["app_id"]
