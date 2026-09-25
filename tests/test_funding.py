"""Balance coming in: a bank transfer or a wallet deposit, announced by the
person and confirmed by the operator once it has arrived."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol.funding import Destinations, Funding, FundingError
from clause.protocol.wallet import Wallets
from test_api_security import Device, session_for

TOKEN = "operator-token-for-tests"
OP = {"x-operator-token": TOKEN}
RIALO = "HddrYhoVi2UAGXvJuCCZMECGGcdjK6FfwHB9cb9vpCJV"


def test_only_offered_ways_can_be_asked_for_and_nothing_is_credited_until_confirmed() -> None:
    wallets = Wallets(demo_balance=0.0)
    wallets.connect("a", fund=False)
    funding = Funding(wallets, Destinations(iban="TR330006100519786457841326", account_name="Specimen Ltd"))
    assert funding.destinations.offered() == ["bank"]
    with pytest.raises(FundingError):
        funding.request("a", {"method": "solana", "amount": 100})
    with pytest.raises(FundingError):
        funding.request("a", {"method": "bank", "amount": 1})
    req = funding.request("a", {"method": "bank", "amount": 500})
    assert req.reference.startswith("CL-") and req.open
    assert wallets.require("a").balance == 0.0
    done = funding.confirm(req.request_id, 480.0, by="Erkan", note="bank ref 12345")
    assert done.status == "received" and wallets.require("a").balance == pytest.approx(480.0)
    with pytest.raises(FundingError):
        funding.confirm(req.request_id, 480.0, by="Erkan")


def test_a_wallet_deposit_names_the_sender_and_the_reference(monkeypatch) -> None:
    monkeypatch.setenv("CLAUSE_FUNDING_RIALO", RIALO)
    monkeypatch.setenv("CLAUSE_FUNDING_RIALO_CHAIN", "Rialo testnet")
    monkeypatch.setenv("CLAUSE_FUNDING_IBAN", "TR33 0006 1005 1978 6457 8413 26")
    monkeypatch.setenv("CLAUSE_FUNDING_NAME", "Specimen Ltd")
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=False, operator_token=TOKEN))
    with TestClient(app) as client:
        device = Device()
        address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        how = client.get("/api/funding", headers=auth).json()["how"]
        assert how["methods"] == ["bank", "rialo"] and how["rialo"] == RIALO
        # The address alone is not an instruction: the reply names the chain.
        assert how["networks"] == {"rialo": "Rialo testnet"}
        assert how["bank"]["iban"] == "TR330006100519786457841326"
        asked = client.post("/api/funding", headers=auth,
                            json={"method": "rialo", "amount": 250, "sender": RIALO})
        assert asked.status_code == 200, asked.text
        req = asked.json()["request"]
        assert req["status"] == "waiting" and req["sender"] == "Hddr…pCJV"
        # Not yet money.
        assert client.get("/api/wallet", headers=auth).json()["wallet"]["balance"] == 0.0
        # The operator sees it with the full sender, and confirms what arrived.
        seen = client.get("/api/operator/funding", headers=OP).json()
        assert seen["waiting"][0]["sender"] == RIALO and seen["waiting"][0]["account"] == address
        ok = client.post(f"/api/operator/funding/{req['request_id']}", headers=OP,
                         json={"status": "received", "received": 250, "note": "tx 0xabc"})
        assert ok.status_code == 200, ok.text
        assert client.get("/api/wallet", headers=auth).json()["wallet"]["balance"] == pytest.approx(250.0)
        mine = client.get("/api/funding", headers=auth).json()["requests"]
        assert mine[0]["status"] == "received" and mine[0]["received"] == 250
        # A stranger cannot cancel it, and nobody can confirm it twice.
        assert client.post(f"/api/funding/{req['request_id']}/cancel").status_code == 401
        assert client.post(f"/api/operator/funding/{req['request_id']}", headers=OP,
                           json={"status": "received", "received": 250}).status_code == 422


def test_the_watcher_credits_a_solana_deposit_by_its_memo_and_an_evm_one_by_its_sender() -> None:
    from clause.protocol.funding import Watcher, TRANSFER_TOPIC, SOLANA_USDC_MINT
    wallets = Wallets(demo_balance=0.0)
    wallets.connect("a", fund=False); wallets.connect("b", fund=False)
    dest = Destinations(solana=RIALO, evm="0x52908400098527886E0F7030069857D2E4169EE7",
                        solana_chain="Solana devnet", evm_chain="Base Sepolia", testnet=True)
    funding = Funding(wallets, dest)
    sol = funding.request("a", {"method": "solana", "amount": 100})
    evm = funding.request("b", {"method": "evm", "amount": 50, "sender": "0x8617E340B3D01FA5F11F306F4090FD50E238070D"})
    sender_sol = "5oNDL3swdJJF1g9DzJiZ4ynHXgszjAEpUkxVYejchzrY"

    def fake_rpc(url, method, params):
        if method == "getSignaturesForAddress":
            return [{"signature": "sigA"}, {"signature": "sigB", "err": {"x": 1}}]
        if method == "getTransaction":
            return {"transaction": {"message": {"accountKeys": [{"pubkey": sender_sol}],
                    "instructions": [{"program": "spl-memo", "parsed": f"payment {sol.reference}"}]}},
                    "meta": {"preTokenBalances": [{"owner": RIALO, "mint": SOLANA_USDC_MINT, "uiTokenAmount": {"uiAmount": 10.0}}],
                             "postTokenBalances": [{"owner": RIALO, "mint": SOLANA_USDC_MINT, "uiTokenAmount": {"uiAmount": 109.5}}]}}
        if method == "eth_blockNumber":
            return hex(1000)
        if method == "eth_getLogs":
            assert params[0]["topics"][0] == TRANSFER_TOPIC
            return [{"transactionHash": "0xabc", "logIndex": "0x1",
                     "topics": [TRANSFER_TOPIC, "0x" + "8617e340b3d01fa5f11f306f4090fd50e238070d".rjust(64, "0"),
                                "0x" + "52908400098527886e0f7030069857d2e4169ee7".rjust(64, "0")],
                     "data": hex(49_990_000)}]
        raise AssertionError(method)

    w = Watcher(funding, solana_rpc="https://sol.example", evm_rpc="https://evm.example",
                evm_usdc="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", rpc=fake_rpc)
    assert w.active
    assert w.run() == 2
    assert wallets.require("a").balance == pytest.approx(99.5)
    assert wallets.require("b").balance == pytest.approx(49.99)
    assert funding.requests[sol.request_id].tx == "sigA" and funding.requests[evm.request_id].confirmed_by == "ethereum watcher"
    # A second pass sees nothing new and credits nothing twice.
    assert w.run() == 0
    assert wallets.require("a").balance == pytest.approx(99.5)


def test_an_address_without_its_chain_is_not_offered() -> None:
    """The same twenty bytes exist on every EVM chain and on their test
    networks. An address shown without the name of the chain it is watched on
    asks the sender to guess, and a wrong guess does not bounce, so the
    destination is withheld until the deployment says where it lives."""
    from clause.protocol.funding import Destinations

    guessing = Destinations(evm="0x52908400098527886E0F7030069857D2E4169EE7")
    assert guessing.offered() == []
    assert guessing.unnamed() == ["evm"]

    named = Destinations(evm="0x52908400098527886E0F7030069857D2E4169EE7",
                         evm_chain="Base Sepolia", testnet=True)
    assert named.offered() == ["evm"]
    assert named.describe()["networks"] == {"evm": "Base Sepolia"}
    assert named.describe()["testnet"] is True


def test_play_money_has_to_be_declared_rather_than_inferred(monkeypatch) -> None:
    """A deployment that means test money says so. Reading it off the chain's
    name would make "Base Sepolia" safe and a chain we have not heard of
    dangerous, which is the wrong way round."""
    from clause.protocol.funding import Destinations

    monkeypatch.setenv("CLAUSE_FUNDING_EVM", "0x52908400098527886E0F7030069857D2E4169EE7")
    monkeypatch.setenv("CLAUSE_FUNDING_EVM_CHAIN", "Base Sepolia")
    assert Destinations.from_env().testnet is False
    monkeypatch.setenv("CLAUSE_FUNDING_TESTNET", "1")
    assert Destinations.from_env().testnet is True


def test_a_restart_does_not_credit_a_deposit_twice() -> None:
    """The watcher is built before the book is read back off disk.

    So the set of transfers it must not credit again was always empty at the
    moment it was built, and its first scan looked back through hours of chain
    and found transfers whose requests were long closed. Every deploy, and
    every restart of a service set to come back up by itself, credited them
    all a second time.
    """
    from clause.protocol.funding import Watcher

    wallets = Wallets()
    funding = Funding(wallets, Destinations(evm="0xabc", evm_chain="Base"))

    # A watcher made against an empty book, exactly as the app makes it.
    watcher = Watcher(funding, evm_rpc="https://example.invalid", evm_usdc="0xusdc")
    assert watcher.seen == set(), "nothing is known before the book is read"

    # The book arrives, carrying a transfer that was credited long ago and
    # whose request is closed, so nothing is waiting for it any more.
    request = funding.request("addr-1", {"method": "evm", "amount": 100.0})
    funding.requests[request.request_id].tx = "0xdeadbeef"
    funding.requests[request.request_id].status = "received"

    assert watcher.resync() == 1
    assert "0xdeadbeef" in watcher.seen
    # And it only ever adds, so calling it again is not an event.
    assert watcher.resync() == 0
