"""Proving control of an address, and the ways of failing to.

Before this existed the API believed whatever address a request claimed. These
tests are the specification of what it now takes to spend from one.
"""

from __future__ import annotations

import base64
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from clause.protocol.auth import (
    AuthError,
    Authenticator,
    address_for,
    load_public_key,
    terms_digest,
)


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class Device:
    """A buyer's phone: it makes a key, keeps it, and signs with it."""

    def __init__(self, curve=ec.SECP256R1()):
        self.key = ec.generate_private_key(curve)

    @property
    def public_raw(self) -> str:
        return b64(
            self.key.public_key().public_bytes(
                Encoding.X962, PublicFormat.UncompressedPoint
            )
        )

    @property
    def public_der(self) -> str:
        return b64(
            self.key.public_key().public_bytes(
                Encoding.DER, PublicFormat.SubjectPublicKeyInfo
            )
        )

    def sign(self, message: str) -> str:
        return b64(self.key.sign(message.encode(), ec.ECDSA(hashes.SHA256())))


TERMS = {"peril": "earthquake", "limit": 100000, "term_days": 365}


def signed_in(auth: Authenticator, device: Device) -> str:
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "sign-in")
    auth.verify(
        challenge.nonce, device.sign(challenge.message),
        purpose="sign-in", address=address,
    )
    return address


# ---------------------------------------------------------------------------
# The address is the key
# ---------------------------------------------------------------------------


def test_the_address_is_derived_from_the_key_not_assigned() -> None:
    device = Device()
    auth = Authenticator()
    address = auth.register(device.public_raw)
    from clause.protocol.address import is_address
    assert is_address(address) and not address.startswith("0x") and len(address) in (43, 44)
    # Registering the same key again is the same address, which is what lets a
    # returning buyer sign in from the same device.
    assert auth.register(device.public_raw) == address
    assert auth.register(Device().public_raw) != address


def test_a_key_arrives_in_either_form_a_browser_exports() -> None:
    device = Device()
    assert address_for(load_public_key(device.public_raw)) == address_for(
        load_public_key(device.public_der)
    )


def test_a_key_on_the_wrong_curve_is_refused() -> None:
    """P-256 only: it is what platform authenticators sign with."""
    with pytest.raises(AuthError):
        Authenticator().register(Device(ec.SECP384R1()).public_raw)


@pytest.mark.parametrize("junk", ["", "not base64!!", b64(b"\x04" + b"\x00" * 64)])
def test_rubbish_is_refused_rather_than_crashing(junk: str) -> None:
    with pytest.raises(AuthError):
        Authenticator().register(junk)


# ---------------------------------------------------------------------------
# Challenge and signature
# ---------------------------------------------------------------------------


def test_a_correct_signature_passes() -> None:
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "buy", TERMS)
    spent = auth.verify(
        challenge.nonce, device.sign(challenge.message),
        purpose="buy", address=address, payload=TERMS,
    )
    assert spent.address == address


def test_a_challenge_can_only_be_spent_once() -> None:
    """Otherwise a captured signature is a standing authorisation."""
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "buy", TERMS)
    signature = device.sign(challenge.message)

    auth.verify(challenge.nonce, signature, purpose="buy", address=address, payload=TERMS)
    with pytest.raises(AuthError):
        auth.verify(
            challenge.nonce, signature, purpose="buy", address=address, payload=TERMS
        )


def test_a_signature_for_one_policy_cannot_buy_another() -> None:
    """The reason the terms are inside the signed message."""
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "buy", TERMS)
    signature = device.sign(challenge.message)

    bigger = dict(TERMS, limit=900_000)
    with pytest.raises(AuthError):
        auth.verify(
            challenge.nonce, signature, purpose="buy", address=address, payload=bigger
        )


def test_a_sign_in_signature_cannot_be_used_to_spend() -> None:
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "sign-in")
    signature = device.sign(challenge.message)
    with pytest.raises(AuthError):
        auth.verify(challenge.nonce, signature, purpose="buy", address=address)


def test_another_device_cannot_answer_your_challenge() -> None:
    auth, mine, theirs = Authenticator(), Device(), Device()
    address = auth.register(mine.public_raw)
    auth.register(theirs.public_raw)
    challenge = auth.challenge(address, "buy", TERMS)
    with pytest.raises(AuthError):
        auth.verify(
            challenge.nonce, theirs.sign(challenge.message),
            purpose="buy", address=address, payload=TERMS,
        )


def test_an_expired_challenge_is_refused() -> None:
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "sign-in", now=time.time() - 600)
    with pytest.raises(AuthError):
        auth.verify(
            challenge.nonce, device.sign(challenge.message),
            purpose="sign-in", address=address,
        )


def test_a_challenge_for_an_unknown_address_is_refused() -> None:
    with pytest.raises(AuthError):
        Authenticator().challenge("0x" + "ab" * 20, "sign-in")


def test_an_unknown_purpose_is_refused() -> None:
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    with pytest.raises(AuthError):
        auth.challenge(address, "drain-the-pool")


def test_open_challenges_cannot_be_piled_up_without_limit() -> None:
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    from clause.protocol import auth as module

    original = module.MAX_OPEN_CHALLENGES
    try:
        module.MAX_OPEN_CHALLENGES = 5
        for _ in range(5):
            auth.challenge(address, "sign-in")
        with pytest.raises(AuthError):
            auth.challenge(address, "sign-in")
    finally:
        module.MAX_OPEN_CHALLENGES = original


def test_expired_challenges_are_cleared_as_new_ones_are_issued() -> None:
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    auth.challenge(address, "sign-in", now=time.time() - 600)
    auth.challenge(address, "sign-in")
    assert len(auth._challenges) == 1


# ---------------------------------------------------------------------------
# What is signed
# ---------------------------------------------------------------------------


def test_the_signed_message_names_everything_it_authorises() -> None:
    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "buy", TERMS)
    assert challenge.message.startswith("clause:v1:buy:")
    assert address in challenge.message
    assert challenge.nonce in challenge.message


def test_the_terms_digest_ignores_key_order_and_not_values() -> None:
    assert terms_digest({"a": 1, "b": 2}) == terms_digest({"b": 2, "a": 1})
    assert terms_digest({"a": 1}) != terms_digest({"a": 2})
    # Nested subjects are covered too, since that is where the location lives.
    assert terms_digest({"s": {"x": 1, "y": 2}}) == terms_digest({"s": {"y": 2, "x": 1}})
    assert terms_digest({"s": {"x": 1}}) != terms_digest({"s": {"x": 9}})


# ---------------------------------------------------------------------------
# Read sessions
# ---------------------------------------------------------------------------


def test_a_session_identifies_its_own_address() -> None:
    auth, device = Authenticator(), Device()
    address = signed_in(auth, device)
    token = auth.issue_session(address)["token"]
    assert auth.session_address(token) == address


def test_a_tampered_token_is_refused() -> None:
    auth, device = Authenticator(), Device()
    address = signed_in(auth, device)
    token = auth.issue_session(address)["token"]
    other = "0x" + "cd" * 20
    forged = token.replace(address, other)
    with pytest.raises(AuthError):
        auth.session_address(forged)


def test_a_token_from_another_server_is_refused() -> None:
    device = Device()
    mine, theirs = Authenticator(), Authenticator()
    address = signed_in(mine, device)
    theirs.register(device.public_raw)
    token = theirs.issue_session(address)["token"]
    with pytest.raises(AuthError):
        mine.session_address(token)


def test_an_expired_token_is_refused() -> None:
    auth, device = Authenticator(), Device()
    address = signed_in(auth, device)
    token = auth.issue_session(address, now=time.time() - 10**6)["token"]
    with pytest.raises(AuthError):
        auth.session_address(token)


@pytest.mark.parametrize("junk", ["", "a.b", "no-dots-at-all"])
def test_a_malformed_token_is_refused_rather_than_crashing(junk: str) -> None:
    with pytest.raises(AuthError):
        Authenticator().session_address(junk)


# ---------------------------------------------------------------------------
# The form a browser actually sends
# ---------------------------------------------------------------------------


def test_a_browser_signature_verifies() -> None:
    """WebCrypto emits r then s, raw. Everything else here speaks DER.

    If this did not hold, the passkey door would not work at all in a browser,
    which is the door most people are meant to come through.
    """
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    auth, device = Authenticator(), Device()
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "sign-in")

    der = device.key.sign(challenge.message.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    spent = auth.verify(challenge.nonce, b64(raw), purpose="sign-in", address=address)
    assert spent.address == address


def test_a_wrong_browser_signature_still_fails() -> None:
    """The conversion must not become a way in."""
    auth, device, other = Authenticator(), Device(), Device()
    address = auth.register(device.public_raw)
    challenge = auth.challenge(address, "sign-in")

    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    der = other.key.sign(challenge.message.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    with pytest.raises(AuthError):
        auth.verify(challenge.nonce, b64(raw), purpose="sign-in", address=address)
