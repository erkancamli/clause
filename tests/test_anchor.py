"""The public chain beside the protocol's own: signing that matches the
Ethereum test vectors, a Merkle tree the contract can verify, intents
recorded as things happen, sent when a key is configured, and proofs a
person can check."""

from __future__ import annotations

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from clause.anchor import Anchor, AnchorConfig, merkle
from clause.anchor.rpc import Rpc
from clause.anchor.service import CALLS, artifacts
from clause.anchor.signing import (abi_encode, address_of_key, contract_address, encode_call, legacy_signing_hash,
                                   private_key_of, rlp, rlp_decode, selector, sender_of_1559, sign_1559, sign_legacy,
                                   to_address)
from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol.evm import keccak256
from test_api_security import session_for
from test_commerce import TOKEN, register, signed_post
from test_desk import buy_quake

KEY = "0x4646464646464646464646464646464646464646464646464646464646464646"
SIGNER = "0x9d8A62f656a8d1615C1294fd71e9CFb3E4855A4F"
POLICY = "0x1111111111111111111111111111111111111111"
BOOK = "0x2222222222222222222222222222222222222222"
OP = {"x-operator-token": TOKEN}


# -- the arithmetic ------------------------------------------------------------


def test_keccak_and_the_eip155_example_transaction() -> None:
    assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    key = private_key_of(KEY)
    assert address_of_key(key) == SIGNER
    to = to_address("0x3535353535353535353535353535353535353535")
    args = dict(nonce=9, gas_price=20_000_000_000, gas=21_000, to=to, value=10**18, data=b"", chain_id=1)
    assert legacy_signing_hash(**args).hex() == "daf5a779ae972f972197303d7b574746c7ef83eadac0f2791ad23db92e4c8e53"
    assert sign_legacy(key, **args).hex() == (
        "f86c098504a817c800825208943535353535353535353535353535353535353535880de0b6b3a764000080"
        "25a028ef61340bd939bc2195fe537567866003e1a15d3c71ff63e1590620aa636276"
        "a067cbe9d8997f761aecb703304b3800ccf555c9f3dc64214b297fb1966a3b6d83")
    raw = sign_1559(key, chain_id=84532, nonce=3, max_priority_fee=1_000, max_fee=2_000, gas=50_000,
                    to=to, value=0, data=b"\x01\x02")
    assert raw[0] == 2 and sender_of_1559(raw) == SIGNER
    fields = rlp_decode(raw[1:])
    assert int.from_bytes(fields[0], "big") == 84532 and int.from_bytes(fields[1], "big") == 3
    assert rlp_decode(rlp([b"cat", [b"dog", 1]])) == [b"cat", [b"dog", b"\x01"]]
    assert contract_address(SIGNER, 0) == "0x72665d3e94Cb4f374b7728F1ab21A3115C4D50Eb"


def test_abi_encoding_and_the_calls_the_contracts_expose() -> None:
    assert selector("transfer(address,uint256)").hex() == "a9059cbb"
    data = encode_call("mint(address,string,bytes32,bytes32)", [POLICY, "CLS-1", "0x" + "11" * 32, "0x" + "22" * 32])
    assert data[:4] == selector(CALLS["mint"])
    body = data[4:]
    assert body[12:32] == to_address(POLICY)
    assert int.from_bytes(body[32:64], "big") == 128          # the string's offset: after four heads
    assert int.from_bytes(body[128:160], "big") == 5 and body[160:165] == b"CLS-1"
    assert abi_encode(["bytes32[]"], [["0x" + "aa" * 32]]) == (b"\x00" * 31 + b"\x20") + (b"\x00" * 31 + b"\x01") + b"\xaa" * 32
    # Every call the service sends exists, with that signature, in the compiled ABI.
    built = artifacts()
    signatures = set()
    for name in ("ClausePolicy", "ClauseBook"):
        for entry in built[name]["abi"]:
            if entry["type"] == "function":
                signatures.add(entry["name"] + "(" + ",".join(i["type"] for i in entry["inputs"]) + ")")
        assert built[name]["bin"].startswith("60")
    for call in CALLS.values():
        assert call in signatures, call
    assert "verify(bytes32,bytes32[],bytes32)" in signatures and "locked(uint256)" in signatures


def test_the_merkle_tree_is_sorted_pairs_and_the_proof_checks() -> None:
    leaves = ["0x" + ("%02x" % i) * 32 for i in range(7)]
    root = merkle.root_of(leaves)
    assert root == merkle.root_of(reversed(leaves))                 # order of arrival does not matter
    for leaf in leaves:
        proof = merkle.proof_of(leaves, leaf)
        assert proof is not None and merkle.verify(root, proof, leaf)
        assert not merkle.verify(root, proof, leaves[(leaves.index(leaf) + 1) % 7])
    assert merkle.proof_of(leaves, "0x" + "ff" * 32) is None
    one = merkle.root_of(leaves[:1])
    assert one == leaves[0] and merkle.verify(one, [], leaves[0])   # a single leaf is its own root
    assert merkle.root_of([]) == "0x" + "00" * 32
    # A pair is hashed in sorted order, as the contract does it.
    a, b = bytes.fromhex(leaves[2][2:]), bytes.fromhex(leaves[1][2:])
    assert merkle.root_of(leaves[1:3]) == "0x" + keccak256(b + a).hex()


# -- a node that answers like one -------------------------------------------------


class FakeNode:
    """Enough of an Ethereum node to accept transactions and confirm them."""

    def __init__(self, chain_id: int = 84532) -> None:
        self.chain_id = chain_id
        self.sent: list[bytes] = []
        self.nonce = 7
        self.mined: dict[str, int] = {}
        self.revert_selectors: set[bytes] = set()
        self.block = 1000

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method, params = body["method"], body.get("params", [])
        result: object
        if method == "eth_chainId":
            result = hex(self.chain_id)
        elif method == "eth_getTransactionCount":
            result = hex(self.nonce)
        elif method == "eth_getBalance":
            result = hex(10**17)
        elif method == "eth_getBlockByNumber":
            result = {"baseFeePerGas": hex(1_000_000), "number": hex(self.block)}
        elif method == "eth_maxPriorityFeePerGas":
            result = hex(1_000)
        elif method == "eth_estimateGas":
            data = bytes.fromhex(params[0]["data"][2:])
            if data[:4] in self.revert_selectors:
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                                                 "error": {"code": 3, "message": "execution reverted: NotIssuer()"}})
            result = hex(100_000)
        elif method == "eth_sendRawTransaction":
            raw = bytes.fromhex(params[0][2:])
            self.sent.append(raw)
            self.nonce += 1
            h = "0x" + keccak256(raw).hex()
            self.mined[h] = self.block
            self.block += 1
            result = h
        elif method == "eth_getTransactionReceipt":
            h = params[0]
            result = {"status": "0x1", "blockNumber": hex(self.mined[h])} if h in self.mined else None
        else:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                                             "error": {"code": -32601, "message": f"no {method}"}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    def calls(self) -> list[tuple[str, bytes, int]]:
        """(to, selector, nonce) of each transaction, in order."""
        out = []
        for raw in self.sent:
            fields = rlp_decode(raw[1:])
            out.append(("0x" + fields[5].hex(), fields[7][:4], int.from_bytes(fields[1], "big") if fields[1] else 0))
        return out


def live_config() -> AnchorConfig:
    return AnchorConfig(chain_id=84532, rpc_url="http://node.test", private_key=KEY,
                        policy_contract=POLICY, book_contract=BOOK, every=3600)


@pytest.fixture
def node() -> FakeNode:
    return FakeNode()


def app_for(tmp_path, node: FakeNode | None, *, live: bool):
    config = live_config() if live else AnchorConfig(every=3600)
    rpc = Rpc(config.rpc_url, transport=node.transport()) if (live and node is not None) else None
    return create_app(trials=300, seed=11, run_chain=False, seed_book=True,
                      settings=Settings(faucet=True, operator_token=TOKEN, specimens=True),
                      store_path=tmp_path / "book.sqlite", anchor_config=config, anchor_rpc=rpc)


# -- recorded without a key, sent with one ------------------------------------------


def test_without_a_key_everything_is_recorded_and_the_proof_still_checks(tmp_path) -> None:
    with TestClient(app_for(tmp_path, None, live=False)) as client:
        status = client.get("/api/anchor").json()
        assert status["mode"] == "record" and status["signer"] is None and status["chain"]["id"] == 84532
        assert client.get("/api/health").json()["anchor"]["mode"] == "record"
        device, address = register(client)
        policy = buy_quake(client, device, address, 20_000)
        pid = policy["policy_id"]
        mine = client.get(f"/api/policies/{pid}/anchor").json()
        assert [i["kind"] for i in mine["intents"]] == ["mint"]
        assert mine["intents"][0]["status"] == "pending" and mine["intents"][0]["payload"]["custodial"]
        # No root yet: the first cycle runs on the worker, which is not running here.
        assert mine["proof"]["root"] is None
        client.post("/api/operator/anchor/run", headers=OP)
        # The seeded book is in the root but gets no transactions of its own.
        assert client.get("/api/anchor").json()["by_kind"]["mint"] == 1
        assert client.get("/api/anchor").json()["last_root"]["payload"]["count"] >= 12
        proof = client.get(f"/api/policies/{pid}/anchor").json()["proof"]
        assert proof["verified"] and proof["current"] and proof["count"] >= 1
        assert merkle.verify(proof["root"], proof["proof"], proof["leaf"])
        assert merkle.leaf_of(proof["fields"]) == proof["leaf"]
        assert proof["fields"]["policy_id"] == pid and proof["fields"]["status_code"] == 1
        # Cancel: the burn is recorded, the leaf changes, the last root is stale for it.
        reply = signed_post(client, device, address, "cancel", {"policy_id": pid},
                            f"/api/policies/{pid}/cancel", {"account": address})
        assert reply.status_code == 200, reply.text
        after = client.get(f"/api/policies/{pid}/anchor").json()
        assert [i["kind"] for i in after["intents"]] == ["mint", "burn"]
        assert not after["proof"]["current"] and after["proof"]["fields"]["status"] == "cancelled"
        client.post("/api/operator/anchor/run", headers=OP)
        assert client.get(f"/api/policies/{pid}/anchor").json()["proof"]["current"]
        assert client.get("/api/anchor").json()["by_kind"]["root"] >= 2


def test_with_a_key_intents_are_sent_in_order_and_confirmed(tmp_path, node) -> None:
    with TestClient(app_for(tmp_path, node, live=True)) as client:
        status = client.get("/api/anchor").json()
        assert status["mode"] == "live" and status["signer"] == SIGNER
        assert status["contracts"]["policy_url"] == f"https://sepolia.basescan.org/address/{POLICY}"
        device, address = register(client)
        policy = buy_quake(client, device, address, 20_000)
        pid = policy["policy_id"]
        report = client.post("/api/operator/anchor/run", headers=OP).json()["report"]
        assert report["sent"] >= 2                      # the mint and the root at least
        calls = node.calls()
        assert all(sender_of_1559(raw) == SIGNER for raw in node.sent)
        kinds = [(to, sel) for to, sel, _ in calls]
        assert (POLICY, selector(CALLS["mint"])) in kinds and (BOOK, selector(CALLS["root"])) in kinds
        assert [n for _, _, n in calls] == list(range(7, 7 + len(calls)))   # nonces rise, none skipped
        # The next cycle reads the receipts.
        client.post("/api/operator/anchor/run", headers=OP)
        mine = client.get(f"/api/policies/{pid}/anchor").json()
        mint = mine["intents"][0]
        assert mint["status"] == "confirmed" and mint["block"] and mint["tx_url"].startswith("https://sepolia.basescan.org/tx/0x")
        assert mine["token_url"].startswith(f"https://sepolia.basescan.org/nft/{POLICY}/")
        assert mine["proof"]["anchor"]["status"] == "confirmed"
        assert client.get("/api/anchor").json()["balance_eth"] == pytest.approx(0.1)
        # A burn goes out after the mint, never before it.
        signed_post(client, device, address, "cancel", {"policy_id": pid}, f"/api/policies/{pid}/cancel", {"account": address})
        client.post("/api/operator/anchor/run", headers=OP)
        order = [sel for _, sel, _ in node.calls()]
        assert order.index(selector(CALLS["burn"])) > order.index(selector(CALLS["mint"]))


def test_a_call_that_would_revert_is_not_paid_for(tmp_path, node) -> None:
    node.revert_selectors.add(selector(CALLS["mint"]))
    with TestClient(app_for(tmp_path, node, live=True)) as client:
        device, address = register(client)
        pid = buy_quake(client, device, address, 20_000)["policy_id"]
        client.post("/api/operator/anchor/run", headers=OP)
        mint = client.get(f"/api/policies/{pid}/anchor").json()["intents"][0]
        assert mint["status"] == "failed" and "NotIssuer" in mint["error"]
        assert selector(CALLS["mint"]) not in [sel for _, sel, _ in node.calls()]
        status = client.get("/api/anchor").json()
        assert status["counts"]["failed"] == status["by_kind"]["mint"] >= 1   # every mint, and only the mints
        assert (BOOK, selector(CALLS["root"])) in [(to, sel) for to, sel, _ in node.calls()]


def test_intents_survive_a_restart_and_a_node_that_is_down(tmp_path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    config = live_config()
    rpc = Rpc(config.rpc_url, transport=httpx.MockTransport(down))
    app = create_app(trials=300, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, specimens=True),
                     store_path=tmp_path / "book.sqlite", anchor_config=config, anchor_rpc=rpc)
    with TestClient(app) as client:
        device, address = register(client)
        pid = buy_quake(client, device, address, 20_000)["policy_id"]
        out = client.post("/api/operator/anchor/run", headers=OP).json()
        assert out["report"]["sent"] == 0 and "refused" in out["anchor"]["last_error"]
        assert client.get(f"/api/policies/{pid}/anchor").json()["intents"][0]["status"] == "pending"
    # Back up, with the node answering: the pending intent is still there and goes out.
    node = FakeNode()
    rpc = Rpc(config.rpc_url, transport=node.transport())
    app = create_app(trials=300, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, specimens=True),
                     store_path=tmp_path / "book.sqlite", anchor_config=config, anchor_rpc=rpc)
    with TestClient(app) as client:
        before = client.get(f"/api/policies/{pid}/anchor").json()["intents"]
        assert [i["kind"] for i in before] == ["mint"] and before[0]["status"] == "pending"
        client.post("/api/operator/anchor/run", headers=OP)
        assert client.get(f"/api/policies/{pid}/anchor").json()["intents"][0]["status"] == "sent"
        assert len(node.sent) >= 1


def test_the_backfill_queues_tokens_from_before_anchoring_but_not_burned_ones() -> None:
    class P:
        def __init__(self, pid, burned=False):
            self.policy_id = pid; self.holder = "h"; self.limit = 1.0; self.starts_at = 0; self.ends_at = 1
            self.status = type("S", (), {"value": "active"})()
            self.metadata = {"token": {"terms_hash": "0x" + "ab" * 32, "burned_at": time.time() if burned else None}}
    ended = P("D"); ended.is_open = False; ended.status = type("S", (), {"value": "lapsed"})()
    pool = type("Pool", (), {"policies": {"A": P("A"), "B": P("B", burned=True), "C": P("C"), "D": ended}})()
    anchor = Anchor(AnchorConfig(), pool=pool)
    assert anchor.backfill() == 2 and anchor.backfill() == 0
    assert sorted(i.policy_id for i in anchor.intents.values()) == ["A", "C"]   # not the burned one, not the ended one
    root = anchor.anchor_root()
    assert root is not None and root.payload["count"] == 4 and anchor.anchor_root() is None
    assert anchor.proof("D")["verified"]                                           # ended cover is still in the root
    # A mint an earlier build queued for cover that has since ended is dropped unsent.
    pool.policies["A"].is_open = False
    assert anchor.backfill() == 0 and sorted(i.policy_id for i in anchor.intents.values() if i.kind == "mint") == ["C"]
    assert anchor.proof("A")["verified"]


def test_a_mint_recorded_before_there_was_a_signer_goes_to_the_signer_once_there_is_one(tmp_path, node) -> None:
    # Recorded without a key: the recipient is nobody yet.
    with TestClient(app_for(tmp_path, None, live=False)) as client:
        device, address = register(client)
        pid = buy_quake(client, device, address, 20_000)["policy_id"]
        mint = client.get(f"/api/policies/{pid}/anchor").json()["intents"][0]
        assert mint["payload"]["to"] == "0x" + "00" * 20
    # The same book, now with a key: the mint goes to the signer, not to nobody.
    with TestClient(app_for(tmp_path, node, live=True)) as client:
        client.post("/api/operator/anchor/run", headers=OP)
        mint = client.get(f"/api/policies/{pid}/anchor").json()["intents"][0]
        assert mint["status"] == "sent" and mint["payload"]["to"] == SIGNER
        raw = next(r for r in node.sent if rlp_decode(r[1:])[7][:4] == selector(CALLS["mint"]))
        assert rlp_decode(raw[1:])[7][16:36] == to_address(SIGNER)
    # And one that already failed for that reason is queued again with its recipient.
    with TestClient(app_for(tmp_path, node, live=True)) as client:
        anchor = client.app.state.anchor
        device, address = register(client)
        pid2 = buy_quake(client, device, address, 20_000)["policy_id"]
        broken = next(i for i in anchor.intents.values() if i.kind == "mint" and i.policy_id == pid2)
        broken.payload["to"] = "0x" + "00" * 20
        broken.status, broken.error = "failed", "execution reverted: ZeroAddress()"
        client.post("/api/operator/anchor/run", headers=OP)
        again = client.get(f"/api/policies/{pid2}/anchor").json()["intents"][0]
        assert again["status"] == "sent" and again["payload"]["to"] == SIGNER and again["error"] == ""


def link_evm(client, device, address, wallet) -> None:
    """The holder links an Ethereum wallet on their profile, both proofs given."""
    auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
    start = client.post("/api/profile/links/start", headers=auth, json={"kind": "evm", "address": wallet.address}).json()
    challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "link-wallet",
                                                         "terms": {"kind": "evm", "address": wallet.address}}).json()
    made = client.post("/api/profile/links", json={
        "account": address, "kind": "evm", "address": wallet.address,
        "wallet_nonce": start["nonce"], "wallet_signature": wallet.sign(start["message"]),
        "nonce": challenge["nonce"], "signature": device.sign(challenge["message"])})
    assert made.status_code == 200, made.text


def test_the_holder_gets_the_token_in_their_own_wallet(tmp_path, node) -> None:
    from test_api_security import session_for as _session
    from test_links import MetaMask
    with TestClient(app_for(tmp_path, node, live=True)) as client:
        device, address = register(client)
        auth = {"authorization": f"Bearer {_session(client, device, address)}"}
        pid = buy_quake(client, device, address, 20_000)["policy_id"]
        # Nobody linked: the mint goes to the signer, and the page offers the profile.
        mine = client.get(f"/api/policies/{pid}/anchor", headers=auth).json()
        assert mine["held"]["custodial"] and mine["wallets"] == []
        assert "wallets" not in client.get(f"/api/policies/{pid}/anchor").json()      # a stranger sees no wallets
        refused = client.post(f"/api/policies/{pid}/anchor/claim", headers=auth, json={})
        assert refused.status_code == 409 and "link an Ethereum wallet" in refused.text
        # Linked before the mint is sent: the mint is simply pointed at the wallet.
        wallet = MetaMask()
        link_evm(client, device, address, wallet)
        claimed = client.post(f"/api/policies/{pid}/anchor/claim", headers=auth, json={}).json()
        assert [i["kind"] for i in claimed["queued"]] == ["mint"] and claimed["held"]["to"].lower() == wallet.address.lower()
        assert not claimed["held"]["custodial"]
        client.post("/api/operator/anchor/run", headers=OP)
        client.post("/api/operator/anchor/run", headers=OP)
        assert client.get(f"/api/policies/{pid}/anchor", headers=auth).json()["held"]["status"] == "confirmed"
        # A second policy, minted to the wallet from the start, and one already on the
        # chain that moves: burn first, then a mint that waits for the burn.
        pid2 = buy_quake(client, device, address, 20_000)["policy_id"]
        assert client.get(f"/api/policies/{pid2}/anchor", headers=auth).json()["held"]["to"].lower() == wallet.address.lower()
        other = MetaMask()
        link_evm(client, device, address, other)
        moved = client.post(f"/api/policies/{pid}/anchor/claim", headers=auth, json={"address": other.address}).json()
        assert [i["kind"] for i in moved["queued"]] == ["burn", "mint"]
        client.post("/api/operator/anchor/run", headers=OP)
        rows = {i["intent_id"]: i for i in client.get(f"/api/policies/{pid}/anchor", headers=auth).json()["intents"]}
        burn, remint = rows[moved["queued"][0]["intent_id"]], rows[moved["queued"][1]["intent_id"]]
        assert burn["status"] == "sent" and remint["status"] == "pending"                  # the mint waits for the burn
        client.post("/api/operator/anchor/run", headers=OP)                                # the burn confirms, the mint goes
        rows = {i["intent_id"]: i for i in client.get(f"/api/policies/{pid}/anchor", headers=auth).json()["intents"]}
        assert rows[burn["intent_id"]]["status"] == "confirmed" and rows[remint["intent_id"]]["status"] == "sent"
        held = client.get(f"/api/policies/{pid}/anchor", headers=auth).json()["held"]
        assert held["to"].lower() == other.address.lower() and held["status"] == "sent"
        # Not one of the holder's wallets: refused. A stranger: nothing.
        assert client.post(f"/api/policies/{pid}/anchor/claim", headers=auth, json={"address": SIGNER}).status_code == 409
        stranger, s_addr = register(client)
        assert client.post(f"/api/policies/{pid}/anchor/claim", json={},
                           headers={"authorization": f"Bearer {_session(client, stranger, s_addr)}"}).status_code == 404
        # Cancelling later burns the re-issued token too: the protocol's own burn is not deduplicated away.
        signed_post(client, device, address, "cancel", {"policy_id": pid}, f"/api/policies/{pid}/cancel", {"account": address})
        kinds = [i["kind"] for i in client.get(f"/api/policies/{pid}/anchor", headers=auth).json()["intents"]]
        assert kinds.count("burn") == 2
