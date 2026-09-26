"""A price promised for ten minutes, carrying its own proof.

The promise is on the screen in words: this price is yours for ten minutes. It
was kept in a dictionary in the process, which meant the promise was only as
durable as the process — and replacing the service is a thing an operator does
on purpose, in the middle of the afternoon, while somebody is part way through
buying. That buyer pressed the button and was told the price had moved.

So the promise is not stored. It is signed and handed to the buyer, and it comes
back with the purchase: the identifier *is* the promise. Anything that can
verify the signature can honour it, whether or not it is the process that made
it, which covers a restart, a replacement, and more than one process behind one
address.

What is signed is the price and the cover it is a price for. Presenting the
token for different cover does not work, because the terms are inside what was
signed; presenting it after ten minutes does not work, because the moment it
expires is too; and making one up does not work, because the signature is over
the whole of it with a key only the service has.

The key is derived from the authenticator's own secret, which the store already
keeps and puts back on a restart -- see Authenticator.derived. That was the one
secret here arranged to outlive the process, and a second one nobody had arranged
to keep would not have outlived anything.

The numbers carried are the ones the pool reads when it writes the policy, and
nothing else. The prose a quote carries -- the notes about the fault beneath the
circle, what doubling the radius would do -- is for the screen that asked for the
quote and is never read again at bind time, so it is not carried and not signed.
A quote rebuilt from a token has no notes; if something ever needs them there,
it must ask for a fresh quote rather than believe an empty list.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

#: What the identifier starts with, and the version of what follows it. A
#: different shape later gets a different prefix, and an old token is then
#: refused rather than misread.
PREFIX = "PQ1"
SECONDS = 600.0

#: The fields carried, in this order. Everything the pool reads from a locked
#: quote when it writes the policy, plus what the pricing object needs to exist.
FIELDS = (
    "premium", "expected_loss", "risk_load", "expense_load", "marginal_capital",
    "trigger_probability", "expected_share", "standalone_capital",
    "diversification_ratio", "capital_cost",
)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def fingerprint(peril: str, subject: dict[str, Any], limit: float, term_days: float) -> str:
    """The cover a price is a price for, as one short string.

    Sixteen bytes of it. The whole token is signed, so this only has to be too
    narrow to collide by accident; nobody can go looking for a collision without
    the key.
    """
    terms = json.dumps([peril, subject, round(float(limit), 2), round(float(term_days), 4)],
                       sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(terms.encode()).hexdigest()[:32]


def issue(secret: bytes, *, peril: str, subject: dict[str, Any], limit: float,
          term_days: float, quoted: Any, now: float | None = None,
          seconds: float = SECONDS) -> dict[str, Any]:
    """The promise, as an identifier the buyer keeps and hands back."""
    now = time.time() if now is None else now
    expires = now + seconds
    body = [1, fingerprint(peril, subject, limit, term_days), round(expires, 3),
            str(getattr(quoted, "diversification", "") or ""),
            str(getattr(quoted, "risk_basis", "") or ""),
            *[round(float(getattr(quoted, name, 0.0) or 0.0), 6) for name in FIELDS]]
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    tag = hmac.new(secret, payload.encode(), hashlib.sha256).digest()[:16]
    return {"id": f"{PREFIX}.{payload}.{_b64(tag)}",
            "premium": round(float(quoted.premium), 2),
            "expires_at": expires, "seconds": seconds}


def honoured(secret: bytes, token: str | None, *, peril: str, subject: dict[str, Any],
             limit: float, term_days: float, build: Any,
             now: float | None = None) -> Any:
    """The quote this token promises, or None if it promises nothing here.

    `build` is called with the carried numbers and returns the pricing object;
    the caller supplies it so this module does not have to know the pricing
    package, and so a change of shape there is a change in one place.
    """
    now = time.time() if now is None else now
    if not token or not token.startswith(PREFIX + "."):
        return None
    try:
        _prefix, payload, tag = token.split(".", 2)
    except ValueError:
        return None
    expected = hmac.new(secret, payload.encode(), hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(_b64(expected), tag):
        return None
    try:
        body = json.loads(_unb64(payload).decode())
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, list) or len(body) != 5 + len(FIELDS) or body[0] != 1:
        return None
    _version, mark, expires, diversification, basis, *numbers = body
    try:
        if float(expires) < now:
            return None
    except (TypeError, ValueError):
        return None
    if mark != fingerprint(peril, subject, limit, term_days):
        return None
    try:
        carried = {name: float(value) for name, value in zip(FIELDS, numbers)}
    except (TypeError, ValueError):
        return None
    # The cover is not carried in the token, because it is already checked
    # against it above; it is passed on so the rebuilt quote is not one claiming
    # to be a price for nothing.
    return build(peril_key=peril, limit=float(limit), term_days=float(term_days),
                 diversification=str(diversification), risk_basis=str(basis), **carried)
