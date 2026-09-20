"""The parts of the API that exist to stop things, gathered in one place.

An audit of this service before any of this existed found, in order of severity:
no authentication anywhere, so the address in a request body was simply believed;
demo endpoints that let an anonymous caller settle any policy and silence any
source; a Monte Carlo simulation running on the event loop, so one laptop in a
loop could take the server down; and JSON accepting Infinity straight into the
ledger, which corrupts the pool's accounting permanently in a single request.

Each of those has a counterpart here.

The shape of the thing
----------------------
Reads are open where they are about the protocol and gated where they are about a
person. Writes are never open: they carry a signature over their own terms, so a
captured request cannot be replayed as a different one. Anything that exists only
to make a demonstration work is off unless an operator turns it on, and then it
needs a token.

Nothing in here is clever. Security that depends on being clever is security
nobody can check.
"""

from __future__ import annotations

import logging
import math
import os
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

from fastapi import Header, HTTPException, Request

logger = logging.getLogger("clause.api.security")

# -- bounds -----------------------------------------------------------------
# Every one of these is an input an attacker chooses, and every one of them
# multiplies work somewhere.

MAX_LIMIT = 50_000_000.0        # cover, in the settlement asset
MIN_LIMIT = 1.0
MAX_TERM_DAYS = 3_660.0         # ten years; beyond this a term is not a policy
MIN_TERM_DAYS = 0.5
MAX_SUBJECT_KEYS = 12
MAX_STRING = 64                 # any string inside a subject
MAX_BOOK = 4_000                # open policies; the simulation is O(book)
MAX_STREAM_CLIENTS = 24         # each open stream costs a simulation every tick


class Refused(HTTPException):
    """A refusal the caller is allowed to see the reason for."""

    def __init__(self, status: int, detail: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(status_code=status, detail=detail, headers=headers)


def safe_detail(error: Exception, *, fallback: str) -> str:
    """What an error is allowed to say to a stranger.

    The audit found the pool's exact balance, an arbitrary address's balance and
    the open policy count all leaking through exception text, which together are
    an unauthenticated balance oracle. Internals go to the log; the caller gets
    the fallback.
    """
    logger.info("refused: %s", error)
    return fallback


# -- numbers ----------------------------------------------------------------


def finite(value: float, name: str) -> float:
    """Reject NaN and Infinity, which JSON carries and Python happily accepts.

    ``Field(gt=0)`` does not catch Infinity, because Infinity is greater than
    zero. One deposit of Infinity makes the pool's balance infinite and its share
    price NaN, and no later arithmetic recovers.
    """
    number = float(value)
    if not math.isfinite(number):
        raise Refused(422, f"{name} must be a finite number")
    return number


def bounded(value: float, name: str, low: float, high: float) -> float:
    number = finite(value, name)
    if not low <= number <= high:
        raise Refused(422, f"{name} must be between {low:g} and {high:g}")
    return number


def clean_subject(subject: dict[str, Any]) -> dict[str, Any]:
    """A subject is a small flat record, not an arbitrary document.

    Unbounded strings inside it end up as dictionary keys, as part of a predicate
    that is re-parsed on every registration, and in every stream payload, so they
    are held forever and re-serialised to everyone.
    """
    if not isinstance(subject, dict):
        raise Refused(422, "subject must be an object")
    if not subject:
        raise Refused(422, "subject cannot be empty")
    if len(subject) > MAX_SUBJECT_KEYS:
        raise Refused(422, "subject has too many fields")

    out: dict[str, Any] = {}
    for key, value in subject.items():
        if not isinstance(key, str) or len(key) > MAX_STRING:
            raise Refused(422, "subject field names must be short strings")
        if isinstance(value, bool):
            raise Refused(422, f"{key} must be a number or a string")
        if isinstance(value, (int, float)):
            out[key] = finite(float(value), key)
        elif isinstance(value, str):
            if len(value) > MAX_STRING:
                raise Refused(422, f"{key} is too long")
            out[key] = value
        else:
            raise Refused(422, f"{key} must be a number or a string")
    return out


def clean_terms(terms: dict[str, Any]) -> dict[str, Any]:
    """The terms a signature covers: flat, plus one nested subject.

    Slightly wider than a subject, because what a buyer signs includes the
    subject itself. Still bounded, because it is attacker supplied and it is
    hashed into a challenge that this server then stores.
    """
    if not isinstance(terms, dict):
        raise Refused(422, "terms must be an object")
    if len(terms) > MAX_SUBJECT_KEYS * 2:
        raise Refused(422, "too many terms")
    out: dict[str, Any] = {}
    for key, value in terms.items():
        if not isinstance(key, str) or len(key) > MAX_STRING:
            raise Refused(422, "term names must be short strings")
        if isinstance(value, dict):
            out[key] = clean_subject(value)
        elif isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = finite(float(value), key)
        elif isinstance(value, str):
            if len(value) > MAX_STRING:
                raise Refused(422, f"{key} is too long")
            out[key] = value
        else:
            raise Refused(422, f"{key} is not a value that can be signed")
    return out


# -- rate limiting ----------------------------------------------------------


@dataclass(slots=True)
class Bucket:
    """One caller's recent history, as timestamps."""

    hits: deque[float] = field(default_factory=deque)


class RateLimiter:
    """A fixed window per caller, per class of work.

    Quoting runs a Monte Carlo over the whole book, so it is limited far harder
    than reading a page of blocks. The limiter is in memory and per process,
    which is the right size for one server and is stated rather than pretended
    otherwise: behind several workers, the real limit belongs in nginx.
    """

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], Bucket] = {}
        self._last_sweep = 0.0

    def check(self, caller: str, kind: str, *, limit: int, window: float) -> None:
        now = time.time()
        self._sweep(now)
        bucket = self._buckets.setdefault((caller, kind), Bucket())
        cutoff = now - window
        while bucket.hits and bucket.hits[0] < cutoff:
            bucket.hits.popleft()
        if len(bucket.hits) >= limit:
            wait = int(bucket.hits[0] + window - now) + 1
            # The wait is also in the header a client library reads.
            raise Refused(429, f"too many requests, try again in {wait}s", headers={"Retry-After": str(wait)})
        bucket.hits.append(now)

    def _sweep(self, now: float) -> None:
        """Drop idle callers, so the table cannot be grown from outside."""
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        dead = [
            key for key, bucket in self._buckets.items()
            if not bucket.hits or bucket.hits[-1] < now - 600
        ]
        for key in dead:
            self._buckets.pop(key, None)


def caller_of(request: Request) -> str:
    """Who is asking, as far as we can tell behind a proxy.

    Only the last hop of a forwarded header is trusted, and only when the
    operator has said there is a proxy; otherwise the header is a free way to
    look like a thousand different callers.
    """
    if os.environ.get("CLAUSE_BEHIND_PROXY") == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()[:64]
    client = request.client
    return client.host if client else "unknown"


# -- settings ---------------------------------------------------------------


@dataclass(slots=True)
class Settings:
    """What this deployment allows. Every default is the safe one."""

    # Endpoints that force chain state. Catastrophic in public, necessary in a
    # demonstration, so they are off unless asked for and gated when on.
    demo_endpoints: bool = False
    operator_token: str | None = None
    # Browsers are only allowed to call this from places the operator names.
    allowed_origins: tuple[str, ...] = ()
    # The schema page names every route, including the dangerous ones.
    public_docs: bool = False
    # A funded address on connect makes a demonstration usable and is free money
    # in public.
    faucet: bool = False
    # Stand in companies in every country, clearly marked as not companies,
    # so the protocol can be shown working anywhere without registering each.
    specimens: bool = False
    # Signing in with email, Google, a passkey or a wallet, through Privy. Off
    # unless an app id is set. Both values are public; no secret is needed.
    privy_app_id: str | None = None
    privy_verification_key: str | None = None
    # Buying a home or vehicle policy outright at POST /api/policies, without
    # the issuing company's review of the address, ownership and contract.
    # On for tests and for a protocol run without insurers; off in a
    # deployment unless CLAUSE_DIRECT_BUY=1, so nothing skips the review the
    # site puts every buyer through.
    direct_buy: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(
            o.strip() for o in os.environ.get("CLAUSE_ORIGINS", "").split(",")
            if o.strip()
        )
        token = os.environ.get("CLAUSE_OPERATOR_TOKEN") or None
        demo = os.environ.get("CLAUSE_DEMO") == "1"
        if demo and not token:
            # Refusing to start is the right response: a demo build reachable
            # from the internet without a token is the audit's finding two.
            raise RuntimeError(
                "CLAUSE_DEMO=1 requires CLAUSE_OPERATOR_TOKEN to be set"
            )
        return cls(
            demo_endpoints=demo,
            operator_token=token,
            allowed_origins=origins,
            public_docs=os.environ.get("CLAUSE_PUBLIC_DOCS") == "1",
            faucet=os.environ.get("CLAUSE_FAUCET") == "1",
            specimens=os.environ.get("CLAUSE_SPECIMENS") == "1",
            privy_app_id=os.environ.get("CLAUSE_PRIVY_APP_ID", "").strip() or None,
            privy_verification_key=os.environ.get("CLAUSE_PRIVY_VERIFICATION_KEY", "").strip() or None,
            direct_buy=os.environ.get("CLAUSE_DIRECT_BUY") == "1",
        )

    def require_admin(self, supplied: str | None) -> None:
        """An operator action that a real deployment needs, not a demo lever.

        Separate from require_operator because activating a carrier's licence is
        ordinary business: someone checks a number against a regulator's
        register and marks it checked. It needs the operator's token and not the
        demonstration switch, which turns on endpoints that move the chain by
        hand and has no place in the path of a real approval.
        """
        if not self.operator_token:
            raise Refused(404, "not found")
        if not supplied or not _constant_equal(supplied, self.operator_token):
            raise Refused(401, "not authorised")

    def require_operator(self, supplied: str | None) -> None:
        if not self.demo_endpoints:
            raise Refused(404, "not found")
        if not self.operator_token:
            raise Refused(404, "not found")
        if not supplied or not _constant_equal(supplied, self.operator_token):
            raise Refused(401, "not authorised")


# -- operator sessions ------------------------------------------------------


@dataclass(slots=True)
class Session:
    """One signed in reviewer, for as long as the review takes."""

    token: str
    reviewer: str
    started_at: float
    expires_at: float

    def live(self, *, now: float | None = None) -> bool:
        return self.expires_at > (time.time() if now is None else now)


class Sessions:
    """Short lived sessions minted from the operator token.

    The token that activates a carrier is the most valuable secret this service
    has, and the version of this feature that asked for it on every click meant
    it travelled on every request, sat in a form field on the page, and got
    pasted into a terminal by whoever was reviewing. So it is exchanged once for
    something that expires, and only the thing that expires is used after that.

    Deliberately in memory and not persisted. A restart signs everyone out,
    which is the correct behaviour for the credential that admits companies to
    the registry, and it means there is no session store to steal.
    """

    TTL = 45 * 60.0
    MAX = 16

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def open(self, reviewer: str, *, now: float | None = None) -> Session:
        now = time.time() if now is None else now
        self._sweep(now)
        if len(self._sessions) >= self.MAX:
            # Drop the oldest rather than refusing: a reviewer locked out by
            # sessions they abandoned yesterday would reach for the raw token.
            oldest = min(self._sessions.values(), key=lambda s: s.started_at)
            self._sessions.pop(oldest.token, None)
        session = Session(
            token=secrets.token_urlsafe(32),
            reviewer=reviewer.strip()[:80],
            started_at=now,
            expires_at=now + self.TTL,
        )
        self._sessions[session.token] = session
        return session

    def of(self, token: str | None, *, now: float | None = None) -> Session | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        if not session.live(now=now):
            self._sessions.pop(token, None)
            return None
        return session

    def close(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def _sweep(self, now: float) -> None:
        for token, session in list(self._sessions.items()):
            if not session.live(now=now):
                self._sessions.pop(token, None)


def _constant_equal(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    difference = 0
    for x, y in zip(a, b):
        difference |= ord(x) ^ ord(y)
    return difference == 0


# -- identity ---------------------------------------------------------------


def bearer(authorization: str | None = Header(None)) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()[:512]


def looks_like_address(value: str) -> str:
    """Addresses are checked for shape before they are used as keys anywhere."""
    from ..protocol.address import canonical, is_address
    if not is_address(value):
        raise Refused(422, "malformed address")
    return canonical(value)
