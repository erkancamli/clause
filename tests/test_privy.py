"""Signing in through Privy: the token check, and one account across devices.

Privy's real keys are not used. A key pair made here stands in for Privy's
signing key and its public half is served as the JWKS, which is exactly the
shape the server reads in production.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.privy import PrivyError, PrivyVerifier
from clause.api.security import Settings

APP = "cmtestapp0000000000000000"
SIGNER = ec.generate_private_key(ec.SECP256R1())


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwks(key=SIGNER, kid="k1") -> bytes:
    n = key.public_key().public_numbers()
    return json.dumps({"keys": [{"kty": "EC", "crv": "P-256", "kid": kid, "alg": "ES256",
                                 "x": b64(n.x.to_bytes(32, "big")), "y": b64(n.y.to_bytes(32, "big"))}]}).encode()


def token(sub="did:privy:alice", *, aud=APP, iss="privy.io", exp=None, key=SIGNER, kid="k1") -> str:
    now = time.time()
    head = b64(json.dumps({"alg": "ES256", "typ": "JWT", "kid": kid}).encode())
    body = b64(json.dumps({"sid": "s", "sub": sub, "iss": iss, "aud": aud,
                           "iat": int(now), "exp": int(exp if exp is not None else now + 3600)}).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"{head}.{body}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def verifier() -> PrivyVerifier:
    return PrivyVerifier(APP, fetcher=lambda url: jwks())


def test_a_valid_token_names_its_user() -> None:
    assert verifier().verify(token()) == "did:privy:alice"


@pytest.mark.parametrize("bad, why", [
    (lambda: token(aud="another-app"), "another app"),
    (lambda: token(iss="evil.example"), "not issued by Privy"),
    (lambda: token(exp=time.time() - 3600), "expired"),
    (lambda: token(key=ec.generate_private_key(ec.SECP256R1())), "does not verify"),
    (lambda: token(sub="alice"), "no Privy user"),
    (lambda: "not.a.token", "not a Privy"),
    (lambda: token().rsplit(".", 1)[0] + "." + b64(b"x" * 64), "does not verify"),
])
def test_a_token_that_proves_nothing_is_refused(bad, why) -> None:
    with pytest.raises(PrivyError, match=why):
        verifier().verify(bad())


def test_a_rotated_key_is_picked_up_without_a_restart() -> None:
    new = ec.generate_private_key(ec.SECP256R1())
    served = {"keys": jwks()}
    v = PrivyVerifier(APP, fetcher=lambda url: served["keys"])
    assert v.verify(token()) == "did:privy:alice"
    served["keys"] = jwks(new, kid="k2")
    later = time.time() + 120
    assert v.verify(token(key=new, kid="k2"), now=later) == "did:privy:alice"


# ---------------------------------------------------------------------------
# One person, two devices
# ---------------------------------------------------------------------------


def device():
    key = ec.generate_private_key(ec.SECP256R1())
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    raw = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return key, b64(raw)


def sign(key, message: str) -> str:
    r, s = decode_dss_signature(key.sign(message.encode(), ec.ECDSA(hashes.SHA256())))
    return b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def link(client, key, public, privy_token):
    address = client.post("/api/auth/register", json={"public_key": public}).json()["address"]
    challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "link"}).json()
    return client.post("/api/privy/link", json={
        "privy_token": privy_token, "address": address,
        "nonce": challenge["nonce"], "signature": sign(key, challenge["message"]),
    })


@pytest.fixture
def client():
    app = create_app(trials=200, run_chain=False, seed_book=False, settings=Settings(),
                     privy_verifier=verifier())
    with TestClient(app) as c:
        yield c


def test_privy_is_off_unless_configured() -> None:
    app = create_app(trials=200, run_chain=False, seed_book=False, settings=Settings())
    with TestClient(app) as c:
        assert c.get("/api/privy").json() == {"enabled": False}
        assert c.post("/api/privy/link", json={"privy_token": "x", "address": "x", "nonce": "x",
                                               "signature": "x"}).status_code == 404


def test_the_same_person_gets_the_same_account_on_a_second_device(client) -> None:
    assert client.get("/api/privy").json() == {"enabled": True, "app_id": APP}
    phone, phone_pub = device()
    laptop, laptop_pub = device()
    first = link(client, phone, phone_pub, token()).json()
    second = link(client, laptop, laptop_pub, token()).json()
    assert first["linked"] is False and second["linked"] is True
    assert second["address"] == first["address"] != second["device"]

    # The laptop's key can now sign for the account: a sign in challenge for
    # the account address, signed on the laptop, is accepted.
    account = first["address"]
    challenge = client.post("/api/auth/challenge", json={"address": account, "purpose": "sign-in"}).json()
    reply = client.post("/api/auth/verify", json={"address": account, "nonce": challenge["nonce"],
                                                   "signature": sign(laptop, challenge["message"])})
    assert reply.status_code == 200 and reply.json()["address"] == account


def test_another_person_gets_their_own_account(client) -> None:
    a, a_pub = device()
    b, b_pub = device()
    alice = link(client, a, a_pub, token("did:privy:alice")).json()
    bob = link(client, b, b_pub, token("did:privy:bob")).json()
    assert alice["address"] != bob["address"]
    # Bob's key cannot sign for Alice.
    challenge = client.post("/api/auth/challenge", json={"address": alice["address"], "purpose": "sign-in"}).json()
    reply = client.post("/api/auth/verify", json={"address": alice["address"], "nonce": challenge["nonce"],
                                                   "signature": sign(b, challenge["message"])})
    assert reply.status_code == 401


def test_linking_needs_both_proofs(client) -> None:
    key, public = device()
    assert link(client, key, public, token(aud="another-app")).status_code == 401
    other, _ = device()
    address = client.post("/api/auth/register", json={"public_key": public}).json()["address"]
    challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "link"}).json()
    reply = client.post("/api/privy/link", json={
        "privy_token": token(), "address": address,
        "nonce": challenge["nonce"], "signature": sign(other, challenge["message"]),
    })
    assert reply.status_code == 401
