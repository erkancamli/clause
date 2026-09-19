"""Wallets and an X account joined to an account, each proved its own way."""

from __future__ import annotations

import base64
import json
import secrets
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol import evm
from clause.protocol.links import LinkError, Links, link_text
from test_privy import APP, SIGNER, b64, device, link, sign, verifier

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


class Phantom:
    """A Solana wallet: an ed25519 key that signs a message."""

    def __init__(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.address = b58(self.key.public_key().public_bytes_raw())

    def sign(self, message: str) -> str:
        return base64.b64encode(self.key.sign(message.encode())).decode()


class MetaMask:
    """An Ethereum wallet: secp256k1, personal_sign. Signing is only here,
    in the test; the protocol never signs."""

    def __init__(self) -> None:
        self.d = secrets.randbelow(evm._N - 1) + 1
        point = evm._mul(self.d, evm._G)
        self.address = evm.address_of(point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big"))

    def sign(self, message: str) -> str:
        e = int.from_bytes(evm.personal_digest(message.encode()), "big") % evm._N
        while True:
            k = secrets.randbelow(evm._N - 1) + 1
            R = evm._mul(k, evm._G)
            r = R[0] % evm._N
            s = pow(k, -1, evm._N) * (e + r * self.d) % evm._N
            if r and s:
                break
        v = R[1] & 1
        if s > evm._N // 2:
            s, v = evm._N - s, v ^ 1
        return "0x" + (r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v + 27])).hex()


def test_a_solana_wallet_is_linked_by_its_own_signature() -> None:
    links = Links()
    wallet = Phantom()
    with pytest.raises(LinkError, match="ask for the text"):
        links.add("acct", "solana", wallet.address, nonce="x", signature="y")
    start = links.start("acct", "solana", wallet.address)
    assert wallet.address in start["message"] and "acct" in start["message"]
    with pytest.raises(LinkError, match="does not verify"):
        links.add("acct", "solana", wallet.address, nonce=start["nonce"], signature=Phantom().sign(start["message"]))
    start = links.start("acct", "solana", wallet.address)
    made = links.add("acct", "solana", wallet.address, nonce=start["nonce"], signature=wallet.sign(start["message"]))
    assert made.verified and made.proof == "signature"
    assert links.account_of("solana", wallet.address) == "acct"
    # The same wallet cannot be claimed by a second account.
    start = links.start("other", "solana", wallet.address)
    with pytest.raises(LinkError, match="another account"):
        links.add("other", "solana", wallet.address, nonce=start["nonce"], signature=wallet.sign(start["message"]))


def test_an_ethereum_wallet_is_linked_by_personal_sign() -> None:
    links = Links()
    wallet = MetaMask()
    start = links.start("acct", "evm", wallet.address)
    made = links.add("acct", "evm", wallet.address, nonce=start["nonce"], signature=wallet.sign(start["message"]))
    assert made.verified and made.address == wallet.address.lower()
    # A nonce is spent once.
    with pytest.raises(LinkError, match="ask for the text"):
        links.add("acct", "evm", wallet.address, nonce=start["nonce"], signature=wallet.sign(start["message"]))


def test_a_rialo_address_is_written_down_as_stated() -> None:
    links = Links()
    made = links.add("acct", "rialo", Phantom().address)
    assert not made.verified and made.proof == "stated"
    assert links.public("acct") == {"x": None, "wallets": 0}
    links.remove("acct", made.link_id)
    assert links.mine("acct") == []


def test_an_x_account_comes_from_privy_and_is_one_per_person() -> None:
    links = Links()
    a = links.add_x("acct", "@e_camli", "12345")
    assert a.address == "e_camli" and a.verified and a.proof == "privy"
    with pytest.raises(LinkError, match="another account"):
        links.add_x("other", "e_camli", "12345")
    b = links.add_x("acct", "ekinoks_26", "12345")
    assert b.link_id == a.link_id and links.public("acct")["x"] == "ekinoks_26"
    with pytest.raises(LinkError, match="not an X handle"):
        links.add_x("acct", "not a handle!", "1")


# -- over the API --------------------------------------------------------------


def identity_token(sub="did:privy:alice", accounts=None) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    now = time.time()
    head = b64(json.dumps({"alg": "ES256", "typ": "JWT", "kid": "k1"}).encode())
    body = b64(json.dumps({"sub": sub, "iss": "privy.io", "aud": APP, "iat": int(now), "exp": int(now + 3600),
                           "linked_accounts": json.dumps(accounts or [])}).encode())
    r, s = decode_dss_signature(SIGNER.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"{head}.{body}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


@pytest.fixture
def client():
    app = create_app(trials=200, run_chain=False, seed_book=False, settings=Settings(faucet=True),
                     privy_verifier=verifier())
    with TestClient(app) as c:
        yield c


def test_the_profile_shows_what_is_linked_and_links_a_wallet_with_both_proofs(client) -> None:
    from test_privy import token
    key, public = device()
    reply = link(client, key, public, token()).json()
    address, auth = reply["address"], {"authorization": f"Bearer {reply['session']['token']}"}
    profile = client.get("/api/profile", headers=auth).json()
    assert profile["address"] == address and profile["via"] == "privy" and profile["links"] == []
    assert profile["x_enabled"] is True
    wallet = MetaMask()
    start = client.post("/api/profile/links/start", headers=auth, json={"kind": "evm", "address": wallet.address}).json()
    challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "link-wallet",
                                                         "terms": {"kind": "evm", "address": wallet.address}}).json()
    made = client.post("/api/profile/links", json={
        "account": address, "kind": "evm", "address": wallet.address,
        "wallet_nonce": start["nonce"], "wallet_signature": wallet.sign(start["message"]),
        "nonce": challenge["nonce"], "signature": sign(key, challenge["message"])})
    assert made.status_code == 200, made.text
    assert made.json()["link"]["verified"] is True
    assert client.get("/api/profile", headers=auth).json()["links"][0]["kind"] == "evm"
    # X, from an identity token Privy signed for this same user.
    x = client.post("/api/profile/x", headers=auth, json={"identity_token": identity_token(
        accounts=[{"type": "email", "address": "a@b.c"}, {"type": "twitter_oauth", "subject": "99", "username": "e_camli"}])})
    assert x.status_code == 200, x.text
    assert x.json()["link"]["short"] == "@e_camli"
    # Another user's token cannot put their X on this account.
    other = client.post("/api/profile/x", headers=auth, json={"identity_token": identity_token(
        sub="did:privy:bob", accounts=[{"type": "twitter_oauth", "subject": "1", "username": "bob"}])})
    assert other.status_code == 409
    none = client.post("/api/profile/x", headers=auth, json={"identity_token": identity_token(accounts=[])})
    assert none.status_code == 422
    link_id = made.json()["link"]["link_id"]
    assert client.post(f"/api/profile/links/{link_id}/remove", headers=auth).json()["links"][0]["kind"] == "x"


def test_a_deposit_from_a_linked_wallet_is_credited_without_an_announcement() -> None:
    from clause.protocol.funding import Destinations, Funding, Watcher
    from clause.protocol.wallet import Wallets
    wallets = Wallets(demo_balance=0.0)
    wallets.connect("acct", fund=False)
    links = Links()
    wallet = MetaMask()
    start = links.start("acct", "evm", wallet.address)
    links.add("acct", "evm", wallet.address, nonce=start["nonce"], signature=wallet.sign(start["message"]))
    to = "0x" + "ee" * 20
    usdc = "0x" + "ab" * 20
    funding = Funding(wallets, Destinations(evm=to), links=links)
    log = {"transactionHash": "0x01", "logIndex": "0x0", "data": hex(250 * 10 ** 6),
           "topics": ["t", "0x" + wallet.address[2:].rjust(64, "0"), "0x" + to[2:].rjust(64, "0")]}
    def rpc(url, method, params):
        return {"eth_blockNumber": "0x10", "eth_getLogs": [log]}[method]
    watcher = Watcher(funding, evm_rpc="http://rpc", evm_usdc=usdc, rpc=rpc)
    assert watcher.run() == 1
    assert wallets.require("acct").balance == pytest.approx(250)
    req = next(iter(funding.requests.values()))
    assert req.status == "received" and req.reference == "LINKED" and "linked wallet" in req.note
    # Seen once: the same log is not credited twice.
    assert watcher.run() == 0
