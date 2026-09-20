"""The platform's fee: one per cent of the premium, out of the company's
fronting fee, back with the fee when the fee comes back, and a statement
for every company every month.

The buyer's price is never touched: it is the pool's premium plus the
company's fee, exactly as before. What changes is where the fee goes.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol.fees import PLATFORM_ACCOUNT, Fees, platform_share
from clause.store import Store
from test_api_security import session_for
from test_commerce import RIDER_KEY, TOKEN, register, rider_buy, sign_mandate, signed_post

OP = {"x-operator-token": TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CLAUSE_RIDER_PURCHASE_KEY_SHA256", hashlib.sha256(RIDER_KEY.encode()).hexdigest())
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, specimens=True))
    with TestClient(app) as c:
        yield c


def platform_balance(client) -> float:
    account = client.app.state.wallets.get(PLATFORM_ACCOUNT)
    return round(account.balance, 2) if account else 0.0


def test_the_share_is_one_percent_of_the_premium_and_never_more_than_the_fee() -> None:
    assert platform_share(1000.0, 60.0) == 10.0          # 6% fee: the platform takes 1 of the 6
    assert platform_share(1000.0, 5.0) == 5.0            # a 0.5% fee: all of it, no more
    assert platform_share(1000.0, 0.0) == 0.0            # no fee, nothing to take from
    assert platform_share(0.0, 60.0) == 0.0


def test_the_fee_is_taken_from_the_company_not_the_buyer_and_the_statement_says_so(client) -> None:
    device, address = register(client)
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    before = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]
    token = sign_mandate(client, device, address).json()["token"]
    policy = rider_buy(client, token).json()["policy"]
    meta = policy["metadata"]
    fee, share = meta["fronting_fee"], meta["platform_fee"]
    assert share == platform_share(policy["premium"], fee) and 0 < share <= fee
    assert meta["platform_fee_paid"] == share
    # The buyer paid premium plus the company's fee: the platform's share is inside the fee.
    after = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]
    assert after == pytest.approx(before - policy["premium"] - fee, abs=0.02)
    assert platform_balance(client) == pytest.approx(share, abs=0.01)
    # The operator sees the month's statements and the platform's totals.
    op = {"authorization": f"Bearer {client.post('/api/operator/session', json={'reviewer': 'Ayşe'}, headers=OP).json()['token']}"}
    reply = client.get("/api/operator/statements", headers=op)
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["platform"]["rate"] == 0.01 and body["platform"]["net"] == pytest.approx(share, abs=0.01)
    st = next(s for s in body["statements"] if s["carrier_id"] == meta["carrier"])
    assert st["policies"] == 1 and st["premiums_written"] == pytest.approx(policy["premium"], abs=0.01)
    assert st["fronting_fees"] == pytest.approx(fee, abs=0.01) and st["platform_fees"] == pytest.approx(share, abs=0.01)
    assert st["net_to_company"] == pytest.approx(fee - share, abs=0.01)
    assert {l["kind"] for l in st["lines"]} == {"fronting_fee", "platform_fee"}
    csv_reply = client.get("/api/operator/statements", params={"format": "csv", "month": body["month"]}, headers=op)
    assert csv_reply.status_code == 200 and "platform_fee" in csv_reply.text and "net_to_company" in csv_reply.text

    # The company reads its own statement from its desk.
    desk_device, desk = register(client)
    desk_auth = {"authorization": f"Bearer {session_for(client, desk_device, desk)}"}
    assert client.post("/api/company/specimen", json={"carrier_id": meta["carrier"]}, headers=desk_auth).status_code == 200
    mine = client.get("/api/company/statements", params={"carrier_id": meta["carrier"]}, headers=desk_auth)
    assert mine.status_code == 200, mine.text
    assert mine.json()["statement"]["net_to_company"] == pytest.approx(fee - share, abs=0.01)
    assert mine.json()["months"] == [body["month"]]
    assert client.get("/api/company/statements", params={"carrier_id": meta["carrier"]}, headers=auth).status_code == 404
    # And the desk's book shows what the platform kept.
    book = client.get("/api/company", headers=desk_auth).json()["companies"][0]["book"]
    assert book["platform_fees"] == pytest.approx(share, abs=0.01) and book["platform_rate"] == 0.01


def test_a_refund_gives_the_platforms_share_back_as_well(client) -> None:
    device, address = register(client)
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    before = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]
    token = sign_mandate(client, device, address).json()["token"]
    policy = rider_buy(client, token).json()["policy"]
    share = policy["metadata"]["platform_fee"]
    assert platform_balance(client) == pytest.approx(share, abs=0.01)
    reply = signed_post(client, device, address, "cancel", {"policy_id": policy["policy_id"]},
                        f"/api/policies/{policy['policy_id']}/cancel", {"account": address})
    assert reply.status_code == 200, reply.text
    meta = reply.json()["policy"]["metadata"]
    assert meta["platform_fee_returned"] == pytest.approx(share, abs=0.01)
    assert meta["fee_returned"] == pytest.approx(meta["fronting_fee"], abs=0.01)
    assert platform_balance(client) == pytest.approx(0.0, abs=0.01)
    after = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]
    assert after == pytest.approx(before, abs=0.02)
    op = {"authorization": f"Bearer {client.post('/api/operator/session', json={'reviewer': 'Ayşe'}, headers=OP).json()['token']}"}
    body = client.get("/api/operator/statements", headers=op).json()
    st = next(s for s in body["statements"] if s["carrier_id"] == meta["carrier"])
    assert st["platform_fees_returned"] == pytest.approx(share, abs=0.01) and st["net_to_company"] == pytest.approx(0.0, abs=0.01)
    assert body["platform"]["net"] == pytest.approx(0.0, abs=0.01)


def test_fee_entries_survive_a_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUSE_RIDER_PURCHASE_KEY_SHA256", hashlib.sha256(RIDER_KEY.encode()).hexdigest())
    monkeypatch.setenv("CLAUSE_STATE_DIR", str(tmp_path))
    settings = Settings(faucet=True, operator_token=TOKEN, specimens=True)
    with TestClient(create_app(trials=400, seed=11, run_chain=False, seed_book=True, settings=settings)) as c:
        device, address = register(c)
        policy = rider_buy(c, sign_mandate(c, device, address).json()["token"]).json()["policy"]
        share = policy["metadata"]["platform_fee"]
    store = Store(tmp_path / "clause.sqlite")
    assert len(store.docs("fee")) == 2
    store.close()
    with TestClient(create_app(trials=400, seed=11, run_chain=False, seed_book=True, settings=settings)) as c:
        op = {"authorization": f"Bearer {c.post('/api/operator/session', json={'reviewer': 'Ayşe'}, headers=OP).json()['token']}"}
        body = c.get("/api/operator/statements", headers=op).json()
        assert body["platform"]["net"] == pytest.approx(share, abs=0.01)
        assert platform_balance(c) == pytest.approx(share, abs=0.01)


def test_the_statement_is_the_entries_not_a_recomputation() -> None:
    fees = Fees()
    fees.record(carrier_id="c1", policy_id="P1", holder="h", kind="fronting_fee", amount=60.0, premium=1000.0, now=1_700_000_000)
    fees.record(carrier_id="c1", policy_id="P1", holder="h", kind="platform_fee", amount=10.0, premium=1000.0, now=1_700_000_000)
    fees.record(carrier_id="c1", policy_id="P2", holder="h", kind="fronting_fee", amount=30.0, premium=500.0, now=1_700_000_100)
    fees.record(carrier_id="c1", policy_id="P2", holder="h", kind="platform_fee", amount=5.0, premium=500.0, now=1_700_000_100)
    fees.record(carrier_id="c1", policy_id="P2", holder="h", kind="fronting_fee_returned", amount=25.0, premium=500.0, now=1_700_000_200)
    fees.record(carrier_id="c1", policy_id="P2", holder="h", kind="platform_fee_returned", amount=5.0, premium=500.0, now=1_700_000_200)
    assert fees.record(carrier_id="c1", policy_id="P3", holder="h", kind="platform_fee", amount=0.0, premium=1.0) is None
    with pytest.raises(ValueError):
        fees.record(carrier_id="c1", policy_id="P3", holder="h", kind="tip", amount=1.0, premium=1.0)
    month = fees.months("c1")[0]
    st = fees.statement("c1", month, names={"c1": "Carrier One"})
    assert st["carrier"] == "Carrier One" and st["policies"] == 2 and st["premiums_written"] == 1500.0
    assert st["fronting_fees"] == 90.0 and st["fronting_fees_returned"] == 25.0
    assert st["platform_fees"] == 15.0 and st["platform_fees_returned"] == 5.0
    assert st["net_to_company"] == pytest.approx(90 - 25 - (15 - 5))
    totals = fees.platform_totals()
    assert totals["net"] == 10.0 and totals["by_month"][month]["policies"] == 2
    text = Fees.csv(st)
    assert text.splitlines()[0].startswith("entry_id,at,month,carrier") and "net_to_company,55.0" in text
