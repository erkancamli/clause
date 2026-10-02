"""Proving who you are, without anyone holding a password.

The identity module says an address is whoever holds its key. Until this module
existed that was a claim rather than a fact: the API took an address as a string
in the request body and believed it. Anyone could read the addresses off the
public endpoints and spend from them. This closes that.

How it works
------------
A key pair is generated on the buyer's own device and the private half never
leaves it. The address is derived from the public half, so the key is not
attached to the identity, the key *is* the identity and there is nothing to look
up, reset, or leak.

  register   the device sends its public key; the server derives the address
  challenge  the server issues a single use nonce, valid for a minute
  verify     the device signs the nonce; the server checks it against the key
  session    a short lived token follows, for reads only

Writes are not covered by the session. A transaction carries its own signature
over its own terms, so a captured session cannot buy a different policy than the
one the holder approved, and a signature captured from one purchase cannot be
replayed for another.

The curve
---------
P-256, ECDSA, SHA-256. That choice is not arbitrary. It is the curve WebAuthn and
the platform authenticators use, which is what lets the ordinary door in this
protocol be a fingerprint rather than a seed phrase. It is also the curve behind
Rialo's published ``rialo-s-secp256r1-program``, so a signature verified here is
verifiable by the chain rather than only by us.

What this module is not
-----------------------
It is not a full WebAuthn implementation: it verifies a raw ECDSA signature over
a server issued challenge rather than parsing an authenticator attestation. A
deployment swaps the verification call for an attestation check and changes
nothing else, because everything above it depends only on "this address proved it
holds its key".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
)

# A challenge is short lived. Long enough for a person to touch a sensor, short
# enough that a captured one is worthless by the time it is used.
CHALLENGE_SECONDS = 90

# A read session. Writes are signed individually, so this only grants the right
# to look at your own policies.
SESSION_SECONDS = 30 * 60

# Never hold more unredeemed challenges than this, so an attacker cannot grow
# the table by asking for challenges and never answering.
MAX_OPEN_CHALLENGES = 4096

_PROTOCOL = "clause:v1"


class AuthError(RuntimeError):
    """Authentication failed. The message is deliberately uninformative."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + padding)
    except Exception as error:  # noqa: BLE001 - any decode failure is the same failure
        raise AuthError("malformed encoding") from error


def _to_der(signature: bytes) -> bytes:
    """Accept the signature form a browser produces as well as the usual one.

    WebCrypto and WebAuthn emit ECDSA signatures as the raw pair r then s, each
    padded to the curve's size, which for P-256 is sixty four bytes. Everything
    on the server side speaks DER. Converting here rather than in the browser
    keeps the page free of hand written ASN.1, which is exactly the kind of code
    that should not be hand written.
    """
    if len(signature) == 64:
        r = int.from_bytes(signature[:32], "big")
        s = int.from_bytes(signature[32:], "big")
        return encode_dss_signature(r, s)
    return signature


def load_public_key(encoded: str) -> ec.EllipticCurvePublicKey:
    """Read a P-256 public key, in either form a browser will send.

    WebCrypto exports raw (65 byte uncompressed point) or SPKI DER. Both are
    accepted; anything else, including a key on another curve, is refused.
    """
    raw = _unb64(encoded)
    key: ec.EllipticCurvePublicKey
    if len(raw) == 65 and raw[0] == 0x04:
        try:
            key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
        except ValueError as error:
            raise AuthError("not a point on P-256") from error
    else:
        try:
            loaded = load_der_public_key(raw)
        except Exception as error:  # noqa: BLE001
            raise AuthError("unreadable public key") from error
        if not isinstance(loaded, ec.EllipticCurvePublicKey):
            raise AuthError("not an elliptic curve key")
        key = loaded

    if not isinstance(key.curve, ec.SECP256R1):
        raise AuthError("only P-256 keys are accepted")
    return key


def raw_public_key(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


def address_for(key: ec.EllipticCurvePublicKey) -> str:
    """The address a key controls.

    Derived from the key, so possession of the key is the only claim to the
    address, and two devices cannot end up sharing one by accident.
    """
    from .address import from_material
    return from_material(raw_public_key(key))


def terms_digest(payload: dict[str, Any]) -> str:
    """A stable fingerprint of what is being approved.

    Signed along with the nonce, so a signature authorises one specific policy on
    one specific terms, and not merely "a purchase".
    """
    parts = []
    for name in sorted(payload):
        value = payload[name]
        if isinstance(value, dict):
            value = ";".join(f"{k}={value[k]}" for k in sorted(value))
        parts.append(f"{name}={value}")
    body = "|".join(parts)
    return hashlib.blake2b(body.encode(), digest_size=16).hexdigest()


@dataclass(slots=True)
class Challenge:
    """A nonce, bound to one address and one action, usable once."""

    nonce: str
    address: str
    purpose: str
    digest: str
    issued_at: float
    expires_at: float

    @property
    def message(self) -> str:
        """Exactly the bytes the device signs. Nothing implicit."""
        return f"{_PROTOCOL}:{self.purpose}:{self.address}:{self.digest}:{self.nonce}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "nonce": self.nonce,
            "message": self.message,
            "expires_at": self.expires_at,
            "purpose": self.purpose,
        }


class Authenticator:
    """Registration, challenges, signature checks and read sessions."""

    def __init__(self, *, secret: bytes | None = None) -> None:
        # Used only to sign read session tokens. Supplied by the operator in a
        # deployment so tokens survive a restart; random otherwise, which simply
        # means everyone signs in again.
        self._secret = secret or os.urandom(32)
        self.keys: dict[str, ec.EllipticCurvePublicKey] = {}
        # Further keys allowed to act for an address: the other devices of a
        # person who signs in the same way on each. The address is still the
        # one its first key derived; these only add who may sign for it.
        self.signers: dict[str, list[ec.EllipticCurvePublicKey]] = {}
        # Addresses whose key this build could not read back. They cannot sign
        # until it can, but they are somebody's: an address is what makes a
        # policy theirs, and a key is only what lets them act on it. Kept
        # because the two were being confused, and a reader that failed left
        # the holder looking like nobody -- which is the test the background
        # job used to decide what it could delete.
        self.unreadable: set[str] = set()
        self._challenges: dict[str, Challenge] = {}

    # -- registration -----------------------------------------------------

    def register(self, public_key: str) -> str:
        """Record a device's public key and return the address it controls.

        Registering twice with the same key is not an error and changes nothing,
        which is what lets a returning buyer sign in from the same device.
        """
        key = load_public_key(public_key)
        raw = raw_public_key(key)
        # A key registered under an earlier address form keeps its address:
        # the policies and the balance are there, and a device must not find
        # itself a stranger to its own account after an update.
        for known_address, known in self.keys.items():
            if raw_public_key(known) == raw:
                return known_address
        address = address_for(key)
        existing = self.keys.get(address)
        if existing is not None and raw_public_key(existing) != raw:
            # Two different keys deriving one address would be a hash collision.
            raise AuthError("address already claimed by another key")
        self.keys[address] = key
        return address

    def knows(self, address: str) -> bool:
        return address in self.keys

    MAX_SIGNERS = 8

    def authorize(self, address: str, device_address: str) -> None:
        """Let the key behind ``device_address`` sign for ``address`` too.

        Both must be registered. The caller has already proved the person
        behind both is the same one; this module does not decide that.
        """
        if address not in self.keys or device_address not in self.keys:
            raise AuthError("unknown address")
        if address == device_address:
            return
        key = self.keys[device_address]
        known = self.signers.setdefault(address, [])
        if any(raw_public_key(k) == raw_public_key(key) for k in known):
            return
        if len(known) >= self.MAX_SIGNERS:
            known.pop(0)   # the oldest device gives way
        known.append(key)

    # -- challenges -------------------------------------------------------

    def challenge(
        self, address: str, purpose: str, payload: dict[str, Any] | None = None,
        *, now: float | None = None,
    ) -> Challenge:
        """Issue a single use nonce for one address and one action."""
        if address not in self.keys:
            raise AuthError("unknown address")
        if purpose not in {"sign-in", "buy", "deposit", "withdraw", "link", "register",
                           "payout", "mandate", "cancel", "partner", "cashout", "link-wallet",
                           "instruct", "withdraw-application"}:
            raise AuthError("unknown purpose")

        now = time.time() if now is None else now
        self._prune(now)
        if len(self._challenges) >= MAX_OPEN_CHALLENGES:
            raise AuthError("too many open challenges")

        item = Challenge(
            nonce=secrets.token_urlsafe(24),
            address=address,
            purpose=purpose,
            digest=terms_digest(payload or {}),
            issued_at=now,
            expires_at=now + CHALLENGE_SECONDS,
        )
        self._challenges[item.nonce] = item
        return item

    def _prune(self, now: float) -> None:
        stale = [n for n, c in self._challenges.items() if c.expires_at < now]
        for nonce in stale:
            self._challenges.pop(nonce, None)

    # -- verification -----------------------------------------------------

    def verify(
        self, nonce: str, signature: str, *,
        purpose: str, address: str, payload: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> Challenge:
        """Check a signature over a challenge, and spend the challenge.

        Every field is checked against the challenge the server itself issued,
        so a signature made for one action cannot be presented for another.
        """
        now = time.time() if now is None else now
        item = self._challenges.pop(nonce, None)   # single use, spent on sight
        if item is None:
            raise AuthError("unknown or already used challenge")
        if item.expires_at < now:
            raise AuthError("challenge expired")
        if item.address != address or item.purpose != purpose:
            raise AuthError("challenge does not match this request")
        if item.digest != terms_digest(payload or {}):
            raise AuthError("signed terms do not match the request")

        key = self.keys.get(address)
        if key is None:
            raise AuthError("unknown address")
        try:
            der = _to_der(_unb64(signature))
        except ValueError as error:
            raise AuthError("signature does not verify") from error
        for candidate in [key, *self.signers.get(address, [])]:
            try:
                candidate.verify(der, item.message.encode(), ec.ECDSA(hashes.SHA256()))
                return item
            except InvalidSignature:
                continue
        raise AuthError("signature does not verify")

    # -- read sessions ----------------------------------------------------

    def derived(self, purpose: str) -> bytes:
        """A key for signing something else short-lived, from the same root.

        The service also promises a price for ten minutes, and a promise is only
        as durable as the key it is signed with. This secret is the one thing
        here that already outlives a restart -- the store keeps it and puts it
        back -- so the promise is signed with a key derived from it rather than
        with a second secret nobody arranged to keep.

        Derived, not reused: a key for one purpose must not verify a statement
        made for another, so that a weakness in either cannot be carried across.
        """
        return hmac.new(self._secret, purpose.encode(), hashlib.sha256).digest()

    def issue_session(self, address: str, *, now: float | None = None) -> dict[str, Any]:
        """A bearer token for reading your own position. It cannot spend."""
        now = time.time() if now is None else now
        expires = int(now + SESSION_SECONDS)
        body = f"{address}.{expires}"
        tag = hmac.new(self._secret, body.encode(), hashlib.sha256).digest()[:16]
        return {"token": f"{body}.{_b64(tag)}", "expires_at": expires}

    def session_address(self, token: str, *, now: float | None = None) -> str:
        """The address a token belongs to, or an error. Constant time compare."""
        now = time.time() if now is None else now
        try:
            address, expires, tag = token.rsplit(".", 2)
        except ValueError as error:
            raise AuthError("malformed token") from error
        body = f"{address}.{expires}"
        expected = hmac.new(self._secret, body.encode(), hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(_b64(expected), tag):
            raise AuthError("token does not verify")
        try:
            if int(expires) < now:
                raise AuthError("token expired")
        except ValueError as error:
            raise AuthError("malformed token") from error
        return address
