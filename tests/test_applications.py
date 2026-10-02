"""Cover asked for through the site waits for the issuing company's checks."""

from __future__ import annotations

import pytest
import time
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from test_api_security import Device, buy_body, buy_terms, session_for

TOKEN = "operator-token-for-tests"
OP = {"x-operator-token": TOKEN}


@pytest.fixture
def client():
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN))
    with TestClient(app) as c:
        yield c


def applicant(client):
    device = Device()
    address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
    return device, address


HOME = {"street": "Specimen Sokak", "number": "12", "flat": "4", "postcode": "34290", "city": "İstanbul"}


def apply(client, device, address, instalments=1, **over):
    body = buy_body(address, "", "", **over)
    body["interest"]["address"] = HOME
    body["instalments"] = instalments
    contract = client.post("/api/contract", json={
        "peril": body["peril"], "subject": body["subject"], "limit": body["limit"],
        "term_days": body["term_days"], "interest": body["interest"], "holder": address,
        "instalments": instalments}).json()
    body["contract_hash"] = contract["hash"]
    terms = buy_terms(**{k: over[k] for k in over if k in ("limit",)})
    terms["contract_hash"] = contract["hash"]
    if instalments > 1:
        terms["instalments"] = float(instalments)
    ch = client.post("/api/auth/challenge", json={"address": address, "purpose": "buy",
                                                  "terms": terms}).json()
    body["nonce"], body["signature"] = ch["nonce"], device.sign(ch["message"])
    return client.post("/api/applications", json=body)


def balance(client, device, address):
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    return client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]


def test_an_application_holds_the_premium_and_says_what_will_be_checked(client) -> None:
    device, address = applicant(client)
    before = balance(client, device, address)
    # The same subject the application carries, year and all. Without the year
    # the quote is for a different building -- the oldest one, which is what an
    # unsaid year is priced as -- so the lock would not be a lock on this cover.
    body = {"peril": "earthquake",
            "subject": {"location": "IST-KADIKOY", "radius_km": 50, "built": 2005},
            "limit": 50_000, "term_days": 365}
    reply = client.post("/api/quote", json=body).json()
    # And the figure agreed to is a company's, not the pool's: companies price
    # the same risk differently, so the pool's arithmetic is the floor under a
    # price rather than a price anybody charges.
    offered = client.post("/api/offers?country=TR&professional=false", json=body).json()["offers"]
    assert offered, "nobody offered"
    made = apply(client, device, address, quote_id=reply["lock"]["id"],
                 max_premium=offered[0]["premium"])
    assert made.status_code == 200, made.text
    app = made.json()["application"]
    assert app["status"] == "pending"
    assert set(app["checks"]) == {"sanctions_clear", "identity_basic", "ownership"}
    assert "Specimen Sokak" in client.get(f"/api/applications/{app['app_id']}/contract",
        headers={"authorization": f"Bearer {session_for(client, device, address)}"}).text
    assert app["premium"] == pytest.approx(offered[0]["premium"], abs=0.01)
    # The premium and the issuing company's fee are both held.
    assert app["total"] >= app["premium"]
    assert balance(client, device, address) == pytest.approx(before - app["total"], abs=0.01)
    # Nothing is on the book yet.
    assert not [p for p in client.get("/api/policies").json()["items"] if p.get("metadata", {}).get("application")]


def test_the_operator_approves_after_confirming_each_check(client) -> None:
    device, address = applicant(client)
    app = apply(client, device, address).json()["application"]
    waiting = client.get("/api/review/applications", headers=OP).json()
    assert waiting["waiting"] >= 1
    half = client.post(f"/api/review/applications/{app['app_id']}", headers=OP,
                       json={"decision": "approve", "checked": ["sanctions_clear"]})
    assert half.status_code == 422, "every check has to be confirmed"
    done = client.post(f"/api/review/applications/{app['app_id']}", headers=OP,
                       json={"decision": "approve", "checked": app["checks"], "note": "screened"})
    assert done.status_code == 200, done.text
    policy = done.json()["policy"]
    assert policy["premium"] == pytest.approx(app["premium"], abs=0.01), "the price agreed is the price"
    assert policy["metadata"]["reviewed_by"] == "operator"
    again = client.post(f"/api/review/applications/{app['app_id']}", headers=OP,
                        json={"decision": "approve", "checked": app["checks"]})
    assert again.status_code == 409


def test_a_rejection_returns_everything_and_says_why(client) -> None:
    device, address = applicant(client)
    before = balance(client, device, address)
    app = apply(client, device, address).json()["application"]
    assert client.post(f"/api/review/applications/{app['app_id']}", headers=OP,
                       json={"decision": "reject"}).status_code == 422
    reply = client.post(f"/api/review/applications/{app['app_id']}", headers=OP,
                        json={"decision": "reject", "note": "identity could not be confirmed"})
    assert reply.json()["application"]["status"] == "rejected"
    assert balance(client, device, address) == pytest.approx(before, abs=0.01)


def test_an_applicant_can_withdraw_and_nobody_else_can_decide(client) -> None:
    device, address = applicant(client)
    app = apply(client, device, address).json()["application"]
    stranger_device, stranger = applicant(client)
    stranger_auth = {"authorization": f"Bearer {session_for(client, stranger_device, stranger)}"}
    assert client.post(f"/api/review/applications/{app['app_id']}", headers=stranger_auth,
                       json={"decision": "approve", "checked": app["checks"]}).status_code == 401
    # Signed, because withdrawing releases the escrow; a session is for
    # reading. A stranger who signs correctly for their own address is still
    # not the applicant.
    def withdraw(who, signer):
        challenge = client.post("/api/auth/challenge", json={
            "address": who, "purpose": "withdraw-application",
            "terms": {"app_id": app["app_id"]}}).json()
        return client.post(f"/api/applications/{app['app_id']}/withdraw", json={
            "account": who, "nonce": challenge["nonce"],
            "signature": signer.sign(challenge["message"])})

    assert withdraw(stranger, stranger_device).status_code == 404
    # And a session, which is what this used to take, is not enough.
    assert client.post(f"/api/applications/{app['app_id']}/withdraw",
                       headers=stranger_auth, json={}).status_code == 422
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    mine = client.get("/api/applications", headers=auth).json()["applications"]
    assert mine[0]["app_id"] == app["app_id"]
    assert withdraw(address, device).json()["application"]["status"] == "withdrawn"


def test_an_unread_or_changed_contract_is_refused(client) -> None:
    device, address = applicant(client)
    body = buy_body(address, "", "")
    body["interest"]["address"] = HOME
    terms = buy_terms(); terms["contract_hash"] = "0" * 64
    ch = client.post("/api/auth/challenge", json={"address": address, "purpose": "buy", "terms": terms}).json()
    body.update(nonce=ch["nonce"], signature=device.sign(ch["message"]), contract_hash="0" * 64)
    reply = client.post("/api/applications", json=body)
    assert reply.status_code == 409 and "contract" in reply.text
    # And a home without an address cannot be applied for at all.
    body = buy_body(address, "", "")
    ch = client.post("/api/auth/challenge", json={"address": address, "purpose": "buy", "terms": buy_terms()}).json()
    body.update(nonce=ch["nonce"], signature=device.sign(ch["message"]))
    assert client.post("/api/applications", json=body).status_code == 422


def test_instalments_where_offered_hold_only_the_first_and_collect_the_rest(client) -> None:
    from clause.protocol.instalments import offers_for
    assert [p["count"] for p in offers_for("TR", 365)] == [1, 3, 6, 12]
    assert [p["count"] for p in offers_for("KE", 365)] == [1]
    assert [p["count"] for p in offers_for("TR", 2)] == [1], "no instalments on short cover"
    device, address = applicant(client)
    before = balance(client, device, address)
    made = apply(client, device, address, instalments=3)
    assert made.status_code == 200, made.text
    app = made.json()["application"]
    assert app["plan"]["count"] == 3 and app["first_payment"] == pytest.approx(app["plan"]["amount"], abs=0.01)
    assert balance(client, device, address) == pytest.approx(before - app["first_payment"], abs=0.01)
    done = client.post(f"/api/review/applications/{app['app_id']}", headers=OP,
                       json={"decision": "approve", "checked": app["checks"]})
    assert done.status_code == 200, done.text
    policy = done.json()["policy"]
    assert policy["metadata"]["premium_owed"] > 0
    plan = policy["metadata"]["plan"]
    assert plan["count"] == 3 and sum(plan["amounts"]) == pytest.approx(plan["total"], abs=0.01)
    # Approval takes exactly the first instalment (premium part, fee part,
    # surcharge part), which is what was held: the balance does not move again.
    assert balance(client, device, address) == pytest.approx(before - plan["amounts"][0], abs=0.02)
    assert policy["metadata"]["fee_paid"] == pytest.approx(plan["fee_parts"][0], abs=0.01)
    # The second instalment falls due: one collection takes all of its parts.
    from clause.api import app as app_module
    proto = client.app
    plan_live = None
    for p in proto.state.pool.policies.values():
        if p.policy_id == policy["policy_id"]:
            plan_live = p.metadata["plan"]
    plan_live["due"][1] = time.time() - 1
    taken = proto.state.collect_due()
    assert taken == 1
    assert balance(client, device, address) == pytest.approx(before - plan["amounts"][0] - plan["amounts"][1], abs=0.03)


def test_on_a_demonstration_anyone_may_take_a_stand_in_companys_desk() -> None:
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, specimens=True, operator_token=TOKEN))
    with TestClient(app) as client:
        device, address = applicant(client)
        placed = apply(client, device, address).json()["application"]
        assert placed["carrier_id"]
        # A second account plays the insurer.
        insurer_device, insurer = applicant(client)
        auth = {"authorization": f"Bearer {session_for(client, insurer_device, insurer)}"}
        company = client.get("/api/company", headers=auth).json()
        assert company["companies"] == [] and company["demo"]["on"]
        desks = {d["carrier_id"]: d for d in company["demo"]["specimens"]}
        assert desks[placed["carrier_id"]]["waiting"] == 1
        # Nothing to decide before taking the desk; the application after it.
        assert client.get("/api/review/applications", headers=auth).json()["waiting"] == 0
        taken = client.post("/api/company/specimen", headers=auth,
                            json={"carrier_id": placed["carrier_id"]}).json()
        assert taken["companies"][0]["carrier_id"] == placed["carrier_id"]
        assert client.get("/api/review/applications", headers=auth).json()["waiting"] == 1
        decided = client.post(f"/api/review/applications/{placed['app_id']}", headers=auth,
                              json={"decision": "approve", "checked": placed["checks"]}).json()
        assert decided["application"]["status"] == "approved"
        assert decided["application"]["decided_by"].startswith("Specimen")
        # Leaving the desk gives it back.
        client.post("/api/company/specimen", headers=auth,
                    json={"carrier_id": placed["carrier_id"], "release": True})
        assert client.get("/api/company", headers=auth).json()["companies"] == []


def test_without_stand_ins_no_desk_can_be_taken(client) -> None:
    device, address = applicant(client)
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    assert client.get("/api/company", headers=auth).json()["demo"]["on"] is False
    assert client.post("/api/company/specimen", headers=auth,
                       json={"carrier_id": "specimen-tr-one"}).status_code == 404
