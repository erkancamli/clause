"""Before a payout leaves, the compliance rules run again on the registry
as it stands: a company suspended while the policy ran does not get paid
through, the premium comes back instead."""

from __future__ import annotations

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol import PolicyStatus
from test_api_security import Device, buy_body, buy_terms, session_for

TOKEN = "operator-token-for-tests"


def test_a_company_suspended_mid_term_stops_the_payout_and_returns_the_premium() -> None:
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN))
    with TestClient(app) as client:
        device = Device()
        address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
        challenge = client.post("/api/auth/challenge", json={
            "address": address, "purpose": "buy", "terms": buy_terms()}).json()
        bought = client.post("/api/policies", json=buy_body(
            address, challenge["nonce"], device.sign(challenge["message"]), client=client))
        assert bought.status_code == 200, bought.text
        policy_id = bought.json()["policy"]["policy_id"]
        carrier_id = bought.json()["policy"]["metadata"]["carrier"]
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        paid_premium = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]

        # The issuing company loses its licence while the policy runs.
        assert client.post(f"/api/carriers/{carrier_id}/suspend", headers={"x-operator-token": TOKEN},
                           json={"note": "licence withdrawn by the regulator"}).status_code == 200

        chain, pool = app.state.chain, app.state.pool
        policy = pool.policies[policy_id]
        chain.attest(policy.data_reference, "max_magnitude", 7.4)
        for _ in range(chain.confirm_blocks(policy) + 3):
            chain.produce_block()
        policy = pool.policies[policy_id]
        assert policy.status is PolicyStatus.EXPIRED, policy.status
        assert "compliance" in policy.settlement_note or "not paid" in policy.settlement_note
        # The premium came back; the payout did not go out.
        after = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]
        assert after > paid_premium
        assert after < paid_premium + policy.limit
