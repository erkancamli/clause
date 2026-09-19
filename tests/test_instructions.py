"""Standing instructions: cover renewed or bought later on terms signed now."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol.instructions import Instructions, InstructionError, RENEW_LEAD, from_condition
from test_api_security import Device, session_for, statements
from test_applications import HOME, OP, TOKEN, applicant, apply, balance


@pytest.fixture
def client():
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN))
    with TestClient(app) as c:
        yield c


def give(client, device, address, body):
    terms = {"kind": body["kind"], "max_premium": round(float(body["max_premium"]), 2), "days": float(body.get("days", 365))}
    if body["kind"] == "renew":
        terms["policy_id"] = body["policy_id"]
    else:
        terms.update({"peril": body["peril"], "subject": body["subject"], "limit": float(body["limit"]),
                      "term_days": float(body["term_days"]), "when": body.get("when", "date")})
        if body.get("when") == "age":
            terms["years"] = float(body["years"])
        else:
            terms["at"] = float(body["at"])
    ch = client.post("/api/auth/challenge", json={"address": address, "purpose": "instruct", "terms": terms}).json()
    body = {**body, "account": address, "nonce": ch["nonce"], "signature": device.sign(ch["message"])}
    return client.post("/api/instructions", json=body)


def approved_home(client, device, address):
    app = apply(client, device, address).json()["application"]
    done = client.post(f"/api/review/applications/{app['app_id']}", headers=OP,
                       json={"decision": "approve", "checked": app["checks"], "note": "screened"})
    assert done.status_code == 200, done.text
    return done.json()["policy"]


def run(client):
    return asyncio.run(client.app.state.run_instructions())


def test_a_renewal_follows_the_policy_and_applies_a_day_before_it_ends(client) -> None:
    device, address = applicant(client)
    policy = approved_home(client, device, address)
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    reply = give(client, device, address, {"kind": "renew", "policy_id": policy["policy_id"],
                                           "max_premium": policy["premium"] * 1.5, "days": 400})
    assert reply.status_code == 200, reply.text
    item = reply.json()["instruction"]
    assert item["status"] == "live" and item["peril"] == "earthquake" and item["policy_id"] == policy["policy_id"]
    # Not yet: the policy has a year to run.
    assert run(client) == 0
    # A second renewal on the same policy is refused.
    assert give(client, device, address, {"kind": "renew", "policy_id": policy["policy_id"],
                                          "max_premium": 100}).status_code == 422
    # Bring the policy to a day from its end: the renewal applies.
    live = client.app.state.pool.policies[policy["policy_id"]]
    live.ends_at = time.time() + RENEW_LEAD / 2
    before = balance(client, device, address)
    assert run(client) == 1
    mine = client.get("/api/instructions", headers=auth).json()["instructions"]
    assert mine[0]["status"] == "waiting" and mine[0]["application_id"]
    assert mine[0]["attempts"][-1]["outcome"] == "applied"
    assert balance(client, device, address) < before, "the premium is held while the company decides"
    app_id = mine[0]["application_id"]
    waiting = client.get("/api/review/applications", headers=OP).json()
    row = next(a for a in waiting["applications"] if a["app_id"] == app_id)
    assert row["instruction"] == item["instruction_id"]
    done = client.post(f"/api/review/applications/{app_id}", headers=OP,
                       json={"decision": "approve", "checked": row["checks"], "note": "renewal"})
    assert done.status_code == 200, done.text
    run(client)
    mine = client.get("/api/instructions", headers=auth).json()["instructions"]
    assert mine[0]["status"] == "live", "a renewal keeps following the new policy"
    assert mine[0]["policy_id"] == done.json()["policy"]["policy_id"]
    assert mine[0]["bought"] == [done.json()["policy"]["policy_id"]]


def test_a_renewal_over_the_cap_waits_and_says_so(client) -> None:
    device, address = applicant(client)
    policy = approved_home(client, device, address)
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    give(client, device, address, {"kind": "renew", "policy_id": policy["policy_id"], "max_premium": 1.0})
    client.app.state.pool.policies[policy["policy_id"]].ends_at = time.time() + 100
    assert run(client) == 1
    mine = client.get("/api/instructions", headers=auth).json()["instructions"]
    assert mine[0]["status"] == "live" and mine[0]["attempts"][-1]["outcome"] == "waiting"
    assert "over the cap" in mine[0]["note"]
    assert mine[0]["next_at"] > time.time() + 3600, "tried again a day later, not every half minute"
    # Cancelling ends it.
    gone = client.post(f"/api/instructions/{mine[0]['instruction_id']}/cancel", headers=auth)
    assert gone.json()["instruction"]["status"] == "cancelled"


def test_a_buy_instruction_waits_for_its_date_then_buys(client) -> None:
    device, address = applicant(client)
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    body = {"kind": "buy", "peril": "drought", "subject": {"station": "TR-KONYA", "distance_km": 8.0, "hectares": 10.0},
            "limit": 5_000, "term_days": 180, "max_premium": 5_000, "days": 30,
            "interest": {"what": "a wheat field", "country": "TR", "inside_trigger_area": True,
                         "value_at_risk": 8_000, "size": {"kind": "field", "area_ha": 10, "crop": "wheat"}},
            "when": "date", "at": time.time() + 3600}
    refused = give(client, device, address, body)
    assert refused.status_code == 451, "a purchase would ask for a statement; so does the instruction"
    body["attestations"] = statements(client, address, "sanctions_clear", "identity_basic")
    reply = give(client, device, address, body)
    assert reply.status_code == 200, reply.text
    assert reply.json()["instruction"]["claims"] == ["identity_basic", "sanctions_clear"]
    assert run(client) == 0, "not before its date"
    item = client.app.state.instructions.instructions[reply.json()["instruction"]["instruction_id"]]
    item.from_at = item.next_at = time.time() - 1
    assert run(client) == 1
    mine = client.get("/api/instructions", headers=auth).json()["instructions"]
    assert mine[0]["status"] == "done" and len(mine[0]["bought"]) == 1, mine[0]
    bought = client.app.state.pool.policies[mine[0]["bought"][0]]
    assert bought.holder == address and bought.metadata["instruction"] == mine[0]["instruction_id"]


def test_an_age_condition_counts_from_the_year_built() -> None:
    now = time.time()
    at, words = from_condition({"when": "age", "years": 10}, {"kind": "home", "built": 2020}, now=now)
    assert words == {"when": "age", "what": "home", "born": 2020, "years": 10, "year": 2030} and at > now
    with pytest.raises(InstructionError):
        from_condition({"when": "age", "years": 10}, {"kind": "home"}, now=now)
    with pytest.raises(InstructionError, match="years away"):
        from_condition({"when": "age", "years": 40}, {"kind": "vehicle", "model_year": 2020}, now=now)


def test_a_renewal_is_dropped_when_its_policy_is_cancelled() -> None:
    from types import SimpleNamespace
    book = Instructions()
    item = book.create("acct", kind="renew", peril="earthquake", subject={}, limit=1, term_days=365,
                       declared={}, size=None, value_at_risk=1, settlement="stablecoin", carrier_id=None,
                       address=None, max_premium=10, instalments=1, days=30, policy_id="P1")
    policies = {"P1": SimpleNamespace(status="cancelled", ends_at=time.time() + 5)}
    assert book.due(policies) == [] and item.status == "cancelled"
