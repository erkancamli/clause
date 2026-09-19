"""Signing in with an email, a Google account, a passkey or a wallet, via Privy.

Privy runs the sign in: it sends the email code, talks to Google, checks the
wallet's signature, and hands the page a short lived access token. That token
is a JSON Web Token signed with ES256 by Privy. This module checks it, and only
this: signature against Privy's published keys, issuer, audience (this app) and
expiry. What comes out is the person's Privy identifier, ``did:privy:...``.

What the identifier is used for
-------------------------------
Nothing is priced, bought or signed with it. Purchases are still signed by a
key made on the device, exactly as before. The identifier only answers one
question the device key cannot: "is this the same person who bought cover on
another device?" The first device a person signs in with through Privy gives
the account its address; every later device they sign in on is added as a key
allowed to act for that address. So the same email opens the same policies on a
phone and on a laptop.

No secret is needed. Privy's public keys are fetched from the app's JWKS
address and kept for an hour; a key id not seen before triggers one refetch,
at most once a minute, which is how a key rotation in the Privy dashboard is
picked up without a restart. A fixed public key can be set instead.
"""

from __future__ import annotations

import base64
import json
import threading
import time
import urllib.request
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import load_pem_public_key

ISSUER = "privy.io"
JWKS_SECONDS = 3600.0
REFETCH_SECONDS = 60.0
LEEWAY = 30.0
MAX_TOKEN = 16384


class PrivyError(RuntimeError):
    """A token that does not prove what it claims. The message is safe to show."""


def jwks_url(app_id: str) -> str:
    return f"https://auth.privy.io/api/v1/apps/{app_id}/jwks.json"


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Clause/0.1"})
    with urllib.request.urlopen(request, timeout=8.0) as reply:  # noqa: S310
        return reply.read(200_000)


def key_from_jwk(jwk: dict[str, Any]) -> ec.EllipticCurvePublicKey:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise PrivyError("unsupported key")
    x = int.from_bytes(_unb64(jwk["x"]), "big")
    y = int.from_bytes(_unb64(jwk["y"]), "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


class PrivyVerifier:
    def __init__(
        self, app_id: str, *, verification_key: str | None = None,
        fetcher: Callable[[str], bytes] = _fetch,
    ) -> None:
        if not app_id:
            raise ValueError("a Privy app id is required")
        self.app_id = app_id
        self.url = jwks_url(app_id)
        self._fetcher = fetcher
        self._fixed: ec.EllipticCurvePublicKey | None = None
        if verification_key:
            key = load_pem_public_key(verification_key.replace("\\n", "\n").encode())
            if not isinstance(key, ec.EllipticCurvePublicKey):
                raise ValueError("the Privy verification key must be an ES256 public key")
            self._fixed = key
        self._keys: dict[str, ec.EllipticCurvePublicKey] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    # -- keys ---------------------------------------------------------------

    def _refresh(self, now: float) -> None:
        data = json.loads(self._fetcher(self.url))
        keys = {}
        for jwk in data.get("keys", []):
            try:
                keys[str(jwk.get("kid", ""))] = key_from_jwk(jwk)
            except (PrivyError, KeyError, ValueError):
                continue
        if not keys:
            raise PrivyError("Privy published no usable keys")
        self._keys = keys
        self._fetched_at = now

    def _key(self, kid: str, now: float) -> ec.EllipticCurvePublicKey:
        if self._fixed is not None:
            return self._fixed
        with self._lock:
            stale = now - self._fetched_at > JWKS_SECONDS
            unknown = kid not in self._keys and now - self._fetched_at > REFETCH_SECONDS
            if stale or unknown or not self._keys:
                try:
                    self._refresh(now)
                except PrivyError:
                    raise
                except Exception as error:  # the network, not the token
                    if not self._keys:
                        raise PrivyError("Privy's keys could not be read right now") from error
            key = self._keys.get(kid)
            if key is None and len(self._keys) == 1 and not kid:
                key = next(iter(self._keys.values()))
            if key is None:
                raise PrivyError("token signed with an unknown key")
            return key

    # -- tokens -------------------------------------------------------------

    def verify(self, token: str, *, now: float | None = None) -> str:
        """The Privy user id a valid access token belongs to."""
        return self.claims(token, now=now)["sub"]

    def linked_accounts(self, identity_token: str, *, now: float | None = None) -> tuple[str, list[dict[str, Any]]]:
        """The accounts Privy has verified for a user, from an identity token:
        the same signature and checks as an access token, plus the list it
        carries (as JSON text) of e-mail, wallet, X and other accounts."""
        claims = self.claims(identity_token, now=now)
        raw = claims.get("linked_accounts")
        try:
            accounts = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except json.JSONDecodeError as error:
            raise PrivyError("the identity token carries no readable accounts") from error
        if not isinstance(accounts, list):
            raise PrivyError("the identity token carries no readable accounts")
        return claims["sub"], [a for a in accounts if isinstance(a, dict)]

    def claims(self, token: str, *, now: float | None = None) -> dict[str, Any]:
        """The claims of a token Privy signed for this app, once checked."""
        now = time.time() if now is None else now
        if not token or len(token) > MAX_TOKEN or token.count(".") != 2:
            raise PrivyError("not a Privy access token")
        head_b64, body_b64, sig_b64 = token.split(".")
        try:
            header = json.loads(_unb64(head_b64))
            claims = json.loads(_unb64(body_b64))
            signature = _unb64(sig_b64)
        except (ValueError, json.JSONDecodeError) as error:
            raise PrivyError("not a Privy access token") from error
        if header.get("alg") != "ES256" or len(signature) != 64:
            raise PrivyError("not a Privy access token")

        key = self._key(str(header.get("kid", "")), now)
        der = encode_dss_signature(int.from_bytes(signature[:32], "big"),
                                   int.from_bytes(signature[32:], "big"))
        try:
            key.verify(der, f"{head_b64}.{body_b64}".encode(), ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as error:
            raise PrivyError("token signature does not verify") from error

        if claims.get("iss") != ISSUER:
            raise PrivyError("token was not issued by Privy")
        audience = claims.get("aud")
        if audience != self.app_id and not (isinstance(audience, list) and self.app_id in audience):
            raise PrivyError("token was issued for another app")
        if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] + LEEWAY < now:
            raise PrivyError("token expired, sign in again")
        if isinstance(claims.get("iat"), (int, float)) and claims["iat"] - LEEWAY > now:
            raise PrivyError("token issued in the future")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.startswith("did:privy:") or len(subject) > 128:
            raise PrivyError("token names no Privy user")
        return claims


class Accounts:
    """Which address a Privy user acts as. In memory, like the rest of the book."""

    MAX = 100_000

    def __init__(self) -> None:
        self._by_user: dict[str, str] = {}
        self._lock = threading.Lock()

    def claim(self, user: str, device_address: str) -> tuple[str, bool]:
        """The user's account address, and whether this device just created it."""
        with self._lock:
            existing = self._by_user.get(user)
            if existing is not None:
                return existing, False
            if len(self._by_user) >= self.MAX:
                raise PrivyError("too many accounts")
            self._by_user[user] = device_address
            return device_address, True

    def of(self, user: str) -> str | None:
        return self._by_user.get(user)
