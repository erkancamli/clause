"""The protocol's read and write API.

Everything the interface shows comes from here as plain JSON, so any figure on
screen can be checked, scripted against or rebuilt by someone else. The pricing
breakdown in particular is returned in full rather than as a single number: a
buyer is entitled to see what they are paying for.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..chain import Chain, ChainConfig
from ..perils import EARTHQUAKE, REGISTRY, get_peril
from ..perils.flight import ROUTES
from ..perils.quake import ALLOWED_RADII_KM, LOCATIONS
from ..perils.weather import STATIONS
from ..pricing import PricingEngine
from ..protocol import (
    Pool,
    PoolError,
    PriceMoved,
    WalletError,
    Wallets,
    derive_address,
)
from ..agent.rider import TOOLS as RIDER_TOOLS, Rider, RiderError
from .privy import Accounts, PrivyError, PrivyVerifier
from ..protocol.valuation import KIND_FOR, ValuationError, schedule, value_of
from ..live import QUIET_DAY, aeroapi_feed, airlabs_feed, flight_feed, quake_feed, quake_week_feed, select_quakes
from ..protocol.auth import AuthError, Authenticator
from ..protocol import kyb
from ..protocol.instalments import part as plan_part, rescheduled
from ..protocol.carrier import (
    Appetite,
    Carrier,
    CarrierError,
    Licence,
    Reach,
    Registry,
    Role,
    Settlement as SettlementAsset,
    specimen_registry,
    add_world_specimens,
    refresh_specimens,
    retire_world_specimens,
)
from ..protocol.compliance import ComplianceEngine, Interest
from ..protocol.pipeline import Action, Match, PolicyError, PolicyPipeline
from ..protocol.documents import OPERATOR as READER_OPERATOR, DocumentError, Documents
from ..protocol.fees import PLATFORM_ACCOUNT, Fees, month_of, platform_share
from ..protocol import desk
from ..protocol import vetting
from ..protocol.mandates import COOLING_OFF_HOURS, MandateError, Mandates, parse_terms
from ..protocol.partners import (
    PARTNER_SCREENED_LIMIT,
    PartnerError,
    Partners,
    beneficiary_address,
)
from ..protocol.payouts import PayoutError, Payouts, rail_from_env
from ..protocol.eligibility import (
    Attestation,
    Claim,
    Eligibility,
    Requirement,
    EligibilityEngine,
    Verifier,
)
from .security import (
    MAX_BOOK,
    MAX_LIMIT,
    MAX_STREAM_CLIENTS,
    MAX_TERM_DAYS,
    MIN_LIMIT,
    MIN_TERM_DAYS,
    RateLimiter,
    Refused,
    Sessions,
    Settings,
    bearer,
    bounded,
    caller_of,
    clean_subject,
    clean_terms,
    finite,
    looks_like_address,
    safe_detail,
)

logger = logging.getLogger("clause.api")

SITE_ROOT = Path(__file__).resolve().parent.parent.parent / "site"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class QuoteRequest(BaseModel):
    peril: str = Field(max_length=32)
    subject: dict[str, Any]
    limit: float
    term_days: float


class InterestDeclaration(BaseModel):
    """What is at risk, where, and what it is worth.

    Not paperwork. This is the difference between insurance and a bet: cover is
    capped by the value declared here, and refused if the thing insured is not
    inside the area the index measures.
    """

    what: str = Field(max_length=120)
    country: str = Field(max_length=2, min_length=2)
    inside_trigger_area: bool
    value_at_risk: float
    professional: bool = False
    # What it is and how big: a home's floor area and type, a field's area and
    # crop, a trip's cost. The protocol works the value out from this and caps
    # cover at it, so a garden cannot buy a farm's cover.
    size: dict[str, Any] | None = None
    # The postal address of a home or where a car is kept: street, number,
    # flat, postcode, city. Seen by the insurer that checks the buyer's
    # interest in it, and by nobody else.
    address: dict[str, str] | None = None


class AttestationBody(BaseModel):
    """One signed statement about an address. No document, one bit per claim."""

    claim: str = Field(max_length=32)
    verifier_id: str = Field(max_length=64)
    issued_at: float
    expires_at: float
    country: str | None = Field(default=None, max_length=2)
    signature: str = Field(max_length=512)


class BuyRequest(QuoteRequest):
    # The buyer is an address, and must prove it holds the key for it.
    holder: str
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)
    interest: InterestDeclaration
    settlement: str = Field(default="stablecoin", max_length=16)
    # Signed statements about this address, held on the buyer's device and
    # presented here. The protocol checks the signatures and stores none of them.
    attestations: list[AttestationBody] = Field(default_factory=list, max_length=8)
    # The most the buyer agreed to pay. The price is struck at bind time against
    # the book as it then stands, so without this a moving book could charge more
    # than the figure they were shown.
    max_premium: float | None = None
    # A price the protocol promised for ten minutes. Within them it is the
    # price, however the book has moved.
    quote_id: str | None = Field(default=None, max_length=40)
    # The company the buyer chose from the offers, if they chose.
    carrier_id: str | None = Field(default=None, max_length=64)
    # The hash of the contract text the buyer read and accepted.
    contract_hash: str | None = Field(default=None, max_length=64)
    # How many instalments the premium is paid in, where that is offered.
    instalments: int = 1


class LicenceBody(BaseModel):
    country: str = Field(max_length=2, min_length=2)
    authority: str = Field(max_length=120)
    reference: str = Field(max_length=64)
    perils: list[str] = Field(max_length=8)
    reach: str = Field(default="retail", max_length=16)
    settlement: list[str] = Field(max_length=2)
    expires_at: float


class EvidenceBody(BaseModel):
    kind: str = Field(default="other", max_length=32)
    filename: str = Field(default="", max_length=120)
    content_type: str = Field(max_length=64)
    data: str = Field(max_length=4_200_000)      # base64 of at most 3 MB


class CarrierRequest(BaseModel):
    """A company asking to be registered. Verified by a human, not by this."""

    name: str = Field(max_length=120)
    lei: str = Field(default="", max_length=20)
    domain: str = Field(default="", max_length=253)
    evidence: list[EvidenceBody] = Field(default_factory=list, max_length=4)
    role: str = Field(max_length=16)
    domicile: str = Field(max_length=2, min_length=2)
    licences: list[LicenceBody] = Field(max_length=24)
    perils: list[str] = Field(max_length=8)
    max_limit: float
    max_term_days: float = 400.0
    capacity: float
    fronting_fee: float = 0.0
    contact: str = Field(default="", max_length=120)
    mersis: str = Field(default="", max_length=16)        # Türkiye: 16 digits
    tax_number: str = Field(default="", max_length=10)    # Türkiye: 10 digits
    excluded_countries: list[str] = Field(default_factory=list, max_length=64)
    # The company signs its own registration, so the row has an owner who can
    # come back and change it.
    address: str | None = None
    nonce: str | None = Field(default=None, max_length=128)
    signature: str | None = Field(default=None, max_length=512)


class SessionRequest(BaseModel):
    """Who is about to review registrations.

    The name is recorded with every decision they take. It is self declared and
    the record says so: one shared token cannot prove which person is holding
    it, and a field that pretended otherwise would be worse than an honest one.
    """

    reviewer: str = Field(default="", max_length=80)


class VettingItem(BaseModel):
    """One item of the operator's checklist, as the reviewer records it."""
    key: str = Field(max_length=32)
    ok: bool | None = None            # confirmed, failed, or not applicable
    source: str = Field(default="", max_length=300)   # where they looked
    note: str = Field(default="", max_length=400)     # what they saw


class ClaimRequest(BaseModel):
    """The holder asks for the token in one of their linked wallets."""
    address: str | None = Field(default=None, max_length=42)


class ComplaintOpen(BaseModel):
    subject: str = Field(default="other", max_length=20)
    text: str = Field(max_length=4000)


class ComplaintMessage(BaseModel):
    text: str = Field(max_length=4000)


class ComplaintClose(BaseModel):
    resolution: str = Field(default="", max_length=1000)


class MoreEvidence(BaseModel):
    evidence: list[EvidenceBody] = Field(min_length=1, max_length=4)


class ReviewRequest(BaseModel):
    """What the reviewer says they checked before letting a company write."""

    note: str = Field(default="", max_length=400)
    # Which of the verification items the reviewer says they confirmed:
    # "lei", "domain", "licence", "evidence".
    checked: list[str] = Field(default_factory=list, max_length=8)


class PolicyCheck(BaseModel):
    """An action described to the policy pipeline, to hear its decision
    without acting. Everything is optional but the stage."""

    stage: str = Field(max_length=16)
    address: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, max_length=2)
    peril: str | None = Field(default=None, max_length=32)
    limit: float | None = None
    amount: float | None = None
    destination: str | None = Field(default=None, max_length=64)
    wallet: str | None = Field(default=None, max_length=64)
    latitude: float | None = None
    longitude: float | None = None


class DenyRequest(BaseModel):
    """A denylist entry: what is refused, and why."""

    match: str = Field(max_length=16)
    value: str = Field(max_length=64)
    reason: str = Field(max_length=300)
    until: float | None = None


class PauseRequest(BaseModel):
    """A moratorium: no new cover on a peril, somewhere, for a while."""

    peril: str = Field(max_length=32)
    reason: str = Field(max_length=300)
    country: str | None = Field(default=None, max_length=2)
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None
    until: float | None = None


class LiftRequest(BaseModel):
    note: str = Field(default="", max_length=300)


class RiderTurn(BaseModel):
    role: str = Field(max_length=16)
    content: str = Field(max_length=4000)


class RiderRequest(BaseModel):
    """What somebody said to Rider, and what was said before it.

    The transcript comes from the browser rather than being held here, because
    a conversation about what a person owns and where they live is exactly the
    kind of thing this protocol has spent its whole design avoiding storing.
    """

    messages: list[RiderTurn] = Field(max_length=24)
    # The language the site is being read in. Checked against a fixed list
    # before it goes anywhere near the model.
    lang: str | None = Field(default=None, max_length=5)
    # A mandate this browser holds, letting Rider buy within its signed limits.
    mandate_token: str | None = Field(default=None, max_length=96)


class RegisterRequest(BaseModel):
    """A device's public key. The address is derived from it, not assigned."""

    public_key: str = Field(max_length=1024)


class ChallengeRequest(BaseModel):
    address: str = Field(max_length=64)
    purpose: str = Field(max_length=16)
    terms: dict[str, Any] | None = None


class VerifyRequest(BaseModel):
    address: str = Field(max_length=64)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


class LinkRequest(BaseModel):
    """A Privy sign in, joined to the device key that will sign purchases."""

    privy_token: str = Field(max_length=4096)
    address: str = Field(max_length=64)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


class PayoutRequest(BaseModel):
    """Where this address's payouts should go. Signed, because it moves money."""

    account: str = Field(max_length=64)
    method: str = Field(max_length=16)
    iban: str | None = Field(default=None, max_length=48)
    holder_name: str | None = Field(default=None, max_length=80)
    provider: str | None = Field(default=None, max_length=24)
    country: str | None = Field(default=None, max_length=2)
    phone: str | None = Field(default=None, max_length=24)
    rialo_address: str | None = Field(default=None, max_length=48)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)

    def terms(self) -> dict[str, Any]:
        out: dict[str, Any] = {"method": self.method}
        for key in ("iban", "holder_name", "provider", "country", "phone", "rialo_address"):
            value = getattr(self, key)
            if value:
                out[key] = value
        return out


class CashoutRequest(BaseModel):
    """Balance leaving for where the payouts go. Signed over the amount."""

    account: str = Field(max_length=64)
    amount: float
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


class WalletLinkStart(BaseModel):
    kind: str = Field(max_length=8)
    address: str = Field(max_length=64)


class WalletLinkRequest(BaseModel):
    """A wallet joined to an account: the device signs the request, the
    wallet signs the text it was given."""

    account: str = Field(max_length=64)
    kind: str = Field(max_length=8)
    address: str = Field(max_length=64)
    wallet_nonce: str = Field(default="", max_length=64)
    wallet_signature: str = Field(default="", max_length=256)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


class XLinkRequest(BaseModel):
    identity_token: str = Field(max_length=16384)


class PayoutDecision(BaseModel):
    status: str = Field(max_length=8)
    reference: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=200)


class FundingAsk(BaseModel):
    method: str = Field(max_length=8)
    amount: float
    sender: str | None = Field(default=None, max_length=48)


class FundingDecision(BaseModel):
    status: str = Field(max_length=10)        # received | cancelled
    received: float | None = None
    note: str = Field(default="", max_length=200)


class RailCallback(BaseModel):
    order_id: str = Field(max_length=24)
    status: str = Field(max_length=8)
    reference: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=200)


class PartnerCreate(BaseModel):
    name: str = Field(max_length=80)
    commission: float = 0.0
    perils: list[str] = Field(default_factory=list, max_length=8)
    countries: list[str] = Field(default_factory=list, max_length=64)
    webhook_url: str = Field(default="", max_length=300)
    # Demonstration only: fund the partner's address with pretend money.
    fund: float = 0.0


class Beneficiary(BaseModel):
    """Who the cover belongs to. An address, or where to pay someone who has none."""

    address: str | None = Field(default=None, max_length=64)
    payout: dict[str, Any] | None = None


class PartnerBind(QuoteRequest):
    external_ref: str = Field(min_length=1, max_length=64)
    interest: InterestDeclaration
    beneficiary: Beneficiary
    max_premium: float | None = None
    attestations: list[AttestationBody] = Field(default_factory=list, max_length=8)


class MandateRequest(BaseModel):
    account: str = Field(max_length=64)
    max_premium_per_policy: float
    max_premium_total: float
    max_limit_per_policy: float
    perils: str = Field(max_length=120)
    days: int
    country: str = Field(max_length=2, min_length=2)
    attestations: list[AttestationBody] = Field(default_factory=list, max_length=8)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


class RiderPurchase(QuoteRequest):
    mandate_token: str = Field(max_length=96)
    interest: InterestDeclaration
    max_premium: float | None = None


class ContractRequest(QuoteRequest):
    interest: InterestDeclaration
    carrier_id: str | None = Field(default=None, max_length=64)
    instalments: int = 1
    quote_id: str | None = Field(default=None, max_length=64)
    settlement: str = Field(default="stablecoin", max_length=16)


class InstructionRequest(BaseModel):
    """A standing instruction, signed over its terms by the device key."""

    account: str = Field(max_length=64)
    kind: str = Field(max_length=8)                     # renew | buy
    max_premium: float
    days: int = 365
    # renew: which policy to keep in force; everything else comes from it.
    policy_id: str | None = Field(default=None, max_length=32)
    # buy: the whole purchase, and when.
    peril: str | None = Field(default=None, max_length=32)
    subject: dict[str, Any] | None = None
    limit: float | None = None
    term_days: float | None = None
    interest: InterestDeclaration | None = None
    carrier_id: str | None = Field(default=None, max_length=64)
    instalments: int = 1
    settlement: str = Field(default="stablecoin", max_length=16)
    when: str = Field(default="date", max_length=8)     # date | age
    at: float | None = None
    years: int | None = None
    # Signed statements about the address, checked now and remembered by
    # name, so the purchase on its day does not have to ask for them.
    attestations: list[AttestationBody] = Field(default_factory=list, max_length=8)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


class SpecimenDesk(BaseModel):
    carrier_id: str = Field(min_length=1, max_length=80)
    release: bool = False


class ReadingKey(BaseModel):
    """A P-256 point the deciding party's browser made and never exported."""
    public_key: str = Field(min_length=80, max_length=120)


class SealedDocument(BaseModel):
    """One document, encrypted in the applicant's browser to the reading key;
    see clause.protocol.documents for the envelope."""
    filename: str = Field(default="", max_length=120)
    content_type: str = Field(max_length=40)
    bytes: int = Field(gt=0, le=4_000_000)
    ephemeral: str = Field(min_length=80, max_length=120)
    salt: str = Field(min_length=20, max_length=32)
    iv: str = Field(min_length=14, max_length=24)
    data: str = Field(min_length=1, max_length=5_500_000)


class SealedDocuments(BaseModel):
    documents: list[SealedDocument] = Field(min_length=1, max_length=4)


class ApplicationDecision(BaseModel):
    decision: str = Field(max_length=8)
    note: str = Field(default="", max_length=400)
    # The checks the reviewer confirms they did, by name.
    checked: list[str] = Field(default_factory=list, max_length=8)


class CancelRequest(BaseModel):
    account: str = Field(max_length=64)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


class CapitalRequest(BaseModel):
    account: str = Field(max_length=64)
    amount: float
    # senior, mezzanine or first_loss. Signed with the amount when given, so
    # a captured deposit cannot be moved into a riskier tranche.
    tranche: str | None = Field(default=None, max_length=16)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


class WithdrawRequest(BaseModel):
    account: str = Field(max_length=64)
    shares: float
    tranche: str | None = Field(default=None, max_length=16)
    nonce: str = Field(max_length=128)
    signature: str = Field(max_length=512)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


def create_app(
    *,
    trials: int = 12_000,
    seed: int = 20260917,
    speed: float = 1.0,
    seed_book: bool = True,
    run_chain: bool = True,
    settings: Settings | None = None,
    live_fetcher: Any = None,
    privy_verifier: Any = None,
    store_path: Any = "env",
    geocoder: Any = None,
    anchor_config: Any = None,
    anchor_rpc: Any = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = PricingEngine(trials=trials, seed=seed)
    wallets = Wallets(demo_balance=250_000.0 if settings.faucet else 0.0)
    pool = Pool(engine=engine, wallets=wallets)
    chain = Chain(pool, ChainConfig(seed=seed, speed=speed))
    auth = Authenticator()
    if privy_verifier is None and settings.privy_app_id:
        privy_verifier = PrivyVerifier(settings.privy_app_id,
                                       verification_key=settings.privy_verification_key)
    accounts = Accounts()
    # Prices promised for a while: id -> (terms, quote, expires). In memory,
    # because a promise that outlives a restart by minutes is not worth a file.
    price_locks: dict[str, tuple[str, Any, float]] = {}
    PRICE_LOCK_SECONDS = 600.0

    def lock_terms(peril: str, subject: dict[str, Any], limit: float, term_days: float) -> str:
        return json.dumps([peril, subject, round(limit, 2), round(term_days, 4)], sort_keys=True)

    def promise(peril: str, subject: dict[str, Any], limit: float, term_days: float,
                quoted: Any) -> dict[str, Any]:
        import secrets as _secrets
        now = time.time()
        for key in [k for k, v in price_locks.items() if v[2] < now]:
            price_locks.pop(key, None)
        if len(price_locks) > 20_000:
            price_locks.pop(next(iter(price_locks)))
        lock_id = "PQ-" + _secrets.token_hex(8)
        price_locks[lock_id] = (lock_terms(peril, subject, limit, term_days), quoted, now + PRICE_LOCK_SECONDS)
        return {"id": lock_id, "premium": round(quoted.premium, 2),
                "expires_at": now + PRICE_LOCK_SECONDS, "seconds": PRICE_LOCK_SECONDS}

    def promised(lock_id: str | None, peril: str, subject: dict[str, Any], limit: float,
                 term_days: float) -> Any:
        if not lock_id:
            return None
        found = price_locks.get(lock_id)
        if not found or found[2] < time.time():
            return None
        if found[0] != lock_terms(peril, subject, limit, term_days):
            return None
        return found[1]
    from ..geocode import ATTRIBUTION as OSM_ATTRIBUTION, GeocodeError, Geocoder
    geocoder = geocoder or Geocoder()
    # Where the book is kept between restarts. CLAUSE_STATE_DIR in a
    # deployment; nowhere in a test, which keeps its book in memory.
    from ..store import Keeper, Store, checkpoint, default_path, restore
    path = default_path() if store_path == "env" else store_path
    store = Store(path) if path else None
    keeper = None
    if store is not None:
        keeper = Keeper(store, lambda: checkpoint(
            store, pool=pool, wallets=wallets, chain=chain, registry=registry,
            auth=auth, accounts=accounts, payouts=payouts, partners=partners,
            mandates=mandates, applications=applications, funding=funding,
            links=links, instructions=instructions, assets=assets, pipeline=pipeline,
            documents=documents, fees=fees, anchor=anchor, complaints=complaints,
            papers=papers, counting=counting))
    # The registry is the thing that decides where this protocol operates, so it
    # is constructed once and everything else reads it: the gate, the coverage
    # map, and the company side of the interface.
    # Empty unless this is a demonstration. A deployment starts with nobody
    # registered, which means nothing can be written anywhere until a real
    # company registers and somebody checks its licence. That is the correct
    # and slightly inconvenient starting state; the stand in companies are tied
    # to the same switch as the pretend money, because they are the same kind
    # of pretending and should never be on separately.
    registry = specimen_registry() if settings.faucet else Registry()
    if settings.specimens:
        add_world_specimens(registry)
    rules = ComplianceEngine(registry)
    eligibility = EligibilityEngine()
    _seed_verifiers(eligibility)
    # Rider reaches the protocol the same way anyone else does, over HTTP, so it
    # has no privileged path into the pool and no way to call something that is
    # not an endpoint.
    rider = Rider(api_base=f"http://127.0.0.1:{os.environ.get('CLAUSE_PORT', '8080')}")
    limiter = RateLimiter()
    # Reviewers sign in with the operator token once and work from a session
    # that expires, so the token that admits companies to the registry is not
    # travelling on every click.
    sessions = Sessions()
    # What is happening in the world right now, for the home page. Fetched by
    # this server at most once a minute however many people are looking.
    live_kw = {"fetcher": live_fetcher} if live_fetcher is not None else {}
    quakes_now = quake_feed(**live_kw)
    quakes_week = quake_week_feed(**live_kw)
    flights_now = flight_feed(**live_kw)
    aeroapi_key = os.environ.get("CLAUSE_AEROAPI_KEY", "").strip()
    airlabs_key = os.environ.get("CLAUSE_AIRLABS_KEY", "").strip()
    flights_world = (airlabs_feed(airlabs_key, **live_kw) if airlabs_key
                     else aeroapi_feed(aeroapi_key, **live_kw) if aeroapi_key else None)

    # The pool and the wallets are mutated from three places: request handlers,
    # the arrivals task in a worker thread, and the chain's own thread. None of
    # them held a lock, which is how one balance check and one debit can be
    # interleaved into a double spend. One lock covers every movement of value.
    money = threading.RLock()
    pool.lock = money
    # The chain settles by paying out of the pool, so it takes its own lock and
    # then the pool's; a purchase takes the pool's and then registers on the
    # chain. Two locks taken in opposite orders is a deadlock waiting for the
    # right moment, so they are one lock.
    chain.lock = money
    streams = {"open": 0}

    # Payouts that leave the protocol for a bank or a mobile wallet.
    payouts = Payouts(wallets, rail_from_env(os.environ), lock=money, background=True)
    from ..protocol.funding import Destinations, Funding, FundingError, Watcher
    from ..protocol.links import LinkError, Links
    links = Links()
    funding = Funding(wallets, Destinations.from_env(), lock=money, links=links)
    watcher = Watcher.from_env(funding)
    pool.listeners.append(payouts.route)
    rail_secret = os.environ.get("CLAUSE_OFFRAMP_SECRET", "").strip()
    # Companies selling cover inside their own product, and Rider's mandates.
    partners = Partners(background=True)
    mandates = Mandates()
    from ..protocol.applications import ApplicationError, Applications
    applications = Applications()
    # What applicants send the deciding company, sealed to its reading key;
    # the bytes live beside the book, the protocol never sees them open.
    documents = Documents(store.path.parent if store is not None else None)
    # The platform's fee on each policy, taken from the company's fronting
    # fee, and the statements that account for it.
    fees = Fees()
    from ..protocol.rewards import Rewards
    rewards = Rewards(fees)
    # Complaints: a thread on the policy, the company's clock, the file for the ombudsman.
    from ..protocol.complaints import ComplaintError, Complaints, route_for
    complaints = Complaints()
    # How many, and nothing about who: the only measurement this protocol has.
    from ..protocol.counting import Counting
    counting = Counting()
    # What each buyer was given: the confirmation, the terms, the reminder of
    # the right to withdraw. Kept because there is nowhere to send them.
    from ..protocol.papers import PaperError, Papers
    papers = Papers()
    from ..protocol.instructions import InstructionError, Instructions
    instructions = Instructions()
    from ..protocol.assets import AssetError, Assets
    assets = Assets()
    # The operator's policy: what is refused whatever else is proved, and
    # where nothing new is being written. Asked at every stage that moves
    # value, and answered without acting at /api/policy/check.
    pipeline = PolicyPipeline()
    # Rider's purchase path needs a key that only the Latch holds; this server
    # keeps its hash. Unset, Rider cannot buy at all.
    rider_key_hash = os.environ.get("CLAUSE_RIDER_PURCHASE_KEY_SHA256", "").strip().lower()

    def tell_partner(settlement: Any) -> None:
        policy = pool.policies.get(settlement.policy_id)
        meta = (policy.metadata or {}) if policy is not None else {}
        partner = partners.partners.get(meta.get("partner", ""))
        if partner is None:
            return
        partners.notify(partner, {
            "type": "policy.settled", "policy_id": settlement.policy_id,
            "external_ref": meta.get("external_ref"), "outcome": settlement.kind,
            "index_value": settlement.index_value, "amount": round(settlement.amount, 2),
            "block": settlement.block_number, "at": settlement.at,
        })

    chain.listeners.append(tell_partner)

    def guard(request: Request, kind: str, *, limit: int, window: float = 60.0) -> None:
        limiter.check(caller_of(request), kind, limit=limit, window=window)

    def signed(
        address: str, purpose: str, nonce: str, signature: str,
        terms: dict[str, Any] | None = None,
    ) -> str:
        """Every movement of value is authorised by its own signature."""
        address = looks_like_address(address)
        try:
            auth.verify(
                nonce, signature, purpose=purpose, address=address, payload=terms,
            )
        except AuthError as error:
            raise Refused(401, safe_detail(error, fallback="not authorised")) from error
        return address

    def reviewer_of(operator: str | None, session_token: str | None) -> str:
        """Who is taking this decision, by session or by raw token.

        Both are accepted because both are real: a person reviewing in a browser
        has a session, and a deployment script or a first activation before
        anyone has signed in has only the token. Either way the caller proved
        they hold the operator secret; the difference is how long ago.
        """
        session = sessions.of(session_token)
        if session is not None:
            return session.reviewer or "operator"
        settings.require_admin(operator)
        return "operator"

    def session_of(token: str | None) -> str | None:
        if not token:
            return None
        try:
            return auth.session_address(token)
        except AuthError:
            return None

    # A public chain as witness. Each token minted or burned, each settlement
    # and, on a timer, the root of the book go out to it as signed
    # transactions when a key is configured; without one they are recorded
    # here, marked as not sent, and the proof page still works.
    from ..anchor import Anchor, AnchorConfig
    from ..anchor.signing import checksum as checksum_evm

    def synthetic_policy(policy: Any) -> bool:
        """The demonstration's own policy, marked or recognised by its holder;
        or, in a book from before the marker and the address migration, a
        policy with nobody behind it: no device key, no Privy account, no
        linked wallet, not bound by a partner for a customer."""
        if is_synthetic(policy):
            return True
        meta = policy.metadata or {}
        if meta.get("partner") or meta.get("synthetic") is False:
            return False
        holder = policy.holder
        if holder in auth.keys or holder in accounts._by_user.values():
            return False
        try:
            if links.mine(holder):
                return False
        except Exception:
            pass
        return True

    anchor = Anchor(anchor_config or AnchorConfig.from_env(), pool=pool, links=links, rpc=anchor_rpc,
                    synthetic=synthetic_policy)
    chain.token_listeners.append(anchor.on_token)
    chain.listeners.append(anchor.on_settlement)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        restored = False
        if store is not None and not store.empty():
            counts = restore(store, pool=pool, wallets=wallets, chain=chain,
                             registry=registry, auth=auth, accounts=accounts,
                             payouts=payouts, partners=partners, mandates=mandates,
                             applications=applications, funding=funding,
                             links=links, instructions=instructions, assets=assets,
                             pipeline=pipeline, documents=documents, fees=fees, anchor=anchor, complaints=complaints,
                             papers=papers, counting=counting)
            restored = True
            logger.info("book restored from %s: %s", store.path, counts)
            # Stand ins saved by an earlier build know only that build's
            # perils; a real company's licence is left exactly as registered.
            refreshed = refresh_specimens(registry)
            if refreshed:
                logger.info("brought %s stand in companies' licences up to this build", refreshed)
            # Tokens of policies cancelled by an earlier build, which kept
            # them in the wallet, are burned now, as a cancellation burns
            # them today.
            burned = 0
            for policy in list(pool.policies.values()):
                token = (policy.metadata or {}).get("token")
                if policy.status.value == "cancelled" and token and not token.get("burned_at"):
                    chain.withdraw(policy)
                    burned += 1
            if burned:
                logger.info("burned the tokens of %s policies cancelled before burning existed", burned)
            if settings.specimens:
                # A book saved before the stand ins existed gets them now; one
                # saved after keeps its own, including any a reviewer suspended.
                added = add_world_specimens(registry)
                if added:
                    logger.info("added %s stand in companies", added)
            else:
                retired = retire_world_specimens(registry)
                if retired:
                    logger.info("suspended %s stand in companies", retired)
        if seed_book and not restored:
            _seed(pool, chain, wallets, registry)
        if keeper is not None:
            keeper.save()
            keeper.start()
        if run_chain:
            chain.start()
            logger.info("chain producing blocks from height %s", chain.height)
        # The anchor's first cycle (tokens owed from before, the first root)
        # runs on its own thread: a big book takes seconds to hash and the
        # service must answer its health check before that.
        if run_chain:
            anchor.start()

        # Buyers keep arriving. Without this the book drains as policies settle
        # and the protocol ends up demonstrating an empty pool.
        arrivals = (
            asyncio.create_task(
                _arrivals(pool, chain, wallets, app.state.declined, registry)
            )
            if run_chain else None
        )
        async def resend() -> None:
            # Payout orders a partner's rail did not take, webhooks a partner
            # did not answer: tried again, with a back off, until they land.
            while True:
                await asyncio.sleep(30)
                try:
                    await run_in_threadpool(payouts.retry)
                    await run_in_threadpool(partners.retry)
                    await run_in_threadpool(lapse_overdue)
                    await run_in_threadpool(collect_due)
                    await run_in_threadpool(app.state.forget_demo_book)
                    await run_in_threadpool(funding.expire)
                    # What a policy earned is a fact once its term is over,
                    # so it is credited then rather than promised before.
                    await run_in_threadpool(rewards.sweep, list(pool.policies.values()))
                    if watcher.active:
                        await run_in_threadpool(watcher.run)
                    await run_instructions()
                except Exception:  # never let a retry loop die quietly
                    logger.exception("retry loop failed")

        resender = asyncio.create_task(resend()) if run_chain else None
        try:
            yield
        finally:
            if resender is not None:
                resender.cancel()
            if arrivals is not None:
                arrivals.cancel()
                try:
                    await arrivals
                except asyncio.CancelledError:
                    pass
            chain.stop()
            anchor.stop()
            if keeper is not None:
                keeper.stop()

    app = FastAPI(
        title="Clause",
        summary="Parametric cover that settles itself, on Rialo",
        version=__version__,
        docs_url="/api/docs" if settings.public_docs else None,
        openapi_url="/api/openapi.json" if settings.public_docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    @app.middleware("http")
    async def harden(request: Request, call_next):
        """The headers a browser needs from an API that answers with personal
        data (ASVS V14.4). Everything under /api is a fresh answer about one
        person's cover or money, so no cache anywhere may keep it; nothing here
        is a page, so nothing here may run a script or be framed. nginx says
        the same in production; the application says it itself so a deployment
        without nginx is no less careful, and the two copies are identical so
        they add up to one policy."""
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("x-content-type-options", "nosniff")
        headers.setdefault("referrer-policy", "strict-origin-when-cross-origin")
        headers.setdefault("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        headers.setdefault("x-frame-options", "DENY")
        path = request.url.path
        if path.startswith("/api/") and not path.startswith("/api/docs"):
            headers.setdefault("cache-control", "no-store")
            headers.setdefault("content-security-policy", "default-src 'none'; frame-ancestors 'none'")
        return response

    if keeper is not None:
        @app.middleware("http")
        async def keep_what_changed(request: Request, call_next):
            """Anything that changed the book is on disk before the answer is."""
            response = await call_next(request)
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 400:
                await run_in_threadpool(keeper.save)
            return response

    @app.exception_handler(RequestValidationError)
    async def malformed(request: Request, error: RequestValidationError) -> Response:
        """A body the route could not read. Answered the way FastAPI answers
        it, and logged, because a page that sent a shape this build does not
        expect is a fault somebody has to find, and the person in front of it
        sees only that they were refused."""
        from fastapi.exception_handlers import request_validation_exception_handler

        where = "; ".join(
            ".".join(str(part) for part in e.get("loc", ())) + ": " + str(e.get("msg", ""))
            for e in error.errors()[:6]
        )
        logger.warning("malformed %s %s: %s", request.method, request.url.path, where)
        return await request_validation_exception_handler(request, error)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> Response:
        """A failure the code did not foresee, answered as JSON the page can
        read. The default answer is plain text from outside the CORS layer,
        so a browser on another origin is not even allowed to see it and the
        page can only say "refused"; the traceback is in the log under a
        reference the person can quote."""
        import secrets as _secrets

        reference = "ERR-" + _secrets.token_hex(4).upper()
        logger.exception("unexpected error %s on %s %s", reference, request.method, request.url.path)
        headers = {}
        origin = request.headers.get("origin", "")
        if origin and origin in settings.allowed_origins:
            headers["access-control-allow-origin"] = origin
            headers["vary"] = "Origin"
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"detail": f"the protocol hit an error it did not expect; nothing was charged "
                       f"(reference {reference}, in the server log)"},
            status_code=500, headers=headers,
        )

    # Everything this service sends is text: JSON, and, for a developer
    # running it alone, the page itself. The page is 660 KB of it, which on a
    # phone on a slow connection is three and a half seconds of waiting before
    # the first word can be drawn. Compressed it is a fifth of that. Pictures
    # and the event stream are excluded by the middleware's own defaults, so
    # nothing that is already packed is packed twice and no event is held back.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    if settings.allowed_origins:
        # Named origins only. A wildcard here, with every write being a POST,
        # would let any page on the internet act through a visitor's browser.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=False,
            # DELETE is here for one thing only: signing a reviewer out.
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["content-type", "authorization", "x-operator-token", "x-clause-key"],
            max_age=600,
        )
    app.state.pool = pool
    app.state.instructions = instructions
    _CARRIER_NAMES.update({c.carrier_id: c.name for c in registry.carriers.values()})
    global _SITE_ORIGIN
    _SITE_ORIGIN = settings.allowed_origins[0].rstrip("/") if settings.allowed_origins else ""

    def place_of(peril: str, subject: dict[str, Any]) -> tuple[float | None, float | None]:
        """Where the insured thing is, for a rule that names a circle."""
        try:
            resolved = get_peril(peril).validate_subject(subject)
        except (KeyError, ValueError):
            resolved = subject
        try:
            if "latitude" in resolved and "longitude" in resolved:
                return float(resolved["latitude"]), float(resolved["longitude"])
        except (TypeError, ValueError):
            pass
        return None, None

    def refused_by_policy(decision: Any) -> HTTPException:
        """The refusal the pipeline wrote, in the shape the compliance gate
        uses, so a page or an agent reads both the same way."""
        return HTTPException(451, {"reasons": list(decision.reasons), "policy": decision.to_dict()})

    def recheck_before_payout(policy_: Any) -> str | None:
        """The operator's policy and the compliance ruling again, on the
        book and the registry as they stand now."""
        meta = policy_.metadata or {}
        interest_ = meta.get("interest") or {}
        countries_ = tuple(c for c in (str(interest_.get("country") or "").upper(),
                                       str(interest_.get("resident") or "").upper()) if c)
        latitude_, longitude_ = place_of(policy_.peril_key, policy_.subject)
        verdict_ = pipeline.check(Action(
            stage="settlement", address=policy_.holder, countries=countries_, peril=policy_.peril_key,
            amount=policy_.limit, latitude=latitude_, longitude=longitude_,
        ))
        if not verdict_.allowed:
            return "; ".join(verdict_.reasons)
        if not interest_:
            return None                      # the demonstration book carries no declaration
        try:
            declared_ = Interest(
                what=str(interest_.get("what", "")), country=str(interest_.get("country", "")).upper(),
                inside_trigger_area=True, value_at_risk=float(interest_.get("value_at_risk") or policy_.limit),
                holder_is_professional=bool(interest_.get("professional", False)),
            )
            ruling_ = rules.recheck_at_settlement(
                interest=declared_, limit=policy_.limit, peril=policy_.peril_key,
                term_days=policy_.term_days, carrier_id=meta.get("carrier"),
            )
        except Exception as error:
            return f"could not be re-evaluated: {error}"
        if ruling_.allowed:
            return None
        return "; ".join(ruling_.reasons) or "no longer lawful where it was written"

    chain.settlement_check = recheck_before_payout
    # Money leaving for a bank, a mobile wallet or another chain asks the
    # same policy about the destination; a refused payout stays at the address.
    payouts.gate = lambda account_, destination_, amount_: pipeline.refusal(Action(
        stage="cashout", address=account_, destination=destination_, amount=amount_))
    app.state.pipeline = pipeline
    app.state.documents = documents
    app.state.fees = fees
    app.state.rewards = rewards
    app.state.anchor = anchor
    app.state.complaints = complaints
    app.state.papers = papers
    app.state.counting = counting
    app.state.chain = chain
    app.state.engine = engine
    app.state.wallets = wallets
    app.state.accounts = accounts
    app.state.auth = auth
    app.state.settings = settings
    app.state.rules = rules
    # Arrivals the pool turned away. A protocol that only shows what it wrote
    # is hiding the half of underwriting that matters.
    app.state.declined: list[dict[str, Any]] = []

    # -- catalogue --------------------------------------------------------

    @app.get("/api/perils")
    async def perils() -> dict[str, Any]:
        """What is on offer, and the honest description of each."""
        out = []
        for key, peril in REGISTRY.items():
            curve = peril.default_curve()
            out.append(
                {
                    **peril.to_dict(),
                    "structure": curve.describe(peril.unit),
                    "direction": curve.direction.value,
                    "shape": curve.shape.value,
                    "attachment": curve.attachment,
                    "exhaustion": curve.exhaustion,
                }
            )
        return {
            "perils": out,
            "routes": [
                {
                    "key": key,
                    "carrier": stats.carrier,
                    "origin": stats.origin,
                    "destination": stats.destination,
                    "late_rate": stats.late_rate,
                    "cancellation_rate": stats.cancellation_rate,
                    "median_late_minutes": stats.median_late_minutes,
                }
                for key, stats in ROUTES.items()
            ],
            "stations": [
                {
                    "code": code,
                    "name": station.name,
                    "region": station.region,
                    "season": station.season,
                    "window_days": station.window_days,
                    "normal_mm": station.normal_mm,
                    "variability": station.variability,
                }
                for code, station in STATIONS.items()
            ],
            "locations": [
                {
                    "code": code,
                    "name": place.name,
                    "zone": place.zone,
                    "has_fault": place.characteristic_magnitude is not None,
                    "characteristic_magnitude": place.characteristic_magnitude,
                    "fault_distance_km": place.fault_distance_km,
                }
                for code, place in LOCATIONS.items()
            ],
            "radii": list(ALLOWED_RADII_KM),
        }

    @app.get("/api/places")
    async def places(
        query: str | None = Query(None, max_length=64),
        country: str | None = Query(None, min_length=2, max_length=2),
    ) -> dict[str, Any]:
        """Names to coordinates, so a buyer never has to know their own.

        The hazard model works on a point. This index exists only so a person
        can type "Kadıköy" or "Tokyo" instead of a coordinate; nothing in the
        pricing depends on a place being in it. Without a query it returns the
        Turkish list the page has always started from; with one it searches
        every country a model was built for, and says of each result whether
        cover can be priced there.
        """
        from ..hazard.model import places as world_places
        from ..perils.places import PLACES, search_world

        if not query:
            return {"places": [{**place.to_dict(), "country": "TR", "priced": True} for place in PLACES],
                    "count": len(PLACES)}
        found = search_world(query, limit=12, country=country.upper() if country else None)
        return {"places": found, "count": len(found),
                "attribution": world_places().get("attribution", "")}

    @app.get("/api/geocode")
    async def geocode(
        http: Request,
        q: str = Query(..., min_length=1, max_length=120),
        lang: str = Query("", max_length=5),
        lat: float | None = Query(None, ge=-90, le=90),
        lon: float | None = Query(None, ge=-180, le=180),
    ) -> dict[str, Any]:
        """An address, a street or a neighbourhood, anywhere, from OpenStreetMap."""
        guard(http, "geocode", limit=40, window=60.0)
        near = (lat, lon) if lat is not None and lon is not None else None
        try:
            places = await run_in_threadpool(
                lambda: geocoder.search(q, lang=lang.lower()[:2], near=near))
        except GeocodeError as error:
            raise Refused(503, str(error)) from error
        return {"places": places, "attribution": OSM_ATTRIBUTION}

    @app.get("/api/reverse")
    async def reverse_geocode(
        http: Request,
        latitude: float = Query(..., ge=-90, le=90),
        longitude: float = Query(..., ge=-180, le=180),
        lang: str = Query("", max_length=5),
    ) -> dict[str, Any]:
        """The place a browser's location falls in, named."""
        guard(http, "geocode", limit=40, window=60.0)
        try:
            place = await run_in_threadpool(
                lambda: geocoder.reverse(latitude, longitude, lang=lang.lower()[:2]))
        except GeocodeError as error:
            raise Refused(503, str(error)) from error
        return {"place": place, "attribution": OSM_ATTRIBUTION}

    @app.get("/api/hazard")
    async def hazard(
        location: str | None = Query(None, max_length=64),
        latitude: float | None = Query(None, ge=-90, le=90),
        longitude: float | None = Query(None, ge=-180, le=180),
        radius_km: float = Query(50.0),
    ) -> dict[str, Any]:
        """The hazard curve behind an earthquake quote, for a place or a point.

        For a point priced by a country's catalogue model the reply also carries
        what the page needs to price every radius itself without asking again:
        the rate at the reference magnitude inside 25, 50 and 100 km, and the
        curve that scales it. The page and the protocol then compute the same
        number from the same inputs.
        """
        if latitude is not None and longitude is not None:
            raw: dict[str, Any] = {"latitude": latitude, "longitude": longitude, "radius_km": radius_km}
        elif location:
            raw = {"location": location, "radius_km": radius_km}
        else:
            raise HTTPException(400, "give a location, or a latitude and a longitude")
        try:
            subject = EARTHQUAKE.validate_subject(raw)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

        grid = EARTHQUAKE.grid_model(subject)
        from ..perils import shaking as sh
        probability = sh.exceedance(subject, 365.25)
        shaking = {
            "levels": list(sh.LEVELS),
            "annual_probability": [round(probability(x), 6) for x in sh.LEVELS],
            "equation": "Allen, Wald and Worden (2012), global, sigma 0.7",
        }
        rows = EARTHQUAKE.hazard_table(subject)
        reply: dict[str, Any] = {
            "subject": subject,
            "country": EARTHQUAKE.risk_country(subject),
            "model": grid.code if grid is not None else "TR-faults",
            "note": EARTHQUAKE.radius_note(subject),
            "shaking": shaking,
            "rows": [
                {
                    **row,
                    "return_period_years": (
                        None
                        if row["return_period_years"] == float("inf")
                        else round(row["return_period_years"], 1)
                    ),
                }
                for row in rows
            ],
        }
        if grid is not None:
            lat, lon = subject["latitude"], subject["longitude"]
            radii = {}
            for r in (25, 50, 100):
                radii[str(r)] = {
                    "rate_reference": grid.rate_reference_within(lat, lon, float(r)),
                    "note": EARTHQUAKE.radius_note({**subject, "radius_km": float(r)}),
                }
            reply["grid"] = {
                "country": grid.code, "name": grid.name, "version": grid.version,
                "reference_magnitude": grid.reference, "b_value": grid.b_value,
                "max_magnitude": grid.max_magnitude, "radii": radii,
                "fitted_until": grid.validation.get("fitted_until"),
                "tested_from": grid.validation.get("tested_from"),
            }
        return reply

    @app.get("/api/vehicle")
    async def vehicle_levels(
        latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180),
    ) -> dict[str, Any]:
        """The rainfall a car cover pays on at a place: that place's own 1 in
        10, 25 and 50 year daily totals, and the fit they come from."""
        from ..perils import VEHICLE_FLOOD
        from ..perils.vehicle import model as rain_model, nearest

        try:
            subject = VEHICLE_FLOOD.validate_subject({"latitude": latitude, "longitude": longitude})
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        place, _ = nearest(latitude, longitude)
        return {"subject": subject, "levels": VEHICLE_FLOOD.levels(subject),
                "gumbel": place["gumbel"], "largest_mm": place["largest_mm"],
                "validation": rain_model()["validation"], "basis_risk": VEHICLE_FLOOD.basis_risk}

    @app.get("/api/storm")
    async def storm_levels(
        latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180),
    ) -> dict[str, Any]:
        """The wind a storm cover pays on at a place: that place's own 1 in
        10, 25 and 50 year daily maxima, and the fit they come from."""
        from ..perils import STORM
        from ..perils.storm import model as wind_model, nearest

        if not STORM.territory:
            raise HTTPException(503, "the wind model has not been built on this deployment, so storm "
                                     "cover cannot be priced anywhere yet")
        try:
            subject = STORM.validate_subject({"latitude": latitude, "longitude": longitude})
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        place, _ = nearest(latitude, longitude)
        return {"subject": subject, "levels": STORM.levels(subject),
                "gumbel": place["gumbel"], "largest_kmh": place.get("largest_kmh"),
                "validation": wind_model()["validation"], "basis_risk": STORM.basis_risk}

    @app.get("/api/models")
    async def hazard_models() -> dict[str, Any]:
        """Every earthquake model the protocol holds, passed or failed.

        A failed model is listed with the test it failed, because a country
        that is not sold should say why rather than simply be missing.
        """
        from ..hazard.model import models as all_models

        cards = []
        for code, model in sorted(all_models().items()):
            card = model.card()
            cards.append({
                "country": code, "name": model.name, "version": model.version,
                "passed": model.passed, "priced_by": (
                    "fault model" if code == "TR" else ("this model" if model.passed else "nothing yet")
                ),
                "failed": model.validation.get("failed", []),
                "rate_m5_per_year": card.get("rate_m5_per_year"),
                "b_value": model.b_value,
            })
        return {"models": cards, "territory": sorted(EARTHQUAKE.territory)}

    @app.get("/api/models/{code}")
    async def hazard_model(code: str) -> dict[str, Any]:
        """One model's full card: method, record, every backtest number, sources."""
        from ..hazard.model import models as all_models

        model = all_models().get(code.upper())
        if model is None:
            raise HTTPException(404, f"no earthquake model for {code.upper()!r}")
        return model.card()

    # -- quoting and buying -----------------------------------------------

    def clean_address(address: dict[str, Any] | None) -> dict[str, str] | None:
        if not address:
            return None
        out = {}
        for key in ("street", "number", "flat", "postcode", "city"):
            value = " ".join(str(address.get(key, "") or "").split())[:80]
            if value:
                out[key] = value
        return out or None

    def contract_for(*, peril_key: str, subject: dict[str, Any], limit: float, term_days: float,
                     premium: float, carrier_id: str | None, holder: str, country: str,
                     instalments: int, address: dict[str, str] | None, value_basis: str = "",
                     starts_at: float | None = None) -> tuple[str, str, dict[str, Any] | None]:
        from ..protocol import contract as contract_mod
        from ..protocol.cancellation import UNFORESEEABLE, cooling_off_for
        from ..protocol.instalments import build as build_plan
        peril = get_peril(peril_key)
        subject = peril.validate_subject(subject)
        rule = cooling_off_for(country)
        fee = fronting_fee_of(carrier_id, premium)
        carrier = registry.carriers.get(carrier_id or "")
        licence = None
        if carrier is not None:
            licence = next((l for l in carrier.licences if l.country == (peril.risk_country(subject) or country)), None)                 or (carrier.licences[0] if carrier.licences else None)
        plan = build_plan(country, term_days, instalments, premium, fee,
                          starts_at=starts_at or time.time())
        text = contract_mod.render(
            peril=peril, subject=subject, limit=limit, term_days=term_days, premium=premium, fee=fee,
            carrier={"name": carrier.name, "authority": licence.authority if licence else "",
                     "specimen": carrier.specimen} if carrier else None,
            holder=holder, country=country,
            cancellation={"cooling_off_days": rule.days if term_days > rule.short_cover_days else 0,
                          "short_cover_days": rule.short_cover_days,
                          "law": rule.law, "pro_rata_after": peril_key in UNFORESEEABLE},
            plan=plan, address=address, value_basis=value_basis,
            attestation=chain.aggregator.describe())
        return text, contract_mod.digest(text), plan

    def fronting_fee_of(carrier_id: str | None, premium: float) -> float:
        carrier = registry.carriers.get(carrier_id or "")
        return round(premium * carrier.fronting_fee, 2) if carrier else 0.0

    def charge_fee(policy_: Any, carrier_id: str, payer_: str, *, amount: float | None = None) -> float:
        """The issuing company's fee, on top of the pool's premium, paid to it.

        Called under the money lock, after the premium has been taken. A
        company with an address is paid there; a stand in only keeps a tally.
        With an instalment plan the fee arrives in parts, one with each
        instalment, so ``amount`` is that part; ``fronting_fee`` on the policy
        is the whole fee and ``fee_paid`` what has arrived so far.
        """
        fee = fronting_fee_of(carrier_id, policy_.premium)
        if fee <= 0:
            return 0.0
        part = round(fee if amount is None else max(0.0, min(amount, fee)), 2)
        if part <= 0:
            policy_.metadata.setdefault("fronting_fee", fee)
            return 0.0
        carrier = registry.carriers[carrier_id]
        wallets.debit(payer_, part, policy_.policy_id, kind="fronting_fee")
        # The platform's share comes out of the company's fee, in the same
        # proportion for each part of it, and never out of the premium: the
        # buyer's price is the pool's price.
        platform_total = platform_share(policy_.premium, fee, fees.rate)
        platform_part = min(part, round(part * platform_total / fee, 2)) if fee > 0 else 0.0
        company_part = round(part - platform_part, 2)
        if carrier.address and not carrier.specimen and company_part > 0:
            wallets.credit(carrier.address, company_part, policy_.policy_id, kind="fronting_fee")
        if platform_part > 0:
            wallets.credit(PLATFORM_ACCOUNT, platform_part, policy_.policy_id, kind="platform_fee")
        carrier.fees_earned += company_part
        policy_.metadata["fronting_fee"] = fee
        policy_.metadata["fee_paid"] = round(float(policy_.metadata.get("fee_paid", 0.0)) + part, 2)
        policy_.metadata["platform_fee"] = platform_total
        policy_.metadata["platform_fee_paid"] = round(float(policy_.metadata.get("platform_fee_paid", 0.0)) + platform_part, 2)
        fees.record(carrier_id=carrier_id, policy_id=policy_.policy_id, holder=policy_.holder,
                    kind="fronting_fee", amount=part, premium=policy_.premium)
        fees.record(carrier_id=carrier_id, policy_id=policy_.policy_id, holder=policy_.holder,
                    kind="platform_fee", amount=platform_part, premium=policy_.premium)
        return part

    def return_fee(policy_: Any) -> float:
        """Inside a cooling off period the fee comes back with the premium."""
        meta = policy_.metadata or {}
        fee = float(meta.get("fee_paid", meta.get("fronting_fee", 0.0)))
        if fee <= 0 or meta.get("fee_returned"):
            return 0.0
        carrier = registry.carriers.get(meta.get("carrier", ""))
        # The platform's share goes back too, from the platform's own account.
        platform_paid = round(float(meta.get("platform_fee_paid", 0.0)), 2)
        company_paid = round(fee - platform_paid, 2)
        recovered = company_paid
        if carrier is not None:
            if carrier.address and not carrier.specimen:
                # Only what the company's address can give back comes back;
                # a fee it has already spent is not created out of nothing.
                recovered = min(company_paid, wallets.require(carrier.address).balance)
                if recovered > 0:
                    wallets.debit(carrier.address, recovered, policy_.policy_id, kind="fronting_fee_returned")
            carrier.fees_earned -= recovered
        platform_recovered = 0.0
        if platform_paid > 0:
            platform_recovered = min(platform_paid, wallets.connect(PLATFORM_ACCOUNT, fund=False).balance)
            if platform_recovered > 0:
                wallets.debit(PLATFORM_ACCOUNT, platform_recovered, policy_.policy_id, kind="platform_fee_returned")
        payer = meta.get("paid_by") or policy_.holder
        if recovered + platform_recovered > 0:
            wallets.credit(payer, round(recovered + platform_recovered, 2), policy_.policy_id,
                           kind="fronting_fee_returned")
        if carrier is not None:
            # The gross fee that went back, the way the fee line was gross when it came in.
            fees.record(carrier_id=carrier.carrier_id, policy_id=policy_.policy_id, holder=policy_.holder,
                        kind="fronting_fee_returned", amount=recovered + platform_recovered, premium=policy_.premium)
            fees.record(carrier_id=carrier.carrier_id, policy_id=policy_.policy_id, holder=policy_.holder,
                        kind="platform_fee_returned", amount=platform_recovered, premium=policy_.premium)
        recovered = round(recovered + platform_recovered, 2)
        policy_.metadata["fee_returned"] = recovered
        policy_.metadata["platform_fee_returned"] = round(platform_recovered, 2)
        return recovered

    async def issue(
        *, holder: str, peril: str, subject: dict[str, Any], limit: float,
        term_days: float, declared: InterestDeclaration, size: dict[str, Any] | None,
        value_at_risk: float, settlement: str, attestations: list[AttestationBody],
        max_premium: float | None, payer: str | None = None,
        satisfied: frozenset[str] = frozenset(), metadata: dict[str, Any] | None = None,
        commission_to: str | None = None, commission_to_partner: Any = None,
        quote_id: str | None = None,
        review: bool = False, locked_quote: Any = None,
        carrier_id: str | None = None, paid_now: float | None = None,
        fee_now: float | None = None,
    ) -> tuple[Any, Any, Any]:
        """Everything between a proven buyer and a policy on chain.

        Shared by a person buying for themselves, a partner selling inside its
        own product and Rider buying under a mandate, so each meets exactly
        the same rules: the licence where the risk is, the value worked out
        from the size, the eligibility checks, the pool's capital.
        """

        # Insurable interest and jurisdiction, before anything is written.
        #
        # The licence that matters is the one where the risk is. A flat in
        # Istanbul needs paper licensed in Türkiye whoever owns it, so for a
        # peril tied to a place the place decides and the buyer's declared
        # country is kept only for what is genuinely about the person: which
        # checks they have to pass. For cover that follows a person, a flight,
        # there is no place and their country is the one that governs.
        resident = declared.country.upper()
        try:
            risk_country = get_peril(peril).risk_country(subject) or resident
        except (KeyError, ValueError) as error:
            raise Refused(422, "unknown peril") from error
        # The value at risk is worked out, not taken on trust: from the floor
        # area of a home, the area and crop of a field. The buyer may declare
        # less than that; never more.
        kind = KIND_FOR.get(peril)
        valuation = None
        if kind in ("home", "field", "vehicle") and size is None:
            raise Refused(422, "describe what is at risk: for a home its floor area and type, "
                               "for a field its area and crop; that decides how much cover it can carry")
        if size is not None:
            try:
                valuation = value_of(size, country=risk_country)
            except ValuationError as error:
                raise Refused(422, str(error)) from error
            if kind and valuation.size["kind"] != kind:
                raise Refused(422, "that description does not fit this cover")
            if peril == "drought" and abs(
                float(subject.get("hectares", 0)) - valuation.size["area_ha"]
            ) > 1e-6:
                raise Refused(422, "the field's area must be the area the cover is written on")
            value_at_risk = min(value_at_risk, valuation.value)
        try:
            interest = Interest(
                what=declared.what,
                country=risk_country,
                inside_trigger_area=declared.inside_trigger_area,
                value_at_risk=value_at_risk,
                holder_is_professional=declared.professional,
            )
        except ValueError as error:
            raise Refused(422, str(error)) from error

        # The asset the buyer asked for, or none, which lets the gate pick the
        # one the carrier's licence in their country actually permits.
        asset = (
            SettlementAsset.FIAT if settlement == "fiat"
            else SettlementAsset.STABLECOIN if settlement == "stablecoin"
            else None
        )
        # The operator's policy first: an address that is refused, or a
        # moratorium on this peril here, ends it before any licence is looked
        # up, so the refusal names the rule rather than blaming the registry.
        latitude, longitude = place_of(peril, subject)
        verdict = pipeline.check(Action(
            stage="purchase", address=holder, countries=(risk_country, resident), peril=peril,
            limit=limit, latitude=latitude, longitude=longitude,
        ))
        if not verdict.allowed:
            raise refused_by_policy(verdict)
        with money:
            registry.reconcile(pool.policies.values())
            ruling = rules.evaluate(
                interest=interest, limit=limit, peril=peril,
                term_days=term_days, asset=asset, book_capacity=pool.balance or None,
                carrier_id=carrier_id,
            )
        if not ruling.allowed:
            raise HTTPException(451, {"reasons": list(ruling.reasons),
                                      "compliance": ruling.to_dict()})

        # What this buyer has to prove, and whether they have proved it. The
        # statements are checked and discarded: what is kept is which claims
        # were satisfied and when they expire, because the payout path has to
        # ask the same question again and needs to know what to ask for.
        need = eligibility.requirement(
            limit=limit,
            professional=interest.holder_is_professional,
            country=resident,
        )
        # Claims already vouched for: by a partner's screening under its
        # agreement, or by the statements checked when a mandate was signed.
        if satisfied:
            need = Requirement(tuple(c for c in need.claims if c.value not in satisfied),
                               need.country, need.because)
        if review:
            # An application: everything above has been checked, and what the
            # buyer has to prove is left to the company that will issue it.
            return need, ruling, {"interest": interest, "resident": resident,
                                  "valuation": valuation, "value_at_risk": value_at_risk}
        presented = []
        for body in attestations:
            try:
                presented.append(Attestation(
                    subject=holder, claim=Claim(body.claim),
                    verifier_id=body.verifier_id, issued_at=finite(body.issued_at, "issued_at"),
                    expires_at=finite(body.expires_at, "expires_at"),
                    country=body.country, signature=body.signature,
                ))
            except ValueError as error:
                raise Refused(422, "that is not an attestation this protocol knows") from error
        standing = eligibility.check(
            address=holder, attestations=presented, requirement=need,
        )
        if satisfied and not need.claims:
            standing = Eligibility(True, (), (), (), need)
        if not standing.ok:
            raise HTTPException(451, {
                "reasons": [
                    "before this can be issued you need: "
                    + ", ".join(c.value.replace("_", " ") for c in standing.missing)
                ] + list(standing.reasons),
                "eligibility": standing.to_dict(),
                "compliance": ruling.to_dict(),
            })

        if len(pool.open_policies) >= MAX_BOOK:
            raise Refused(503, "the book is full; no new cover is being written")

        ceiling = (
            bounded(max_premium, "max_premium", 0.0, MAX_LIMIT)
            if max_premium is not None else None
        )

        def work():
            with money:
                locked_ = locked_quote or promised(quote_id, peril, subject, limit, term_days)
                # Premium and fee are two debits; both must be affordable before
                # either is taken, or a buyer who can pay the premium alone
                # would be left with a policy the pool holds and no chain
                # subscription.
                if wallets is not None and locked_ is not None:
                    expected = locked_.premium if paid_now is None else min(locked_.premium, paid_now)
                    fee_expected = fronting_fee_of(ruling.carrier_id, locked_.premium) if ruling.carrier_id else 0.0
                    if fee_now is not None:
                        fee_expected = min(fee_expected, fee_now)
                    if wallets.require(payer or holder).balance + 1e-9 < expected + fee_expected:
                        raise WalletError(
                            f"{expected + fee_expected:,.2f} is needed (premium and issuing fee) and the "
                            f"address holds {wallets.require(payer or holder).balance:,.2f}")
                policy_ = pool.write(
                    peril_key=peril, subject=subject, limit=limit,
                    term_days=term_days, holder=holder, max_premium=ceiling,
                    payer=payer, locked=locked_, paid_now=paid_now,
                )
                policy_.metadata["compliance"] = ruling.to_dict()
                policy_.metadata["interest"] = {
                    "what": interest.what, "country": interest.country,
                    "resident": resident,
                    "value_at_risk": interest.value_at_risk,
                    "size": valuation.size if valuation else None,
                    "basis": valuation.basis if valuation else None,
                    "professional": interest.holder_is_professional,
                }
                # Which claims were satisfied and when they run out. Not the
                # statements themselves, and nothing that identifies anyone.
                policy_.metadata["eligibility"] = {
                    "claims": [c.value for c in need.claims],
                    "expires_at": min(
                        (a.expires_at for a in standing.held), default=None
                    ),
                }
                try:
                    if ruling.carrier_id:
                        policy_.metadata["carrier"] = ruling.carrier_id
                        registry.record(ruling.carrier_id, limit)
                        charge_fee(policy_, ruling.carrier_id, payer or holder, amount=fee_now)
                    if satisfied:
                        policy_.metadata["eligibility"]["vouched"] = sorted(satisfied)
                    for key_, value_ in (metadata or {}).items():
                        policy_.metadata[key_] = value_
                    armed_ = chain.register(policy_)
                    if commission_to:
                        pool.pay_commission(policy_, commission_to, Partners.commission_on(
                            commission_to_partner, policy_.premium, policy_.expense_load))
                except Exception:
                    chain.withdraw(policy_)
                    # Nothing half done: the premium goes back and the policy
                    # is closed, so the book never holds cover nobody can see.
                    pool.cancel(policy_, note="not issued: the fee or the chain registration failed", now=None)
                    if ruling.carrier_id:
                        registry.reconcile(pool.policies.values())
                    raise
            return policy_, armed_

        try:
            policy, armed = await run_in_threadpool(work)
        except WalletError as error:
            raise Refused(402, safe_detail(error, fallback="insufficient balance")) from error
        except PriceMoved as error:
            # The one refusal repeated verbatim. It names the price the buyer was
            # shown and the price now, both of which they are entitled to, and
            # nothing about the book. Anything vaguer would leave a buyer who was
            # not charged unable to tell why.
            raise Refused(409, str(error)) from error
        except PoolError as error:
            raise Refused(409, safe_detail(error, fallback="the pool cannot write this cover")) from error
        except ValueError as error:
            raise Refused(400, safe_detail(error, fallback="that cover cannot be written")) from error

        return policy, armed, ruling


    @app.post("/api/quote")
    async def quote(request: QuoteRequest, http: Request) -> dict[str, Any]:
        """Price a policy against the book the pool holds right now.

        Every call here runs a Monte Carlo over the whole book, several times.
        That is expensive by design and therefore a lever for anyone who wants
        the server down, so it is rate limited and, more importantly, run off
        the event loop: a CPU bound simulation on the loop blocks every other
        request including the live stream.
        """
        guard(http, "quote", limit=20, window=60.0)
        counting.count("priced", request.peril)
        return await price(request)

    async def price(request: QuoteRequest) -> dict[str, Any]:
        """The quote itself, for the route above and for the routes that
        build on it (offers, a partner's quote) without spending the
        public rate limit twice."""
        subject = clean_subject(request.subject)
        limit = bounded(request.limit, "limit", MIN_LIMIT, MAX_LIMIT)
        term_days = bounded(request.term_days, "term_days", MIN_TERM_DAYS, MAX_TERM_DAYS)

        def work() -> tuple[Any, bool, list[str]]:
            # The book is read under the money lock and priced outside it.
            # A quote is seconds of simulation; holding the lock for all of
            # it made every purchase wait behind every visitor's price. The
            # purchase itself prices again, under the lock, against the book
            # as it is then, and refuses if the price moved past what was
            # agreed; so a preview on a snapshot loses nothing.
            with money:
                book, balance = pool.snapshot()
            quoted_ = pool.quote(
                peril_key=request.peril, subject=subject,
                limit=limit, term_days=term_days, book=book,
            )
            allowed_, reasons_ = pool.can_write(
                peril_key=request.peril, subject=subject,
                limit=limit, term_days=term_days, book=book, balance=balance,
            )
            return quoted_, allowed_, reasons_

        try:
            quoted, allowed, reasons = await run_in_threadpool(work)
        except ValueError as error:
            raise Refused(400, safe_detail(error, fallback="that cover cannot be priced")) from error
        except KeyError as error:
            raise Refused(400, "unknown peril or subject") from error

        subject_key = subject
        request = request.model_copy(update={"subject": subject, "limit": limit, "term_days": term_days})
        peril = get_peril(request.peril)
        subject = peril.validate_subject(subject)
        curve = peril.curve_for(subject)

        return {
            **quoted.to_dict(),
            "lock": promise(request.peril, subject_key, limit, term_days, quoted),
            "can_write": allowed,
            "refusal_reasons": reasons,
            "aggregation_rule": chain.aggregator.describe(),
            "subject": subject,
            "subject_text": peril.describe_subject(subject),
            "structure": curve.describe(peril.unit),
            "basis_risk": peril.basis_risk,
            "basis_risk_level": peril.basis_risk_level,
            "data_source": {
                "reference": peril.data_source(subject).reference,
                "publisher": peril.data_source(subject).publisher,
                "resolution": peril.data_source(subject).resolution,
                "deadline_days": peril.data_source(subject).settlement_deadline_days,
                "on_missing_data": peril.data_source(subject).on_missing_data,
            },
            "predicate": peril.predicate(subject, curve, "quote"),
        }

    @app.get("/api/instalments")
    async def instalment_offers(country: str = Query("", max_length=2),
                                term_days: float = Query(365, gt=0, le=MAX_TERM_DAYS)) -> dict[str, Any]:
        """How the premium may be paid where the buyer lives."""
        from ..protocol.instalments import MIN_TERM_DAYS, offers_for
        return {"plans": offers_for(country, term_days), "min_term_days": MIN_TERM_DAYS}

    @app.post("/api/contract")
    async def contract_preview(request: ContractRequest, http: Request) -> dict[str, Any]:
        """The contract a buyer would be signing, in full, and its hash."""
        guard(http, "quote", limit=30, window=60.0)
        subject = clean_subject(request.subject)
        limit = bounded(request.limit, "limit", MIN_LIMIT, MAX_LIMIT)
        term_days = bounded(request.term_days, "term_days", MIN_TERM_DAYS, MAX_TERM_DAYS)
        counting.count("contracted", request.peril)

        def priced():
            held = promised(request.quote_id, request.peril, subject, limit, term_days)
            if held is not None:
                return held
            with money:
                book, _balance = pool.snapshot()
            return pool.quote(peril_key=request.peril, subject=subject, limit=limit, term_days=term_days, book=book)
        try:
            quoted = await run_in_threadpool(priced)
        except (ValueError, KeyError) as error:
            raise Refused(400, safe_detail(error, fallback="that cover cannot be priced")) from error
        # The company and the valuation the application itself would settle
        # on, from the very same path, so the text and the hash match.
        basis, carrier_id = "", request.carrier_id
        size = clean_subject(request.interest.size) if request.interest.size else None
        try:
            _need, ruling, info = await issue(
                holder="", peril=request.peril, subject=subject, limit=limit, term_days=term_days,
                declared=request.interest, size=size,
                value_at_risk=bounded(request.interest.value_at_risk, "value_at_risk", MIN_LIMIT, MAX_LIMIT),
                settlement=request.settlement, attestations=[], max_premium=None, review=True,
                carrier_id=request.carrier_id,
            )
            carrier_id = ruling.carrier_id
            basis = info["valuation"].basis if info["valuation"] else ""
        except (HTTPException, Refused):
            if size:
                try:
                    basis = value_of(size, country=get_peril(request.peril).risk_country(subject)
                                     or request.interest.country).basis
                except (ValuationError, ValueError):
                    basis = ""
        try:
            text, digest_, plan = contract_for(
                peril_key=request.peril, subject=subject, limit=limit, term_days=term_days,
                premium=round(quoted.premium, 2), carrier_id=carrier_id,
                holder="", country=request.interest.country.upper(),
                instalments=request.instalments, address=clean_address(request.interest.address),
                value_basis=basis)
        except ValueError as error:
            raise Refused(422, str(error)) from error
        return {"text": text, "hash": digest_, "plan": plan, "premium": round(quoted.premium, 2)}

    @app.post("/api/offers")
    async def offers(request: QuoteRequest, http: Request,
                     country: str = Query("", max_length=2),
                     professional: bool = Query(False)) -> dict[str, Any]:
        """Every company that could issue this cover, each with its price.

        The pool's premium is the same whoever issues it: the risk is the
        risk. What differs is the company's own fee on top, what it settles
        in, how fast a bank payout arrives, any cooling off beyond the law,
        and whether it is a real company at all. Every one of those is said
        so the buyer can choose.
        """
        from ..protocol.cancellation import cooling_off_for
        guard(http, "quote", limit=20, window=60.0)
        counting.count("offered", request.peril)
        answer = await price(request)
        subject = answer["subject"]
        peril = get_peril(request.peril)
        resident = country.upper() or "TR"
        risk_country = peril.risk_country(subject) or resident
        rule = cooling_off_for(resident)
        with money:
            registry.reconcile(pool.policies.values())
            try:
                interest = Interest(what="offers", country=risk_country, inside_trigger_area=True,
                                    value_at_risk=answer["limit"], holder_is_professional=professional)
            except ValueError as error:
                raise Refused(422, str(error)) from error
            ruling = rules.evaluate(interest=interest, limit=answer["limit"], peril=request.peril,
                                    term_days=answer["term_days"], book_capacity=pool.balance or None)
        placement = ruling.placement
        rows = []
        fastest = min((o.carrier.fiat_payout_days for o in placement.offers), default=None) if placement else None
        for offer in (placement.offers if placement else ()):
            c = offer.carrier
            fee = round(answer["premium"] * c.fronting_fee, 2)
            plus, minus = [], []
            if c.fronting_fee == 0:
                plus.append("no fee of its own on top of the premium")
            elif c.fronting_fee <= 0.05:
                plus.append(f"a low fee: {c.fronting_fee:.1%} of the premium")
            else:
                minus.append(f"a fee of {c.fronting_fee:.1%} of the premium on top")
            assets = {a.value for a in offer.licence.settlement}
            if "stablecoin" in assets:
                plus.append("pays in USDC, to your address, the block it settles")
            if "fiat" in assets:
                (plus if c.fiat_payout_days <= 2 else minus).append(
                    f"a bank payout takes about {c.fiat_payout_days:g} day{'s' if c.fiat_payout_days != 1 else ''}")
            if c.extra_cooling_off_days > 0:
                plus.append(f"{c.extra_cooling_off_days:g} extra days to change your mind, beyond the {rule.days:g} the law gives")
            if offer.licence.expiring():
                minus.append("its licence is due for renewal soon")
            if c.headroom() < answer["limit"] * 3:
                minus.append("nearly full: little room for more cover on its paper")
            if c.specimen:
                minus.append("a stand in, not a real company; nothing here is real cover")
            rows.append({
                "carrier_id": c.carrier_id, "name": c.name, "domicile": c.domicile,
                "authority": offer.licence.authority, "specimen": c.specimen,
                "fronting_fee": c.fronting_fee, "fee": fee, "premium": round(answer["premium"], 2),
                "total": round(answer["premium"] + fee, 2), "settlement": sorted(assets),
                "fiat_payout_days": c.fiat_payout_days, "extra_cooling_off_days": c.extra_cooling_off_days,
                "headroom": round(c.headroom(), 2), "plus": plus, "minus": minus,
                "fastest": fastest is not None and c.fiat_payout_days == fastest,
            })
        rows.sort(key=lambda r: (r["total"], -r["headroom"]))
        for i, row in enumerate(rows):
            row["cheapest"] = i == 0
        return {"offers": rows, "premium": round(answer["premium"], 2), "lock": answer["lock"],
                "reasons": list(ruling.reasons) if not rows else [],
                "cooling_off_days": rule.days if answer["term_days"] > rule.short_cover_days else 0}

    @app.post("/api/policies")
    async def buy(request: BuyRequest, http: Request) -> dict[str, Any]:
        """Bind a policy and register it onchain.

        Three things have to hold before money moves. The buyer must prove they
        hold the key for the address, by signing these exact terms rather than a
        bare "let me in". The cover must be lawful where they are, and capped by
        what they declared at risk. And the pool must be able to carry it.

        The signature covers the terms, so a captured request cannot be replayed
        as a larger policy or a different peril.
        """
        guard(http, "buy", limit=10, window=60.0)
        subject = clean_subject(request.subject)
        limit = bounded(request.limit, "limit", MIN_LIMIT, MAX_LIMIT)
        term_days = bounded(request.term_days, "term_days", MIN_TERM_DAYS, MAX_TERM_DAYS)
        value_at_risk = bounded(
            request.interest.value_at_risk, "value_at_risk", MIN_LIMIT, MAX_LIMIT
        )

        # Normalised the way the challenge normalised it, so the signature
        # over the description checks against the same text.
        size = clean_subject(request.interest.size) if request.interest.size is not None else None
        terms = {
            "peril": request.peril, "limit": limit, "term_days": term_days,
            "subject": subject, "country": request.interest.country.upper(),
            "value_at_risk": value_at_risk,
        }
        if size is not None:
            terms["size"] = size
        if request.carrier_id:
            terms["carrier_id"] = request.carrier_id
        if request.contract_hash:
            # The contract read and accepted is part of what is signed, as on
            # the application path: the signature binds the buyer to that text.
            terms["contract_hash"] = request.contract_hash
        holder = signed(request.holder, "buy", request.nonce, request.signature, terms)
        if KIND_FOR.get(request.peril) in ("home", "vehicle") and not settings.direct_buy:
            # A home or a car is checked by the issuing company first: its
            # address, its ownership, the contract read and accepted. That is
            # the application path; nothing here can skip it.
            raise Refused(409, "cover on a home or a vehicle is applied for, not bought outright: "
                               "use POST /api/applications")
        policy, armed, ruling = await issue(
            holder=holder, peril=request.peril, subject=subject, limit=limit,
            term_days=term_days, declared=request.interest, size=size,
            value_at_risk=value_at_risk, settlement=request.settlement,
            attestations=request.attestations, max_premium=request.max_premium,
            quote_id=request.quote_id, carrier_id=request.carrier_id,
        )
        if request.contract_hash:
            # The contract the buyer read and accepted is written onto the
            # policy, so their own copy can be taken later and the day they
            # were informed is known: the withdrawal period counts from it.
            try:
                # Written exactly as the preview wrote it, so the hash the
                # buyer signed is the hash of the text kept for them.
                basis = ""
                if size:
                    try:
                        basis = value_of(size, country=get_peril(request.peril).risk_country(subject)
                                         or request.interest.country).basis
                    except (ValuationError, ValueError):
                        basis = ""
                text, digest_, _plan = contract_for(
                    peril_key=request.peril, subject=subject, limit=limit, term_days=term_days,
                    premium=round(policy.premium, 2), carrier_id=(policy.metadata or {}).get("carrier"), holder="",
                    country=request.interest.country.upper(), instalments=getattr(request, "instalments", 1) or 1,
                    address=clean_address(request.interest.address), value_basis=basis)
                policy.metadata["contract"] = text
                policy.metadata["contract_hash"] = digest_
                policy.metadata["disclosure"] = {"served_at": policy.bought_at, "hash": digest_,
                                                 "accepted_hash": request.contract_hash}
            except Exception:  # the policy stands; only its copy is missing
                logger.exception("could not write the contract onto %s", policy.policy_id)
        give_papers(holder, policy, (policy.metadata or {}).get("contract", ""),
                    (policy.metadata or {}).get("contract_hash", ""))
        counting.count("bought", request.peril)
        return {
            "policy": policy.to_dict(),
            "account": armed.account,
            "compliance": ruling.to_dict(),
            "wallet": wallets.require(holder).as_dict(),
            "session": auth.issue_session(holder),
        }

    PRIVATE_POLICY_KEYS = ("review_note", "reviewed_by", "address_hash", "interest", "plan",
                           "premium_owed", "written_off", "fee_paid", "financing_paid",
                           "contract", "disclosure", "withdrawal")

    def public_policy(found: Any, *, owner: bool) -> dict[str, Any]:
        """A policy as anyone may see it: the terms, never the person."""
        row = found.to_dict()
        if owner:
            return row
        row["holder"] = None
        row["metadata"] = {k: v for k, v in (row.get("metadata") or {}).items()
                           if k not in PRIVATE_POLICY_KEYS}
        return row

    @app.get("/api/policies")
    async def policies(
        status: str | None = Query(None, max_length=16),
        limit: int = Query(100, ge=1, le=200),
        token: str | None = Depends(bearer),
    ) -> dict[str, Any]:
        """The book, with the holders removed.

        The shape of the book is what makes the capital argument checkable, so
        it stays public. Who holds what does not: the audit found that listing
        holders here and balances elsewhere together made an unauthenticated
        lookup of any address's position. Your own policies come back with your
        address on them, and nobody else's do.
        """
        mine = session_of(token)
        rows = [public_policy(policy, owner=policy.holder == mine) for policy in pool.policies.values()]
        if status:
            rows = [row for row in rows if row["status"] == status]
        rows.sort(key=lambda row: row["bought_at"], reverse=True)
        return {"count": len(rows), "items": rows[:limit]}

    @app.get("/api/policies/{policy_id}/token")
    async def policy_token(policy_id: str) -> dict[str, Any]:
        """The policy's token, in the metadata shape wallets and explorers read.

        Locked: it belongs to the address that bought the cover and cannot be
        moved, so cover can never be sold on to someone with no interest in
        what it insures. The image is a certificate drawn from the terms.
        """
        found = pool.policies.get(policy_id)
        if found is None or "token" not in (found.metadata or {}):
            raise HTTPException(404, f"no token for {policy_id}")
        _CARRIER_NAMES.update({c.carrier_id: c.name for c in registry.carriers.values()})
        return token_metadata(found)

    @app.post("/api/policies/{policy_id}/transfer")
    async def policy_transfer(policy_id: str) -> dict[str, Any]:
        """Always refused. Kept as an endpoint so the refusal is explicit."""
        if policy_id not in pool.policies:
            raise HTTPException(404, f"no policy {policy_id}")
        raise Refused(409, "a policy token cannot be transferred: cover belongs to the "
                           "person with an interest in what it insures")

    @app.get("/api/policies/{policy_id}")
    async def policy(policy_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        found = pool.policies.get(policy_id)
        if found is None:
            raise HTTPException(404, f"no policy {policy_id}")
        settlements = [
            item.to_dict() for item in chain.settlements if item.policy_id == policy_id
        ]
        owner = session_of(token) == found.holder
        return {"policy": public_policy(found, owner=owner), "settlements": settlements}

    # -- identity: proving control of an address ---------------------------

    @app.post("/api/auth/register")
    async def auth_register(request: RegisterRequest, http: Request) -> dict[str, Any]:
        """Record a device's public key and return the address it controls.

        The key is generated on the device and its private half never leaves.
        The address is derived from the public half, so there is no account to
        create, no password to reset and nothing here worth stealing.

        P-256 is required, which is the curve platform authenticators sign with
        and the curve behind Rialo's published secp256r1 program. The same
        signature this server checks is one the chain could check.
        """
        guard(http, "auth", limit=30, window=60.0)
        try:
            address = auth.register(request.public_key)
        except AuthError as error:
            raise Refused(400, safe_detail(error, fallback="that key was not accepted")) from error
        wallets.connect(address, custody="passkey")
        return {"address": address, "wallet": wallets.require(address).as_dict()}

    @app.post("/api/auth/challenge")
    async def auth_challenge(request: ChallengeRequest, http: Request) -> dict[str, Any]:
        """A single use nonce to sign, bound to one address and one action."""
        guard(http, "auth", limit=60, window=60.0)
        address = looks_like_address(request.address)
        terms = clean_terms(request.terms) if request.terms else None
        try:
            challenge = auth.challenge(address, request.purpose, terms)
        except AuthError as error:
            raise Refused(400, safe_detail(error, fallback="cannot issue a challenge")) from error
        return challenge.to_dict()

    @app.post("/api/auth/verify")
    async def auth_verify(request: VerifyRequest, http: Request) -> dict[str, Any]:
        """Check a sign in signature and hand back a read session.

        The session can look at your own position and nothing else. It cannot
        spend: every movement of value carries its own signature over its own
        terms, so a stolen session is a stolen view, not a stolen wallet.
        """
        guard(http, "auth", limit=30, window=60.0)
        address = signed(request.address, "sign-in", request.nonce, request.signature)
        return {
            "address": address,
            "session": auth.issue_session(address),
            "wallet": wallets.require(address).as_dict(),
        }

    @app.get("/api/valuation")
    async def valuation_schedule() -> dict[str, Any]:
        """The figures a value at risk is worked out from, so the page can show
        a buyer the ceiling as they type and the protocol can hold them to it."""
        return schedule()

    @app.get("/api/privy")
    async def privy_config() -> dict[str, Any]:
        """Whether signing in through Privy is on here, and with which app.

        The app id is public: it is what the page gives Privy to say which
        app's sign in to show. Nothing secret is involved on either side.
        """
        if privy_verifier is None:
            return {"enabled": False}
        return {"enabled": True, "app_id": privy_verifier.app_id}

    @app.post("/api/privy/link")
    async def privy_link(request: LinkRequest, http: Request) -> dict[str, Any]:
        """Sign in through Privy, on this device, as the same person everywhere.

        Two proofs, both required. The Privy token proves who the person is
        (their email, Google account, passkey or wallet, as Privy checked it).
        The signature proves this device holds the key it registered. The first
        device a person links gives their account its address; each later one
        is allowed to sign for that same address, so their policies follow
        them. The protocol stores which address a Privy user acts as and
        nothing else: no email, no name.
        """
        if privy_verifier is None:
            raise Refused(404, "not found")
        guard(http, "auth", limit=30, window=60.0)
        try:
            user = await run_in_threadpool(privy_verifier.verify, request.privy_token)
        except PrivyError as error:
            raise Refused(401, str(error)) from error
        device = signed(request.address, "link", request.nonce, request.signature)
        try:
            account, created = accounts.claim(user, device)
            if not created:
                auth.authorize(account, device)
        except (PrivyError, AuthError) as error:
            raise Refused(409, "this account could not be joined on this device; "
                               "sign in again on the device you first used") from error
        wallets.connect(account, custody="passkey")
        return {
            "address": account,
            "device": device,
            "linked": not created,
            "session": auth.issue_session(account),
            "wallet": wallets.require(account).as_dict(),
        }

    @app.get("/api/wallet")
    async def wallet(token: str | None = Depends(bearer)) -> dict[str, Any]:
        """What your address holds. Yours, because the token says which."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        account = wallets.get(address)
        if account is None:
            raise Refused(404, "nothing here yet")
        return {"wallet": account.as_dict()}

    @app.get("/api/portfolio")
    async def portfolio(token: str | None = Depends(bearer)) -> dict[str, Any]:
        """Everything your address holds, assembled the way the chain would.

        On a live chain this is get_subscription for what is armed and
        get_triggered_transactions for what has settled. You can make those
        calls yourself without this interface, which is the point of it.
        """
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        view = wallets.portfolio(address, pool.policies.values())
        mine = [p.to_dict() for p in pool.policies.values() if p.holder == address]
        mine.sort(key=lambda row: row["bought_at"], reverse=True)
        ids = {row["policy_id"] for row in mine}
        settlements = [
            item.to_dict() for item in chain.settlements if item.policy_id in ids
        ]
        return {"portfolio": view, "policies": mine, "settlements": settlements[-40:],
                "faucet": {"on": settings.faucet, "amount": FAUCET_TOP_UP, "ceiling": FAUCET_CEILING}}

    @app.post("/api/wallet/faucet")
    async def faucet(http: Request, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """Demonstration money, on demand, for the address signed in.

        Only where the demonstration switch is on, which is the same switch
        that funds a new address; pretend money and nothing else. Capped, so a
        demo account stays a demo account.
        """
        if not settings.faucet:
            raise Refused(404, "not found")
        guard(http, "faucet", limit=10, window=3600.0)
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        with money:
            account = wallets.connect(address, fund=False)
            room = max(0.0, FAUCET_CEILING - account.balance)
            amount = min(FAUCET_TOP_UP, room)
            if amount <= 0:
                raise Refused(409, "this demonstration balance is already at its ceiling")
            wallets.credit(address, amount, "demonstration top up", kind="faucet")
        return {"added": round(amount, 2), "wallet": wallets.require(address).as_dict()}

    @app.get("/api/lineage/{policy_id}")
    async def lineage(policy_id: str) -> dict[str, Any]:
        """Why a policy paid, or did not, from the chain's own record.

        The question an insurer is normally asked to answer out of its own
        files. Here it is answered from what the chain stored: the subscription,
        every round of validator reports on the topic it listens to, what the
        aggregator concluded about each, and the settlement transaction.
        """
        if not re.fullmatch(r"[A-Za-z0-9-]{1,32}", policy_id):
            raise Refused(422, "malformed policy id")
        story = chain.lineage(policy_id[:32])
        if story is None:
            raise Refused(404, "no such policy")
        return story

    @app.get("/api/rewards")
    async def rewards_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        """What this address has been given back, and what is still earning.

        The programme pays for cover held, out of the platform's own fee and
        never out of the premium or the insurer's pocket. See
        ``clause/protocol/rewards.py`` for why each of those matters.
        """
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        return await run_in_threadpool(
            rewards.mine, address, list(pool.policies.values()))

    @app.get("/api/decided")
    async def decided(limit: int = Query(12, ge=1, le=50)) -> dict[str, Any]:
        """What the chain decided last, paid and not paid, with the figures.

        The companion to /api/lineage: that one answers about a policy you can
        already name, this one says which policies there are to ask about. No
        field here is new — a settlement is a public transaction and any
        policy's lineage already answers to its id — and the holder is left out,
        because no part of the argument needs it.
        """
        stats = chain.stats()
        return {
            "items": chain.recent_decisions(limit),
            "book": {
                "policies": len(pool.policies),
                "evaluated": stats["settlements"],
                "paid": stats["paid"],
                "height": stats["height"],
                "mean_latency_blocks": round(stats["mean_latency_blocks"], 1),
            },
        }

    @app.get("/api/rewards/totals")
    async def rewards_totals() -> dict[str, Any]:
        """The programme's own books: the rule, the budget and what it has
        given back. Public, because a scheme whose size is a secret is one
        nobody can check is solvent."""
        return await run_in_threadpool(rewards.totals)

    @app.get("/api/compliance")
    async def compliance() -> dict[str, Any]:
        """Where cover may be written, assembled from who is registered.

        This used to be a list of countries in the source, which made the
        protocol's reach a property of our documentation. It is now a
        consequence: a country is here because a company licensed to write
        there registered, and it leaves when that licence lapses.
        """
        rows = rules.coverage(include_closed=True)
        open_rows = [row for row in rows if row["open"]]
        summary = registry.summary()
        # The registry counts countries with a licence; the map counts countries
        # where something can actually be bought. Only the second is "open".
        summary["licensed_countries"] = summary.get("countries", 0)
        summary["countries"] = len(open_rows)
        return {
            "coverage": open_rows,
            "waiting": [row for row in rows if not row["open"]],
            "registry": summary,
            "priceable": {
                key: (sorted(t) if t is not None else None)
                for key, t in rules.territories.items()
            },
            "unlisted": (
                "cover can be bought where three things meet: a carrier licensed "
                "there, a reinsurer behind it, and a model that can price the "
                "risk. Where one is missing, the protocol says which rather than "
                "pretending the country does not exist."
            ),
            "eligibility": eligibility.to_dict(),
            "aggregation_rule": chain.aggregator.describe(),
        }

    # -- the operator's policy -------------------------------------------

    @app.get("/api/policy")
    async def policy_describe() -> dict[str, Any]:
        """The pipeline as anyone may read it: the rules in order, what each
        one reads, how many entries are live, and every moratorium in full.
        A buyer is entitled to know that nothing is being written here this
        week; nobody is entitled to the denylist."""
        return pipeline.describe()

    def may_speak_for(address: str | None, *, token: str | None, operator: str | None,
                      key: str | None) -> str | None:
        """Who the check is about. A person may ask about their own address,
        the operator and a partner about any; nobody anonymous about anyone,
        because the answer is one bit about an address and that bit is
        exactly what a denylist must not leak."""
        if operator or sessions.of(token) is not None:
            if sessions.of(token) is None:
                settings.require_admin(operator)
            return address
        if key:
            partner_of(key, None)
            return address
        mine = session_of(token)
        if mine is None:
            raise Refused(401, "sign in first, or present the operator token or a partner key")
        if address and looks_like_address(address) != mine:
            raise Refused(403, "you may ask about your own address only")
        return mine

    @app.post("/api/policy/check")
    async def policy_check(
        request: PolicyCheck, http: Request, token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
        key: str | None = Header(None, alias="x-clause-key"),
    ) -> dict[str, Any]:
        """The decision the real stage would take, without acting.

        Rider asks its Latch for a decision before it acts rather than acting
        and catching the refusal; a page can do the same here before it asks
        a person to sign. Nothing is reserved: the rules run again when the
        action itself arrives, and they may have changed by then.
        """
        guard(http, "policy", limit=60, window=60.0)
        address = may_speak_for(request.address, token=token, operator=operator, key=key)
        try:
            action = Action(
                stage=request.stage, address=address or "",
                countries=tuple(c for c in ((request.country or "").upper(),) if c),
                peril=(request.peril or "")[:32],
                limit=bounded(request.limit, "limit", 0.0, MAX_LIMIT) if request.limit is not None else 0.0,
                amount=bounded(request.amount, "amount", 0.0, MAX_LIMIT) if request.amount is not None else 0.0,
                destination=(request.destination or "").strip(), wallet=(request.wallet or "").strip(),
                latitude=finite(request.latitude, "latitude") if request.latitude is not None else None,
                longitude=finite(request.longitude, "longitude") if request.longitude is not None else None,
            )
        except PolicyError as error:
            raise Refused(422, str(error)) from error
        return pipeline.check(action).to_dict()

    @app.get("/api/operator/policy")
    async def operator_policy(
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Every entry ever written, lifted ones included, and the latest
        decisions: what was refused, when, by which rule."""
        reviewer = reviewer_of(operator, token)
        return {"reviewer": reviewer, **pipeline.book(), "describe": pipeline.describe()}

    @app.post("/api/operator/policy/deny")
    async def operator_deny(
        request: DenyRequest, token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Refuse an address, a wallet, a country or a destination, at every
        stage, until lifted. Who wrote it and why stay on the entry."""
        reviewer = reviewer_of(operator, token)
        try:
            match = Match(request.match)
        except ValueError as error:
            raise Refused(422, "match one of: address, wallet, country, destination") from error
        try:
            entry = pipeline.deny(match=match, value=request.value, reason=request.reason, by=reviewer,
                                  until=finite(request.until, "until") if request.until is not None else None)
        except PolicyError as error:
            raise Refused(422, str(error)) from error
        logger.info("policy: %s refused by %r: %s", request.match, reviewer, entry.entry_id)
        return {"entry": entry.to_dict(private=True)}

    @app.post("/api/operator/policy/pause")
    async def operator_pause(
        request: PauseRequest, token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """No new cover on a peril, in a country or inside a circle, until a
        date or until lifted. Cover already in force is unaffected."""
        reviewer = reviewer_of(operator, token)
        if request.peril != "*" and request.peril not in REGISTRY:
            raise Refused(422, "unknown peril; use * for every peril")
        try:
            entry = pipeline.pause(
                peril=request.peril, reason=request.reason, by=reviewer, country=request.country or "",
                latitude=finite(request.latitude, "latitude") if request.latitude is not None else None,
                longitude=finite(request.longitude, "longitude") if request.longitude is not None else None,
                radius_km=finite(request.radius_km, "radius_km") if request.radius_km is not None else None,
                until=finite(request.until, "until") if request.until is not None else None,
            )
        except PolicyError as error:
            raise Refused(422, str(error)) from error
        logger.info("policy: moratorium on %s by %r: %s", request.peril, reviewer, entry.entry_id)
        return {"entry": entry.to_dict(private=True)}

    @app.post("/api/operator/policy/{entry_id}/lift")
    async def operator_lift(
        entry_id: str, request: LiftRequest | None = None, token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        reviewer = reviewer_of(operator, token)
        try:
            entry = pipeline.lift(entry_id[:16], by=reviewer, note=request.note if request else "")
        except PolicyError as error:
            raise Refused(404, str(error)) from error
        logger.info("policy: %s lifted by %r", entry.entry_id, reviewer)
        return {"entry": entry.to_dict(private=True)}

    @app.get("/api/carriers")
    async def carriers() -> dict[str, Any]:
        with money:
            registry.reconcile(pool.policies.values())
        """The companies behind the cover. Public, because a buyer is entitled
        to know whose paper their policy is on before they buy it."""
        return {
            "companies": [c.to_dict() for c in registry.carriers.values()],
            "summary": registry.summary(),
        }

    @app.get("/api/carriers/documents")
    async def carrier_documents(country: str = Query("", max_length=2),
                                role: str = Query("carrier", max_length=16)) -> dict[str, Any]:
        """What a company in this country is asked to attach, and why.

        Asked by the registration form as soon as a country is chosen, so
        nobody is shown a document their country does not issue.
        """
        from ..protocol import kyb as kyb_mod
        return {"country": (country or "").upper(), "role": role,
                "documents": kyb_mod.documents_for(country, role=role),
                "max_files": kyb_mod.EVIDENCE_MAX_FILES,
                "max_bytes": kyb_mod.EVIDENCE_MAX_BYTES}

    @app.post("/api/carriers")
    async def carrier_register(request: CarrierRequest, http: Request) -> dict[str, Any]:
        """A company asking to be registered.

        It arrives PENDING and can write nothing. Somebody has to check the
        licence number against the regulator's own register and activate it,
        which is a human step on purpose: this protocol cannot read a register
        from inside a block, and a registration that activated itself would mean
        anyone could claim to be an insurer here.
        """
        guard(http, "carrier", limit=5, window=300.0)
        try:
            role = Role(request.role)
        except ValueError as error:
            raise Refused(422, "a company is a carrier or a reinsurer") from error

        licences = []
        for body in request.licences:
            try:
                licences.append(Licence(
                    country=body.country.upper(),
                    authority=body.authority,
                    reference=body.reference,
                    perils=frozenset(p for p in body.perils if p in REGISTRY),
                    reach=Reach(body.reach),
                    settlement=frozenset(
                        SettlementAsset(x) for x in body.settlement
                    ),
                    expires_at=finite(body.expires_at, "expires_at"),
                ))
            except (ValueError, CarrierError) as error:
                raise Refused(422, safe_detail(
                    error, fallback="that licence cannot be recorded as stated"
                )) from error

        mersis = "".join(ch for ch in request.mersis if ch.isdigit())
        tax_number = "".join(ch for ch in request.tax_number if ch.isdigit())
        if request.domicile.upper() == "TR":
            if mersis and len(mersis) != 16:
                raise Refused(422, "a MERSİS number is 16 digits")
            if tax_number and len(tax_number) != 10:
                raise Refused(422, "a vergi kimlik numarası is 10 digits")
        holder = None
        if request.address and request.nonce and request.signature:
            holder = signed(
                request.address, "register", request.nonce, request.signature,
                {"name": request.name, "role": request.role,
                 "domicile": request.domicile.upper()},
            )

        slug = "".join(
            ch if ch.isalnum() else "-" for ch in request.name.lower()
        ).strip("-")[:40] or "company"
        carrier_id = slug
        suffix = 2
        while carrier_id in registry.carriers:
            carrier_id = f"{slug}-{suffix}"
            suffix += 1

        evidence_root = store.path.parent if store is not None else None
        bodies = [e.model_dump() for e in request.evidence]
        try:
            # Checked (type, size, shape) but not yet written: the files land
            # only once the registration itself has been accepted.
            kyb.store_evidence(None, carrier_id, bodies)
        except ValueError as error:
            raise Refused(422, str(error)) from error
        evidence = await run_in_threadpool(kyb.store_evidence, evidence_root, carrier_id, bodies)
        try:
            carrier = registry.register(Carrier(
                carrier_id=carrier_id,
                name=request.name,
                lei=request.lei.strip().upper(),
                domain=request.domain.strip().lower(),
                evidence=evidence,
                role=role,
                domicile=request.domicile.upper(),
                licences=tuple(licences),
                appetite=Appetite(
                    max_limit=bounded(request.max_limit, "max_limit", MIN_LIMIT, MAX_LIMIT),
                    max_term_days=bounded(
                        request.max_term_days, "max_term_days", MIN_TERM_DAYS, MAX_TERM_DAYS
                    ),
                    perils=frozenset(p for p in request.perils if p in REGISTRY),
                    excluded_countries=frozenset(
                        c.upper() for c in request.excluded_countries[:64]
                    ),
                ),
                capacity=bounded(request.capacity, "capacity", MIN_LIMIT, MAX_LIMIT * 200),
                fronting_fee=bounded(request.fronting_fee, "fronting_fee", 0.0, 0.49),
                contact=request.contact,
                mersis=mersis, tax_number=tax_number,
                address=holder,
            ))
        except CarrierError as error:
            for item in evidence:
                if item.get("stored") and evidence_root is not None:
                    try:
                        os.remove(os.path.join(str(evidence_root), item["stored"]))
                    except OSError:
                        pass
            raise Refused(422, str(error)) from error

        logger.info("carrier registered pending review: %s", carrier_id)
        task = asyncio.get_running_loop().create_task(run_verification(carrier))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return {
            "carrier": carrier.to_dict(private=True),
            "proof_file": {"url": f"https://{carrier.domain}{kyb.WELL_KNOWN}" if carrier.domain else "",
                           "content": kyb.expected_proof(holder) if holder else ""},
            "next": (
                "Registered, and writing nothing. Every licence number here has "
                "to be checked against the regulator's own register by a person "
                "before this company can issue a policy."
            ),
        }

    background_tasks: set[asyncio.Task] = set()

    async def run_verification(carrier: Any) -> dict[str, Any]:
        """The automatic checks, off the request thread: GLEIF and the
        company's own domain are outside this process."""
        licence = carrier.licences[0] if carrier.licences else None
        result = await asyncio.to_thread(
            kyb.verify, name=carrier.name, lei=carrier.lei, domain=carrier.domain,
            address=carrier.address, country=licence.country if licence else carrier.domicile,
            reference=licence.reference if licence else "", domicile=carrier.domicile,
        )
        with money:
            carrier.verification = result
        if keeper is not None:
            await run_in_threadpool(keeper.save)
        return result

    @app.post("/api/carriers/{carrier_id}/verify")
    async def carrier_verify(
        carrier_id: str,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Run the automatic checks again: after the company has put its proof
        file up, or when GLEIF was unreachable the first time. The operator,
        or the company itself."""
        try:
            carrier = registry.require(carrier_id[:64])
        except CarrierError as error:
            raise HTTPException(404, str(error)) from error
        if sessions.of(token) is None and not operator:
            address = session_of(token)
            if address is None or carrier.address != address:
                raise Refused(401, "the operator, or the company that registered")
        elif sessions.of(token) is None:
            settings.require_admin(operator)
        if time.time() - float((carrier.verification or {}).get("checked_at", 0)) < 30:
            raise Refused(429, "checked less than half a minute ago; wait")
        return {"verification": await run_verification(carrier)}

    @app.get("/api/carriers/{carrier_id}/evidence/{n}")
    async def carrier_evidence(
        carrier_id: str, n: int,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> Response:
        """A document the company uploaded, for the reviewer's eyes."""
        try:
            carrier = registry.require(carrier_id[:64])
        except CarrierError as error:
            raise HTTPException(404, str(error)) from error
        if sessions.of(token) is None:
            if operator:
                settings.require_admin(operator)
            else:
                address = session_of(token)
                if address is None or carrier.address != address:
                    raise Refused(401, "the operator, or the company that registered")
        item = next((e for e in carrier.evidence if e.get("n") == n), None)
        stored = item.get("stored") if item else None
        if stored and not os.path.isabs(stored) and store is not None:
            stored = os.path.join(str(store.path.parent), stored)
        if item is None or not stored or not os.path.exists(stored):
            raise HTTPException(404, "no such document")
        with open(stored, "rb") as handle:
            body = handle.read()
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(item.get("filename") or f"document-{n}"))[:80]
        return Response(content=body, media_type=item["content_type"],
                        headers={"Content-Disposition": f'inline; filename="{safe_name}"',
                                 "Cache-Control": "no-store"})

    def book_of(carrier: Any, *, recent: int = 30) -> dict[str, Any]:
        """What one company has on its paper, and what it earned for it.

        Buyers appear by a shortened address and nothing else: the company
        needs to know what it has written, not who bought it.
        """
        from ..protocol.wallet import shorten

        mine = [p for p in pool.policies.values()
                if (p.metadata or {}).get("carrier") == carrier.carrier_id]
        if carrier.role is Role.REINSURER:
            # A reinsurer stands behind the whole book rather than named policies.
            mine = [p for p in pool.policies.values() if (p.metadata or {}).get("carrier")]
        open_ = [p for p in mine if p.is_open]
        premiums = sum(p.premium for p in mine)
        by_country: dict[str, dict[str, float]] = {}
        for p in open_:
            country = ((p.metadata or {}).get("compliance") or {}).get("country") or \
                ((p.metadata or {}).get("interest") or {}).get("country") or "?"
            row = by_country.setdefault(country, {"policies": 0, "in_force": 0.0})
            row["policies"] += 1
            row["in_force"] += p.limit
        rows = sorted(mine, key=lambda p: p.bought_at, reverse=True)[:recent]
        return {
            "policies": len(mine),
            "open": len(open_),
            "in_force": round(sum(p.limit for p in open_), 2),
            "premiums": round(premiums, 2),
            "fees": round(premiums * carrier.fronting_fee, 2) if carrier.role is Role.CARRIER else 0.0,
            "platform_fees": round(sum(float((p.metadata or {}).get("platform_fee_paid", 0.0))
                                       - float((p.metadata or {}).get("platform_fee_returned", 0.0)) for p in mine), 2),
            "platform_rate": fees.rate,
            "paid_out": round(sum(p.payout for p in mine), 2),
            "by_country": {k: {"policies": v["policies"], "in_force": round(v["in_force"], 2)}
                           for k, v in sorted(by_country.items())},
            "recent": [{
                "policy_id": p.policy_id, "peril": p.peril_key, "subject": p.peril.describe_subject(p.subject),
                "limit": round(p.limit, 2), "premium": round(p.premium, 2),
                "status": p.status.value, "bought_at": p.bought_at, "payout": round(p.payout, 2),
                "holder": shorten(p.holder),
            } for p in rows],
        }

    @app.get("/api/company")
    async def my_company(token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The companies this signed in address registered, and their books."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        with money:
            registry.reconcile(pool.policies.values())
            companies = [c for c in registry.carriers.values() if c.address == address]
            return {
                "address": address,
                "companies": [{**c.to_dict(private=True), "book": book_of(c)} for c in companies],
                "demo": specimen_desks(address),
            }

    def statement_reply(statement: dict[str, Any], format_: str, filename: str) -> Any:
        if format_ == "csv":
            from fastapi.responses import Response
            return Response(content=Fees.csv(statement), media_type="text/csv; charset=utf-8",
                            headers={"content-disposition": f'attachment; filename="{filename}"'})
        return statement

    def desk_reply(policies_: list[Any], *, q: str, status: str, peril: str, province: str,
                   due_within: float | None, sort: str, order: str, format_: str, limit: int, offset: int,
                   private: bool, filename: str) -> Any:
        names = {c.carrier_id: c.name for c in registry.carriers.values()}
        rows = desk.select(policies_, q=q, status=status, peril=peril, province=province, due_within=due_within,
                           sort=sort, descending=(order != "asc"), names=names, private=private)
        if format_ == "csv":
            from fastapi.responses import Response
            return Response(content=desk.to_csv(rows), media_type="text/csv; charset=utf-8",
                            headers={"content-disposition": f'attachment; filename="{filename}"'})
        everything = desk.select(policies_, names=names, private=private)
        return {"summary": desk.summary(everything), "by_province": desk.by_province(everything),
                "renewals_due": [r for r in everything if r["renewal_due"]][:200],
                "provinces": sorted({r["province"] for r in everything if r["province"]}),
                "total": len(rows), "offset": offset, "limit": limit,
                "policies": rows[offset:offset + limit]}

    @app.get("/api/company/policies")
    async def company_policies(carrier_id: str = Query(..., max_length=80), q: str = Query("", max_length=120),
                               status: str = Query("", max_length=60), peril: str = Query("", max_length=30),
                               province: str = Query("", max_length=60),
                               due_within: float | None = Query(None, ge=0, le=400),
                               sort: str = Query("bought_at", max_length=20), order: str = Query("desc", max_length=4),
                               format: str = Query("json", max_length=4),
                               limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
                               token: str | None = Depends(bearer)) -> Any:
        """The company's book, worked: found by number, street or place;
        filtered by status, peril or province; the ones ending within a
        number of days, for renewal; grouped by province; as CSV."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        carrier = registry.carriers.get(carrier_id)
        if carrier is None or carrier.address != address:
            raise HTTPException(404, "no such company on this account")
        with money:
            mine = [p for p in pool.policies.values() if (p.metadata or {}).get("carrier") == carrier_id]
            if carrier.role is Role.REINSURER:
                mine = [p for p in pool.policies.values() if (p.metadata or {}).get("carrier")]
            return desk_reply(mine, q=q, status=status, peril=peril, province=province, due_within=due_within,
                              sort=sort, order=order, format_=format, limit=limit, offset=offset,
                              private=carrier.role is not Role.REINSURER, filename=f"{carrier_id}-policies.csv")

    @app.get("/api/operator/policies")
    async def operator_policies(q: str = Query("", max_length=120), status: str = Query("", max_length=60),
                                peril: str = Query("", max_length=30), province: str = Query("", max_length=60),
                                carrier_id: str = Query("", max_length=80),
                                due_within: float | None = Query(None, ge=0, le=400),
                                sort: str = Query("bought_at", max_length=20), order: str = Query("desc", max_length=4),
                                format: str = Query("json", max_length=4),
                                limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
                                token: str | None = Depends(bearer),
                                operator: str | None = Header(None, alias="x-operator-token")) -> Any:
        """The whole book, worked the same way, for whoever runs the protocol."""
        reviewer_of(operator, token)
        with money:
            rows = [p for p in pool.policies.values()
                    if not carrier_id or (p.metadata or {}).get("carrier") == carrier_id]
            return desk_reply(rows, q=q, status=status, peril=peril, province=province, due_within=due_within,
                              sort=sort, order=order, format_=format, limit=limit, offset=offset,
                              private=False, filename=f"policies-{carrier_id or 'all'}.csv")

    @app.get("/api/company/statements")
    async def company_statements(carrier_id: str = Query(..., max_length=80), month: str = Query("", max_length=7),
                                 format: str = Query("json", max_length=4),
                                 token: str | None = Depends(bearer)) -> Any:
        """One company's month: every fee movement on its paper, line by
        line, and what it was left with. As JSON for the page, as CSV for
        the accountant."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        carrier = registry.carriers.get(carrier_id)
        if carrier is None or carrier.address != address:
            raise HTTPException(404, "no such company on this account")
        months = fees.months(carrier_id)
        month = month or (months[0] if months else month_of(time.time()))
        names = {c.carrier_id: c.name for c in registry.carriers.values()}
        statement = fees.statement(carrier_id, month, names=names)
        if format == "csv":
            return statement_reply(statement, "csv", f"{carrier_id}-{month}.csv")
        return {"months": months, "statement": statement, "rate": fees.rate}

    @app.get("/api/operator/statements")
    async def operator_statements(month: str = Query("", max_length=7), format: str = Query("json", max_length=4),
                                  carrier_id: str = Query("", max_length=80),
                                  token: str | None = Depends(bearer),
                                  operator: str | None = Header(None, alias="x-operator-token")) -> Any:
        """Every company's statement for a month, and the platform's own
        totals: what it took, what it gave back, by month."""
        reviewer_of(operator, token)
        months = fees.months()
        month = month or (months[0] if months else month_of(time.time()))
        names = {c.carrier_id: c.name for c in registry.carriers.values()}
        if format == "csv":
            if carrier_id:
                return statement_reply(fees.statement(carrier_id, month, names=names), "csv", f"{carrier_id}-{month}.csv")
            merged = {"carrier": "all companies", "lines": [], **{k: 0 for k in ("policies", "premiums_written",
                      "fronting_fees", "fronting_fees_returned", "platform_fees", "platform_fees_returned", "net_to_company")}}
            for st in fees.statements(month, names=names):
                merged["lines"] += st["lines"]
                for k in list(merged):
                    if k not in ("carrier", "lines"):
                        merged[k] = round(merged[k] + st[k], 2)
            return statement_reply(merged, "csv", f"all-{month}.csv")
        platform = wallets.get(PLATFORM_ACCOUNT)
        return {"months": months, "month": month, "statements": fees.statements(month, names=names),
                "platform": {**fees.platform_totals(), "balance": round(platform.balance, 2) if platform else 0.0}}

    def specimen_desks(address: str) -> dict[str, Any]:
        """The stand in companies a signed in account may act for, in a demonstration.

        No real company sits behind a specimen, so nobody could ever approve
        the applications placed with one. Where the stand ins are switched on
        this lets any signed in account take a specimen's desk and decide its
        applications, which is how a presenter shows both sides of a purchase.
        """
        if not settings.specimens:
            return {"on": False, "specimens": []}
        waiting: dict[str, int] = {}
        for a in applications.applications.values():
            if a.open and a.carrier_id:
                waiting[a.carrier_id] = waiting.get(a.carrier_id, 0) + 1
        rows = []
        for c in registry.carriers.values():
            if not c.specimen or c.status.value != "active":
                continue
            rows.append({
                "carrier_id": c.carrier_id, "name": c.name,
                "countries": sorted({l.country for l in c.licences}),
                "mine": c.address == address, "taken": bool(c.address) and c.address != address,
                "waiting": waiting.get(c.carrier_id, 0),
            })
        rows.sort(key=lambda r: (-r["waiting"], r["name"]))
        return {"on": True, "specimens": rows}

    @app.post("/api/company/specimen")
    async def take_specimen_desk(request: SpecimenDesk, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """Act for a stand in company, in a demonstration only."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        if not settings.specimens:
            raise Refused(404, "stand in companies are not switched on here")
        carrier = registry.carriers.get(request.carrier_id)
        if carrier is None or not carrier.specimen:
            raise Refused(404, "no such stand in company")
        with money:
            if request.release:
                if carrier.address == address:
                    carrier.address = None
            else:
                if carrier.address and carrier.address != address:
                    raise Refused(409, "someone else is at that desk; they can leave it")
                if carrier.status.value != "active":
                    raise Refused(409, "that stand in company is not active")
                carrier.address = address
        return {"demo": specimen_desks(address),
                "companies": [{**c.to_dict(private=True), "book": book_of(c)}
                              for c in registry.carriers.values() if c.address == address]}

    @app.get("/api/operator/overview")
    async def operator_overview(
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Both sides at once, for whoever runs the protocol: every company
        with its book, and every buyer's policies, newest first."""
        from ..protocol.wallet import shorten

        reviewer = reviewer_of(operator, token)
        with money:
            registry.reconcile(pool.policies.values())
            companies = [{**c.to_dict(private=True), "book": book_of(c, recent=5)}
                         for c in registry.carriers.values()]
            policies = sorted(pool.policies.values(), key=lambda p: p.bought_at, reverse=True)
            holders = {p.holder for p in policies}
            names = {c.carrier_id: c.name for c in registry.carriers.values()}
            recent = [{
                "policy_id": p.policy_id, "peril": p.peril_key, "subject": p.peril.describe_subject(p.subject),
                "limit": round(p.limit, 2), "premium": round(p.premium, 2),
                "status": p.status.value, "bought_at": p.bought_at, "payout": round(p.payout, 2),
                "holder": shorten(p.holder),
                "carrier": names.get((p.metadata or {}).get("carrier", ""), None),
                "country": ((p.metadata or {}).get("interest") or {}).get("country"),
            } for p in policies[:100]]
            attention = []
            for c in registry.carriers.values():
                if c.specimen:
                    continue
                d = vetting.due(c)
                if d["review_overdue"] or d["review_due_soon"] or d["licences_expiring"] or d["licences_lapsed"]:
                    attention.append({"carrier_id": c.carrier_id, "name": c.name, "status": c.status.value, **d})
            return {
                "reviewer": reviewer,
                "attention": attention,
                "totals": {
                    "buyers": len(holders), "policies": len(policies),
                    "open": sum(1 for p in policies if p.is_open),
                    "premiums": round(sum(p.premium for p in policies), 2),
                    "paid_out": round(sum(p.payout for p in policies), 2),
                    "pool_balance": round(pool.balance, 2),
                    "companies": len(companies),
                    "pending": sum(1 for c in companies if c["status"] == "pending"),
                },
                "companies": companies,
                "policies": recent,
            }

    @app.post("/api/operator/session")
    async def operator_session(
        http: Request, request: SessionRequest | None = None,
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Sign a reviewer in.

        The operator token is presented here, once, and exchanged for a session
        that expires. Everything after this carries the session instead, which
        is what lets the person reviewing registrations work in a browser rather
        than pasting the service's most valuable secret into a terminal.

        Rate limited hard and on every attempt rather than on failures, because
        a token guessed at a thousand tries a second is not a token.
        """
        guard(http, "operator", limit=8, window=900.0)
        settings.require_admin(operator)
        session = sessions.open(request.reviewer if request else "")
        logger.info("operator session opened for %r", session.reviewer or "operator")
        return {
            "token": session.token,
            "reviewer": session.reviewer or "operator",
            "expires_at": session.expires_at,
            "note": (
                "This session expires on its own and does not survive a restart "
                "of the service. The operator token is not needed again until it "
                "does."
            ),
        }

    @app.delete("/api/operator/session")
    async def operator_sign_out(token: str | None = Depends(bearer)) -> dict[str, Any]:
        sessions.close(token)
        return {"signed_out": True}

    @app.get("/api/operator/carriers")
    async def operator_carriers(
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Every registration, as the person reviewing it needs to see it.

        Wider than the public list: it carries the contact the company gave, the
        address that signed the registration, and the trail of decisions already
        taken about it. None of that belongs on a public page, and all of it
        belongs in front of whoever is deciding whether this company may issue
        policies to people.
        """
        reviewer = reviewer_of(operator, token)
        with money:
            registry.reconcile(pool.policies.values())
        companies = [c.to_dict(private=True) for c in registry.carriers.values()]
        pending = [c for c in companies if c["status"] == "pending"]
        return {
            "reviewer": reviewer,
            "companies": companies,
            "pending": len(pending),
            "summary": registry.summary(),
            "instruction": (
                "Nothing here has been checked by this service. Take each licence "
                "number to the authority's own public register and confirm it is "
                "held by this company, for this class of business, and still in "
                "force. Activating is your statement that you did."
            ),
        }

    def may_see_vetting(carrier: Any, operator: str | None, token: str | None) -> str:
        """The operator, or the company's own account: the company sees what
        is confirmed and what it still owes, the operator records it."""
        session = sessions.of(token)
        if session is not None:
            return session.reviewer or "operator"
        if operator:
            settings.require_admin(operator)
            return "operator"
        address = session_of(token)
        if address and carrier.address == address:
            return "company"
        raise Refused(401, "the operator or the company itself")

    @app.get("/api/carriers/{carrier_id}/vetting")
    async def carrier_vetting(carrier_id: str, token: str | None = Depends(bearer),
                              operator: str | None = Header(None, alias="x-operator-token")) -> dict[str, Any]:
        """The operator's checklist for one company: each item, what to
        confirm, where, the documents that bear on it, and who confirmed
        it when. The company sees the same list, so it knows what is owed."""
        try:
            carrier = registry.require(carrier_id[:64])
        except CarrierError as error:
            raise Refused(404, str(error)) from error
        who = may_see_vetting(carrier, operator, token)
        return {"carrier_id": carrier.carrier_id, "viewer": who, **vetting.summary(carrier),
                "can_activate": carrier.specimen or not vetting.missing(carrier)}

    @app.post("/api/carriers/{carrier_id}/vetting")
    async def carrier_vetting_record(carrier_id: str, request: VettingItem,
                                     token: str | None = Depends(bearer),
                                     operator: str | None = Header(None, alias="x-operator-token")) -> dict[str, Any]:
        """One item confirmed, failed or set aside, with where the reviewer
        looked and what they saw. Written on the company's record."""
        reviewer = reviewer_of(operator, token)
        try:
            carrier = registry.require(carrier_id[:64])
            with money:
                vetting.record(carrier, key=request.key, ok=request.ok, source=request.source,
                               note=request.note, by=reviewer)
        except CarrierError as error:
            raise Refused(404, str(error)) from error
        except ValueError as error:
            raise Refused(422, str(error)) from error
        logger.info("vetting %s on %s by %r: %s", request.key, carrier.carrier_id, reviewer, request.ok)
        return {"carrier_id": carrier.carrier_id, **vetting.summary(carrier),
                "can_activate": carrier.specimen or not vetting.missing(carrier)}

    @app.post("/api/company/{carrier_id}/evidence")
    async def company_more_evidence(carrier_id: str, request: MoreEvidence,
                                    token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The company adds documents after registering, when the operator
        asks for one the checklist needs."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        carrier = registry.carriers.get(carrier_id[:64])
        if carrier is None or carrier.address != address:
            raise HTTPException(404, "no such company on this account")
        if len(carrier.evidence) + len(request.evidence) > kyb.EVIDENCE_MAX_TOTAL:
            raise Refused(422, f"at most {kyb.EVIDENCE_MAX_TOTAL} documents on one company")
        evidence_root = store.path.parent if store is not None else None
        bodies = [e.model_dump() for e in request.evidence]
        try:
            kyb.store_evidence(None, carrier.carrier_id, bodies, start=len(carrier.evidence))
        except ValueError as error:
            raise Refused(422, str(error)) from error
        added = await run_in_threadpool(kyb.store_evidence, evidence_root, carrier.carrier_id, bodies,
                                        start=len(carrier.evidence))
        with money:
            carrier.evidence = list(carrier.evidence) + added
        return {"carrier": carrier.to_dict(private=True), **vetting.summary(carrier)}

    @app.post("/api/carriers/{carrier_id}/activate")
    async def carrier_activate(
        carrier_id: str,
        request: ReviewRequest | None = None,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """The human step: licences checked, company may write.

        Who took it and what they say they checked go into the company's record
        and stay there. An approval nobody can be asked about later is the part
        of a registry that fails an audit.
        """
        reviewer = reviewer_of(operator, token)
        try:
            found = registry.require(carrier_id[:64])
        except CarrierError as error:
            raise Refused(404, str(error)) from error
        left = [] if found.specimen else vetting.missing(found)
        if left:
            names = {i["key"]: i["title"] for i in vetting.checklist_for(found)}
            raise Refused(422, "confirm each required check before activating: " +
                          "; ".join(names[k] for k in left))
        try:
            carrier = registry.activate(
                carrier_id[:64], reviewer=reviewer, checks=found.vetting,
                note=((request.note if request else "") +
                      (" [confirmed: " + ", ".join(sorted(set(request.checked))) + "]" if request and request.checked else "")),
            )
        except CarrierError as error:
            raise Refused(404, str(error)) from error
        logger.info("carrier activated by %r: %s", reviewer, carrier.carrier_id)
        return {"carrier": carrier.to_dict(private=True)}

    @app.post("/api/carriers/{carrier_id}/suspend")
    async def carrier_suspend(
        carrier_id: str,
        request: ReviewRequest | None = None,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Stops matching immediately. Cover already written is unaffected, and
        the settlement check will see the suspension on its next run."""
        reviewer = reviewer_of(operator, token)
        try:
            carrier = registry.suspend(
                carrier_id[:64], (request.note if request else ""), reviewer=reviewer,
            )
        except CarrierError as error:
            raise Refused(404, str(error)) from error
        logger.info("carrier suspended by %r: %s", reviewer, carrier.carrier_id)
        return {"carrier": carrier.to_dict(private=True)}

    @app.post("/api/eligibility/demo")
    async def eligibility_demo(
        request: ChallengeRequest, http: Request
    ) -> dict[str, Any]:
        """Issue a demonstration statement about an address.

        In a deployment this endpoint does not exist. A person verifies their
        identity with a firm that actually looks at a document, and that firm
        signs the statement; the protocol never sees either. This stands in for
        that step so the flow can be walked end to end, and it says in its own
        reply that nothing was checked, because a statement that claims a check
        nobody performed is the exact thing this design is meant to avoid.

        It is tied to the faucet: on for a demonstration, off in public, one
        switch for both kinds of pretend.
        """
        if not settings.faucet:
            raise Refused(404, "not found")
        guard(http, "auth", limit=20, window=60.0)

        address = looks_like_address(request.address)
        try:
            claim = Claim(request.purpose)
        except ValueError as error:
            raise Refused(422, "that is not an attestation this protocol knows") from error

        verifier_id = (
            "demo-professional" if claim is Claim.PROFESSIONAL else "demo-identity"
        )
        key = _DEMO_KEYS.get(verifier_id)
        if key is None:
            raise Refused(503, "no verifier is available")

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        import base64

        now = time.time()
        # Short lives on purpose: a screening is good for a month at most, and
        # the payout path re-checks it.
        days = 25 if claim is Claim.SANCTIONS_CLEAR else 180
        country = None
        if claim is Claim.RESIDENCY:
            terms = request.terms or {}
            country = str(terms.get("country", ""))[:2].upper() or None

        draft = Attestation(
            subject=address, claim=claim, verifier_id=verifier_id,
            issued_at=now, expires_at=now + days * 86400, country=country,
        )
        signature = base64.urlsafe_b64encode(
            key.sign(draft.message.encode(), ec.ECDSA(hashes.SHA256()))
        ).decode().rstrip("=")

        return {
            "attestation": {
                "claim": claim.value, "verifier_id": verifier_id,
                "issued_at": draft.issued_at, "expires_at": draft.expires_at,
                "country": country, "signature": signature,
            },
            "demonstration": (
                "No document was checked and no person was identified. This is a "
                "correctly signed statement from a verifier that exists only in "
                "this build, so the flow can be walked without anyone uploading "
                "identification to a demonstration."
            ),
        }

    @app.post("/api/rider")
    async def rider_answer(request: RiderRequest, http: Request) -> dict[str, Any]:
        """Rider: the one part of this protocol that reasons.

        It reads, prices and explains, and it cannot spend. Not because it is
        told not to in a prompt, which is a request rather than a constraint,
        but because the only tools it has are reads and because its authority,
        where one is configured, is a Latch whose policy pipeline decides every
        call before a credential is used.

        Nothing said to it is stored. The transcript arrives from the browser
        and leaves with the reply.
        """
        guard(http, "rider", limit=12, window=60.0)
        if rider is None or not rider.available:
            raise Refused(503, (
                "Rider is not configured on this deployment. Everything it does "
                "is available directly: the same prices, the same registry and "
                "the same record, through the endpoints it would have called."
            ))

        turns = [
            {"role": "assistant" if t.role == "assistant" else "user",
             "content": t.content}
            for t in request.messages
        ][-24:]
        if not turns or turns[-1]["role"] != "user":
            raise Refused(422, "the last thing in a conversation is what was asked")

        # A mandate is passed on only if it is live; the model never sees it.
        mandate_token = None
        if request.mandate_token:
            try:
                mandates.authenticate(request.mandate_token)
                mandate_token = request.mandate_token
            except MandateError:
                mandate_token = None
        try:
            answer = await run_in_threadpool(
                lambda: rider.answer(turns, lang=request.lang, mandate_token=mandate_token)
            )
        except RiderError as error:
            raise Refused(502, str(error)) from error
        return answer

    @app.get("/api/rider")
    async def rider_state() -> dict[str, Any]:
        """Whether Rider is here, and what it is allowed to do.

        Said out loud rather than discovered, so the page never offers an
        assistant that cannot answer, and never implies a constraint that is not
        actually in place.
        """
        available = bool(rider and rider.available)
        return {
            "available": available,
            "authority": rider.authority.describe() if available else (
                "Rider is not configured on this deployment: no model key is set. "
                "Everything it would do is reachable directly, through the same "
                "endpoints it would have called."
            ),
            "constrained": bool(rider and rider.authority.constrained),
            # Only with a mandate the person signed, and only where a purchase
            # Latch is configured.
            "can_spend": bool(available and rider.can_buy and rider_key_hash),
            "tools": [t["name"] for t in RIDER_TOOLS],
        }

    @app.get("/api/eligibility")
    async def eligibility_view(
        limit: float = Query(100_000.0), country: str = Query("TR", max_length=2),
        professional: bool = Query(False),
    ) -> dict[str, Any]:
        """What a buyer would have to prove for this cover, and why each one.

        Answerable before anyone signs in, because a person deciding whether to
        start should be able to see what will be asked of them.
        """
        need = eligibility.requirement(
            limit=bounded(limit, "limit", MIN_LIMIT, MAX_LIMIT),
            professional=professional, country=country.upper(),
        )
        return {
            "requirement": need.to_dict(),
            "verifiers": [v.to_dict() for v in eligibility.verifiers.values()],
            "held_by_us": (
                "nothing. A verifier checks the document and signs a statement "
                "about your address; your device holds the statement and this "
                "protocol only checks the signature."
            ),
        }

    # -- applications: the issuing company checks before it issues -----------

    class ContractNotAccepted(ValueError):
        pass

    def refund_escrow(app: Any, reason: str) -> float:
        """What was held comes back to the applicant, once."""
        amount = app.release()
        if amount > 0:
            wallets.credit(app.holder, amount, app.app_id, kind="escrow_returned")
        return amount

    def collect_due() -> int:
        """Instalments that have fallen due, taken; overdue ones end the policy."""
        from ..protocol.instalments import due_now, overdue
        n, now = 0, time.time()
        with money:
            for policy in list(pool.open_policies):
                meta = policy.metadata or {}
                plan = meta.get("plan")
                if not plan or meta.get("provisional"):
                    continue
                for i in due_now(plan, now):
                    premium_i = plan_part(plan, "premium_parts", i)
                    fee_i = plan_part(plan, "fee_parts", i)
                    extra_i = plan_part(plan, "extra_parts", i)
                    try:
                        # One debit for premium and surcharge, one for the fee.
                        if wallets.require(policy.holder).balance + 1e-9 < premium_i + extra_i + fee_i:
                            raise WalletError("instalment not affordable")
                        pool.collect(policy, premium_i, extra=extra_i, now=now)
                        if fee_i > 0 and meta.get("carrier"):
                            charge_fee(policy, meta["carrier"], policy.holder, amount=fee_i)
                        plan["paid"][i] = True
                        plan["paid_total"] = round(plan["paid_total"] + premium_i + fee_i + extra_i, 2)
                        n += 1
                    except WalletError:
                        missed = plan.setdefault("missed", [])
                        if i not in missed:
                            missed.append(i)
                        break
                if overdue(plan, now):
                    try:
                        pool.cancel(policy, refund=0.0,
                                    note="ended for non payment: an instalment was not paid within the grace period")
                    except PoolError:
                        continue
                    chain.withdraw(policy)
        return n

    app.state.collect_due = collect_due

    # The demonstration writes policies by the thousand and, once settled,
    # they were kept for ever: every checkpoint encoded them, every capital
    # reading walked past them, every count on the chain's own page summed
    # them. A settled demonstration policy is of no further interest, so only
    # the most recent are kept and the rest are forgotten along with their
    # settlements, whose arithmetic the chain keeps so its published figures
    # do not move. Nothing a person bought is touched: the test is the
    # demonstration's own marker, or an address it derived for itself.
    demo_keep = max(0, int(os.environ.get("CLAUSE_DEMO_KEEP", "2000") or 0))

    def demo_policy(policy: Any, claimable: set[str] | None = None) -> bool:
        """The demonstration's own, by three tests in order.

        A record that says outright it is not the demonstration's is believed,
        so anything can be exempted by hand. A policy that carries the
        contract its holder accepted came through the application path and is
        somebody's, whatever else is true of it. Otherwise it is the
        demonstration's if it is marked, if it was written to an address the
        demonstration derived for itself, or if nobody can reach it: no device
        key, no account, no linked wallet, no partner behind it. Books written
        before the addresses changed shape hold demonstration policies that
        only the last of those catches.
        """
        meta = policy.metadata or {}
        if meta.get("synthetic") is False or meta.get("partner"):
            return False
        if meta.get("contract") or meta.get("contract_hash"):
            return False
        if is_synthetic(policy):
            return True
        if claimable is None:
            return synthetic_policy(policy)
        return policy.holder not in claimable

    def claimable_holders() -> set[str]:
        """Every address somebody can still act as: a key registered on a
        device, an account signed in through Privy, a wallet linked to one."""
        held = set(auth.keys) | set(accounts._by_user.values())
        held.update(link.account for link in links.links.values())
        return held

    def forget_demo_book() -> int:
        if demo_keep <= 0:
            return 0
        with money:
            claimable = claimable_holders()
            closed = [p for p in pool.policies.values()
                      if not p.is_open and demo_policy(p, claimable)]
            if len(closed) <= demo_keep:
                return 0
            closed.sort(key=lambda p: (p.ends_at or p.bought_at or 0.0))
            gone = {p.policy_id for p in closed[: len(closed) - demo_keep]}
            for policy_id in gone:
                pool.policies.pop(policy_id, None)
            chain.forget(gone)
        logger.info("forgot %d settled demonstration policies, keeping %d", len(gone), demo_keep)
        return len(gone)

    app.state.forget_demo_book = forget_demo_book
    app.state.demo_policy = demo_policy

    def lapse_overdue() -> int:
        n = 0
        with money:
            for app in applications.overdue():
                applications.close(app, "lapsed", by="protocol",
                                   note="not decided within three days; premium returned")
                refund_escrow(app, "lapsed")
                documents.purge(app.app_id)
                n += 1
        return n

    def can_decide(app: Any, operator: str | None, token: str | None) -> str:
        """The operator, or whoever registered the company that would issue it."""
        session = sessions.of(token)
        if session is not None:
            return session.reviewer or "operator"
        if operator:
            settings.require_admin(operator)
            return "operator"
        address = session_of(token)
        carrier = registry.carriers.get(app.carrier_id or "")
        if address and carrier is not None and carrier.address == address:
            return f"{carrier.name}, {address[:10]}"
        raise Refused(401, "only the issuing company or the operator decides an application")

    def make_application(*, holder: str, peril: str, subject: dict[str, Any], limit: float,
                         term_days: float, interest: InterestDeclaration, size: dict[str, Any] | None,
                         settlement: str, max_premium: float | None, instalments: int,
                         contract_hash: str | None, quote_id: str | None, address: dict[str, str] | None,
                         need: Any, ruling: Any, info: dict[str, Any], instruction_id: str = "") -> Any:
        """Price, write the contract, hold the first payment and queue the
        application for the company. Under the money lock.

        By hand, ``contract_hash`` is what the buyer read and accepted and
        must match the contract written here. From a standing instruction it
        is None: the person signed the terms in advance and the contract
        written now, on those terms, is the one the application carries.
        """
        kind = KIND_FOR.get(peril)
        with money:
            quoted = promised(quote_id, peril, subject, limit, term_days) \
                or pool.quote(peril_key=peril, subject=subject, limit=limit, term_days=term_days)
            if max_premium is not None and quoted.premium > float(max_premium) + 0.01:
                raise PriceMoved(
                    f"the price moved while you were deciding: {quoted.premium:,.2f} "
                    f"against the {float(max_premium):,.2f} you agreed to. "
                    f"Nothing was taken; ask for a fresh price.")
            allowed, reasons = pool.can_write(peril_key=peril, subject=subject, limit=limit, term_days=term_days)
            if not allowed:
                raise PoolError("; ".join(reasons))
            peril_ = get_peril(peril)
            fee = fronting_fee_of(ruling.carrier_id, quoted.premium)
            # The contract the buyer accepted has to be the one that would
            # be issued: same terms, same price, same company.
            text, digest_, plan = contract_for(
                peril_key=peril, subject=subject, limit=limit, term_days=term_days,
                premium=round(quoted.premium, 2), carrier_id=ruling.carrier_id, holder="",
                country=interest.country.upper(), instalments=instalments,
                address=address, value_basis=info["valuation"].basis if info["valuation"] else "")
            if not instruction_id:
                if not contract_hash:
                    raise ContractNotAccepted("read and accept the contract before signing")
                if contract_hash != digest_:
                    raise ContractNotAccepted("the contract has changed since you read it; read it again")
            checks_ = [c.value for c in need.claims]
            if kind in ("home", "vehicle"):
                checks_.append("ownership")
            app_ = applications.create(
                holder=holder, peril=peril, subject=subject, limit=limit,
                term_days=term_days, declared=interest.model_dump(), size=size,
                value_at_risk=info["value_at_risk"], settlement=settlement,
                premium=round(quoted.premium, 2), fee=fee, carrier_id=ruling.carrier_id,
                checks=checks_,
                subject_text=peril_.describe_subject(peril_.validate_subject(subject)),
                contract=text, contract_hash=digest_, address=address, plan=plan,
                instruction_id=instruction_id,
            )
            try:
                wallets.debit(holder, app_.first_payment, app_.app_id, kind="escrow")
            except WalletError:
                applications.applications.pop(app_.app_id, None)
                raise
            return app_

    @app.post("/api/applications")
    async def apply(request: BuyRequest, http: Request) -> dict[str, Any]:
        """Ask for cover. Signed like a purchase; the premium is held, not taken,
        until the company that would issue it has done its checks."""
        guard(http, "buy", limit=10, window=60.0)
        subject = clean_subject(request.subject)
        limit = bounded(request.limit, "limit", MIN_LIMIT, MAX_LIMIT)
        term_days = bounded(request.term_days, "term_days", MIN_TERM_DAYS, MAX_TERM_DAYS)
        value_at_risk = bounded(request.interest.value_at_risk, "value_at_risk", MIN_LIMIT, MAX_LIMIT)
        size = clean_subject(request.interest.size) if request.interest.size is not None else None
        terms = {
            "peril": request.peril, "limit": limit, "term_days": term_days,
            "subject": subject, "country": request.interest.country.upper(),
            "value_at_risk": value_at_risk,
        }
        if size is not None:
            terms["size"] = size
        if request.carrier_id:
            terms["carrier_id"] = request.carrier_id
        if request.contract_hash:
            terms["contract_hash"] = request.contract_hash
        if request.instalments > 1:
            terms["instalments"] = float(request.instalments)
        holder = signed(request.holder, "buy", request.nonce, request.signature, terms)
        address = clean_address(request.interest.address)
        kind = KIND_FOR.get(request.peril)
        if kind in ("home", "vehicle") and not address:
            raise Refused(422, "give the address of the home, or where the car is kept: the insurer "
                               "checks that it is yours")
        need, ruling, info = await issue(
            holder=holder, peril=request.peril, subject=subject, limit=limit,
            term_days=term_days, declared=request.interest, size=size,
            value_at_risk=value_at_risk, settlement=request.settlement,
            attestations=[], max_premium=request.max_premium, review=True,
            carrier_id=request.carrier_id,
        )

        try:
            app_ = await run_in_threadpool(
                make_application, holder=holder, peril=request.peril, subject=subject, limit=limit,
                term_days=term_days, interest=request.interest, size=size, settlement=request.settlement,
                max_premium=request.max_premium, instalments=request.instalments,
                contract_hash=request.contract_hash, quote_id=request.quote_id, address=address,
                need=need, ruling=ruling, info=info)
        except WalletError as error:
            raise Refused(402, safe_detail(error, fallback="insufficient balance")) from error
        except PriceMoved as error:
            raise Refused(409, str(error)) from error
        except ContractNotAccepted as error:
            raise Refused(409, str(error)) from error
        except ValueError as error:
            raise Refused(422, safe_detail(error, fallback="that application was refused")) from error
        except PoolError as error:
            raise Refused(409, safe_detail(error, fallback="the pool cannot write this cover")) from error
        # The order is confirmed now; the right to withdraw is given when the
        # policy exists, since until the insurer decides there is no contract
        # to withdraw from and the premium is only held.
        try:
            when = dt.datetime.fromtimestamp(app_.created_at, dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC")
            papers.give(holder, "confirmation", f"Your application, {app_.app_id}",
                        (f"Cover of {app_.limit:,.0f} USDC for {app_.term_days:g} days, "
                         f"for {app_.premium:,.2f} USDC. Asked for {when}. The premium is held, "
                         "not taken, until the company that would issue it has decided."),
                        about=app_.app_id)
            if app_.contract:
                papers.give(holder, "terms", f"The contract you accepted, {app_.app_id}",
                            app_.contract, about=app_.app_id,
                            terms_hash=getattr(app_, "contract_hash", "") or "")
        except Exception:
            logger.exception("could not write the papers for %s", app_.app_id)
        counting.count("applied", request.peril)
        return {"application": with_documents(app_), "wallet": wallets.require(holder).as_dict(),
                "session": auth.issue_session(holder)}

    @app.get("/api/applications/{app_id}/contract")
    async def application_contract(app_id: str, token: str | None = Depends(bearer)):
        from fastapi.responses import PlainTextResponse
        address = session_of(token)
        app_ = applications.applications.get(app_id)
        if app_ is None or address is None or app_.holder != address:
            raise HTTPException(404, "no such application")
        return PlainTextResponse(app_.contract or "", media_type="text/plain; charset=utf-8")

    @app.get("/api/policies/{policy_id}/contract")
    async def policy_contract(policy_id: str, download: bool = Query(False),
                              token: str | None = Depends(bearer)):
        """The contract as the holder's own copy. The first time it is
        taken is noted on the policy: a document on the buyer's device is
        the durable medium the distance selling rules ask for, and the
        right to withdraw is counted from it when nothing earlier counts."""
        from fastapi.responses import PlainTextResponse
        address = session_of(token)
        found = pool.policies.get(policy_id)
        if found is None or address is None or found.holder != address:
            raise HTTPException(404, f"no policy {policy_id}")
        app_ = applications.applications.get((found.metadata or {}).get("application", ""))
        text = app_.contract if app_ is not None else str((found.metadata or {}).get("contract") or "")
        if text:
            record = found.metadata.setdefault("disclosure", {})
            record.setdefault("kept_at", time.time())
            record.setdefault("hash", getattr(app_, "contract_hash", None))
        headers = {"content-disposition": f'attachment; filename="{policy_id}-contract.txt"'} if download else {}
        return PlainTextResponse(text, media_type="text/plain; charset=utf-8", headers=headers)

    # -- standing instructions ----------------------------------------------

    def instruction_terms(request: InstructionRequest) -> dict[str, Any]:
        """What the device signs: the whole instruction, normalised the way
        the challenge normalised it."""
        terms: dict[str, Any] = {"kind": request.kind, "max_premium": round(float(request.max_premium), 2),
                                 "days": float(request.days)}
        if request.kind == "renew":
            terms["policy_id"] = request.policy_id or ""
            return terms
        terms.update({"peril": request.peril or "", "subject": clean_subject(request.subject or {}),
                      "limit": float(request.limit or 0), "term_days": float(request.term_days or 0),
                      "when": request.when})
        if request.when == "age":
            terms["years"] = float(request.years or 0)
        else:
            terms["at"] = float(request.at or 0)
        if request.carrier_id:
            terms["carrier_id"] = request.carrier_id
        if request.instalments > 1:
            terms["instalments"] = float(request.instalments)
        return terms

    @app.get("/api/instructions")
    async def instructions_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        names = {c.carrier_id: c.name for c in registry.carriers.values()}
        return {"instructions": [{**i.to_dict(), "carrier": names.get(i.carrier_id or "")}
                                 for i in instructions.mine(address)[:50]],
                "renew_lead_days": 1, "max_days": 3650}

    @app.post("/api/instructions")
    async def instruction_give(request: InstructionRequest, http: Request) -> dict[str, Any]:
        """Give a standing instruction. Renewal: the policy's own terms, its
        declaration and address are copied from the policy and the
        application it came from. Buy: the purchase, in full, and when."""
        guard(http, "buy", limit=10, window=60.0)
        if request.kind not in ("renew", "buy"):
            raise Refused(422, "an instruction renews a policy or buys cover from a date")
        terms = instruction_terms(request)
        account = signed(request.account, "instruct", request.nonce, request.signature, terms)
        max_premium = bounded(request.max_premium, "max_premium", 0.01, MAX_LIMIT)
        try:
            if request.kind == "renew":
                policy = pool.policies.get(request.policy_id or "")
                if policy is None or policy.holder != account:
                    raise Refused(404, "no such policy of yours")
                if policy.peril_key == "flight_delay":
                    raise Refused(422, "a flight is not renewed; buy cover for the next one")
                meta = policy.metadata or {}
                interest = meta.get("interest") or {}
                app_ = applications.applications.get(meta.get("application", ""))
                declared = dict(app_.declared) if app_ is not None else {
                    "what": interest.get("what", "cover"), "country": interest.get("resident") or interest.get("country") or "TR",
                    "inside_trigger_area": True, "value_at_risk": interest.get("value_at_risk", policy.limit),
                    "professional": interest.get("professional", False), "size": interest.get("size"),
                }
                with money:
                    item = instructions.create(
                        account, kind="renew", peril=policy.peril_key, subject=dict(policy.subject),
                        limit=policy.limit, term_days=policy.term_days, declared=declared,
                        size=interest.get("size") or (app_.size if app_ is not None else None),
                        value_at_risk=float(interest.get("value_at_risk", policy.limit)),
                        settlement="stablecoin", carrier_id=meta.get("carrier"),
                        address=app_.address if app_ is not None else None, max_premium=max_premium,
                        instalments=len((meta.get("plan") or {}).get("amounts") or []) or 1,
                        days=request.days, policy_id=policy.policy_id)
            else:
                if not (request.peril and request.subject and request.limit and request.term_days and request.interest):
                    raise Refused(422, "a buy instruction names the cover, the subject, the limit, the term and what is at risk")
                if request.peril not in REGISTRY:
                    raise Refused(422, "unknown peril")
                subject = clean_subject(request.subject)
                limit = bounded(request.limit, "limit", MIN_LIMIT, MAX_LIMIT)
                term_days = bounded(request.term_days, "term_days", MIN_TERM_DAYS, MAX_TERM_DAYS)
                value_at_risk = bounded(request.interest.value_at_risk, "value_at_risk", MIN_LIMIT, MAX_LIMIT)
                size = clean_subject(request.interest.size) if request.interest.size is not None else None
                address = clean_address(request.interest.address)
                if KIND_FOR.get(request.peril) in ("home", "vehicle") and not address:
                    raise Refused(422, "give the address of the home, or where the car is kept")
                # Priced and checked now, so an instruction that could never be
                # honoured is refused today rather than failing on its day.
                need, _ruling, _info = await issue(
                    holder=account, peril=request.peril, subject=subject, limit=limit,
                    term_days=term_days, declared=request.interest, size=size,
                    value_at_risk=value_at_risk, settlement=request.settlement, attestations=[],
                    max_premium=None, review=True, carrier_id=request.carrier_id)
                # What the purchase would ask the person for is asked now, and
                # what was shown is remembered by name until it expires.
                presented = []
                for body in request.attestations:
                    try:
                        presented.append(Attestation(
                            subject=account, claim=Claim(body.claim), verifier_id=body.verifier_id,
                            issued_at=finite(body.issued_at, "issued_at"),
                            expires_at=finite(body.expires_at, "expires_at"),
                            country=body.country, signature=body.signature))
                    except ValueError as error:
                        raise Refused(422, "that is not an attestation this protocol knows") from error
                standing = eligibility.check(address=account, attestations=presented, requirement=need)
                if KIND_FOR.get(request.peril) not in ("home", "vehicle") and settings.direct_buy and not standing.ok:
                    raise HTTPException(451, {"reasons": [
                        "before this can be bought for you, you need: "
                        + ", ".join(c.value.replace("_", " ") for c in standing.missing)] + list(standing.reasons),
                        "eligibility": standing.to_dict()})
                held = tuple(sorted({a.claim.value for a in standing.held}))
                with money:
                    item = instructions.create(
                        account, kind="buy", peril=request.peril, subject=subject, limit=limit,
                        term_days=term_days, declared=request.interest.model_dump(), size=size,
                        value_at_risk=value_at_risk, settlement=request.settlement,
                        carrier_id=request.carrier_id, address=address, max_premium=max_premium,
                        instalments=request.instalments, days=request.days,
                        condition={"when": request.when, "at": request.at, "years": request.years},
                        claims=held, claims_expire_at=min((a.expires_at for a in standing.held), default=None))
        except InstructionError as error:
            raise Refused(422, str(error)) from error
        return {"instruction": item.to_dict()}

    @app.post("/api/instructions/{instruction_id}/cancel")
    async def instruction_cancel(instruction_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        try:
            with money:
                item = instructions.cancel(address, instruction_id[:24])
        except InstructionError as error:
            raise Refused(409, str(error)) from error
        return {"instruction": item.to_dict()}

    async def run_instruction(item: Any) -> None:
        """One attempt at what an instruction says, through the same path a
        purchase by hand takes; the outcome is written on the instruction."""
        declared = InterestDeclaration(**{k: v for k, v in item.declared.items()
                                          if k in InterestDeclaration.model_fields})
        subject = clean_subject(item.subject)
        size = clean_subject(item.size) if item.size else None
        kind = KIND_FOR.get(item.peril)
        old = pool.policies.get(item.policy_id) if item.kind == "renew" else None
        vouched = frozenset(((old.metadata or {}).get("eligibility") or {}).get("claims") or []) if old else frozenset()
        if item.claims and (item.claims_expire_at is None or item.claims_expire_at > time.time()):
            vouched = vouched | frozenset(item.claims)
        metadata = {"instruction": item.instruction_id, "bought_by": "instruction"}
        if old is not None:
            metadata["renews"] = old.policy_id
        try:
            if kind in ("home", "vehicle") or not settings.direct_buy:
                need, ruling, info = await issue(
                    holder=item.account, peril=item.peril, subject=subject, limit=item.limit,
                    term_days=item.term_days, declared=declared, size=size, value_at_risk=item.value_at_risk,
                    settlement=item.settlement, attestations=[], max_premium=item.max_premium, review=True,
                    carrier_id=item.carrier_id, satisfied=vouched)
                app_ = await run_in_threadpool(
                    make_application, holder=item.account, peril=item.peril, subject=subject, limit=item.limit,
                    term_days=item.term_days, interest=declared, size=size, settlement=item.settlement,
                    max_premium=item.max_premium, instalments=item.instalments, contract_hash=None,
                    quote_id=None, address=item.address, need=need, ruling=ruling, info=info,
                    instruction_id=item.instruction_id)
                instructions.record(item, "applied", application_id=app_.app_id,
                                    note="applied; the company decides")
            else:
                policy, armed, ruling = await issue(
                    holder=item.account, peril=item.peril, subject=subject, limit=item.limit,
                    term_days=item.term_days, declared=declared, size=size, value_at_risk=item.value_at_risk,
                    settlement=item.settlement, attestations=[], max_premium=item.max_premium,
                    satisfied=vouched, metadata=metadata, carrier_id=item.carrier_id)
                instructions.record(item, "bought", policy_id=policy.policy_id,
                                    note=f"bought at {policy.premium:,.2f}")
        except HTTPException as error:
            detail = error.detail
            text = "; ".join(detail.get("reasons", [])) if isinstance(detail, dict) else str(detail)
            instructions.record(item, "waiting", note=text[:200] or "refused")
        except PriceMoved as error:
            instructions.record(item, "waiting", note=f"over the cap: {error}")
        except WalletError as error:
            instructions.record(item, "waiting", note=safe_detail(error, fallback="insufficient balance"))
        except (PoolError, ContractNotAccepted, ValueError) as error:
            instructions.record(item, "waiting", note=safe_detail(error, fallback="the cover cannot be written now"))
        except Exception as error:  # one instruction failing must not stop the rest
            logger.exception("instruction %s failed", item.instruction_id)
            instructions.record(item, "waiting", note=safe_detail(error, fallback="could not be carried out"))

    async def run_instructions() -> int:
        """Every instruction whose moment has come; and the applications the
        earlier ones made that the company has since decided."""
        with money:
            instructions.settle_waiting(applications.applications)
            due = instructions.due(pool.policies)
        for item in due:
            await run_instruction(item)
        return len(due)

    app.state.run_instructions = run_instructions

    @app.get("/api/applications")
    async def applications_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        names = {c.carrier_id: c.name for c in registry.carriers.values()}
        return {"applications": [{**with_documents(a), "carrier": names.get(a.carrier_id or "")}
                                 for a in applications.mine(address)[:50]],
                "demo": settings.specimens}

    def with_documents(app_: Any, *, private: bool = False) -> dict[str, Any]:
        """An application as the page sees it, with what was sent for it:
        names, sizes, who opened what and when; never the bytes."""
        out = app_.to_dict(private=private)
        out["documents"] = [d.to_dict() for d in documents.for_application(app_.app_id)]
        return out

    def recipient_of(carrier_id: str | None) -> dict[str, Any]:
        carrier = registry.carriers.get(carrier_id or "")
        found = documents.recipient_for(carrier)
        return {"carrier_id": carrier.carrier_id if carrier else None,
                "name": carrier.name if carrier else None,
                "recipient": found[0] if found else None,
                "reading_key": found[1] if found else None}

    @app.post("/api/auth/reading-key")
    async def register_reading_key(request: ReadingKey, http: Request,
                                   token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The key documents to this account are sealed to. Made in its
        browser, non extractable; only the public point comes here."""
        guard(http, "reading-key", limit=10, window=60.0)
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        try:
            key = documents.register_key(address, request.public_key)
        except DocumentError as error:
            raise Refused(422, str(error)) from error
        return {"address": address, "reading_key": key}

    @app.post("/api/operator/reading-key")
    async def register_operator_reading_key(
        request: ReadingKey, http: Request, token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """The operator decides for stand in companies, so documents sent to
        one are sealed to the operator's browser. One key: the last browser
        to register wins, and what was sealed to an earlier one stays shut."""
        guard(http, "reading-key", limit=10, window=60.0)
        who = reviewer_of(operator, token)
        try:
            key = documents.register_key(READER_OPERATOR, request.public_key)
        except DocumentError as error:
            raise Refused(422, str(error)) from error
        logger.info("operator reading key registered by %r", who)
        return {"address": READER_OPERATOR, "reading_key": key}

    @app.get("/api/applications/recipient")
    async def document_recipient(carrier_id: str = Query("", max_length=80)) -> dict[str, Any]:
        """Who will be able to open documents sent with an application to
        this company, and the key to seal them to; nobody, when neither the
        company nor, for a stand in, the operator has a reading key yet."""
        return recipient_of(carrier_id)

    @app.post("/api/applications/{app_id}/documents")
    async def application_documents_send(
        app_id: str, request: SealedDocuments, http: Request,
        token: str | None = Depends(bearer),
    ) -> dict[str, Any]:
        """Documents for the company's checks, sealed in the applicant's
        browser to that company's reading key. Sent after the application,
        while it is still open; the protocol keeps the ciphertext and a
        record, and cannot read either document."""
        guard(http, "documents", limit=12, window=60.0)
        address = session_of(token)
        try:
            app_ = applications.require(app_id)
        except ApplicationError as error:
            raise HTTPException(404, str(error)) from error
        if address is None or app_.holder != address:
            raise HTTPException(404, "no such application")
        if not app_.open:
            raise Refused(409, f"that application is already {app_.status}; nothing more can be sent for it")
        recipient = recipient_of(app_.carrier_id)
        if not recipient["reading_key"]:
            raise Refused(409, "the company that will decide this application has no reading key yet, "
                               "so nothing can be sealed to it; it will ask for its documents by other means")
        try:
            added = documents.add(app_id=app_.app_id, holder=address,
                                  items=[d.model_dump() for d in request.documents],
                                  recipient=recipient["recipient"], recipient_key=recipient["reading_key"])
        except DocumentError as error:
            raise Refused(422, str(error)) from error
        return {"documents": [d.to_dict() for d in added], "application": with_documents(app_)}

    @app.delete("/api/applications/{app_id}/documents/{doc_id}")
    async def application_document_remove(app_id: str, doc_id: str,
                                          token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The applicant takes a document back, while the application is open."""
        address = session_of(token)
        try:
            app_ = applications.require(app_id)
            doc = documents.require(app_id, doc_id)
        except (ApplicationError, DocumentError) as error:
            raise HTTPException(404, str(error)) from error
        if address is None or app_.holder != address:
            raise HTTPException(404, "no such application")
        if not app_.open:
            raise Refused(409, f"that application is already {app_.status}")
        documents.remove(doc)
        return {"application": with_documents(app_)}

    @app.get("/api/applications/{app_id}/documents/{doc_id}")
    async def application_document_open(
        app_id: str, doc_id: str, http: Request,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """The sealed envelope, to whoever may decide the application. Opening
        is recorded, and the applicant sees who opened what and when. The
        bytes come out as they went in: sealed, for that party's browser."""
        guard(http, "documents", limit=60, window=60.0)
        try:
            app_ = applications.require(app_id)
            doc = documents.require(app_id, doc_id)
        except (ApplicationError, DocumentError) as error:
            raise HTTPException(404, str(error)) from error
        who = can_decide(app_, operator, token)
        try:
            data = documents.ciphertext(doc)
        except DocumentError as error:
            raise Refused(410, str(error)) from error
        documents.mark_opened(doc, who)
        return doc.envelope(data)

    @app.post("/api/applications/{app_id}/withdraw")
    async def application_withdraw(app_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The applicant changes their mind before a decision: all of it back."""
        address = session_of(token)
        try:
            app_ = applications.require(app_id)
        except ApplicationError as error:
            raise HTTPException(404, str(error)) from error
        if address is None or app_.holder != address:
            raise HTTPException(404, "no such application")
        with money:
            try:
                applications.close(app_, "withdrawn", by="applicant")
            except ApplicationError as error:
                raise Refused(409, str(error)) from error
            refund_escrow(app_, "withdrawn")
            documents.purge(app_.app_id)
        return {"application": with_documents(app_)}

    @app.get("/api/review/applications")
    async def review_list(
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """What is waiting for a decision: every application for the operator,
        a company's own for a company."""
        session = sessions.of(token)
        if session is not None or operator:
            if session is None:
                settings.require_admin(operator)
            ids = None
        else:
            address = session_of(token)
            if address is None:
                raise Refused(401, "sign in first")
            ids = {c.carrier_id for c in registry.carriers.values() if c.address == address}
        names = {c.carrier_id: c.name for c in registry.carriers.values()}
        rows = applications.for_carriers(ids)
        return {"applications": [{**with_documents(a, private=True), "carrier": names.get(a.carrier_id or "")}
                                 for a in rows[:200]],
                "waiting": sum(1 for a in rows if a.open)}

    @app.post("/api/review/applications/{app_id}")
    async def review_decide(
        app_id: str, request: ApplicationDecision,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Approve, having done the checks, or reject with a reason."""
        try:
            app_ = applications.require(app_id)
        except ApplicationError as error:
            raise HTTPException(404, str(error)) from error
        reviewer = can_decide(app_, operator, token)
        if request.decision not in ("approve", "reject"):
            raise Refused(422, "approve or reject")
        if request.decision == "reject" and len(request.note.strip()) < 3:
            raise Refused(422, "say why it is rejected; the applicant is told")
        missing = [c for c in app_.checks if c not in request.checked] if request.decision == "approve" else []
        if missing:
            raise Refused(422, "confirm each check before approving: " + ", ".join(
                m.replace("_", " ") for m in missing))
        # Claim it: from here no second decision, and no withdrawal, can act
        # on this application until this one has finished.
        with money:
            try:
                applications.begin_decision(app_)
            except ApplicationError as error:
                raise Refused(409, str(error)) from error
        if request.decision == "reject":
            with money:
                applications.close(app_, "rejected", by=reviewer, note=request.note)
                refund_escrow(app_, "rejected")
                documents.purge(app_.app_id)
            return {"application": with_documents(app_)}

        declared = InterestDeclaration(**app_.declared)

        def fixed_quote():
            import dataclasses as _dc
            with money:
                fresh = pool.quote(peril_key=app_.peril, subject=app_.subject, limit=app_.limit,
                                   term_days=app_.term_days)
            return _dc.replace(fresh, premium=app_.premium,
                               risk_load=max(0.0, app_.premium - fresh.expected_loss - fresh.expense_load))

        # The plan's dates run from approval, as the contract says.
        plan = rescheduled(app_.plan, starts_at=time.time()) if app_.plan else None
        first_premium = fee_first = None
        if plan:
            plan["paid"][0] = True
            plan["paid_total"] = plan["amounts"][0] if plan.get("amounts") else plan["amount"]
            first_premium = plan_part(plan, "premium_parts", 0)
            fee_first = plan_part(plan, "fee_parts", 0)
        try:
            locked = await run_in_threadpool(fixed_quote)
        except Exception as error:
            with money:
                applications.reopen(app_)
            raise Refused(409, safe_detail(error, fallback="the cover could not be priced")) from error
        with money:
            # What was held comes back out of escrow and is taken again by the
            # pool as the policy is written, so the ledger shows both.
            refund_escrow(app_, "released to the pool")
        try:
            policy, armed, ruling = await issue(
                holder=app_.holder, peril=app_.peril, subject=app_.subject, limit=app_.limit,
                term_days=app_.term_days, declared=declared, size=app_.size,
                value_at_risk=app_.value_at_risk, settlement=app_.settlement,
                attestations=[], max_premium=None, satisfied=frozenset(app_.checks),
                metadata={"application": app_.app_id, "reviewed_by": reviewer,
                          "review_note": request.note[:400],
                          "contract_hash": app_.contract_hash,
                          "address_hash": hashlib.sha256(json.dumps(app_.address, sort_keys=True).encode()).hexdigest()[:16] if app_.address else None,
                          **({"plan": plan} if plan else {})},
                locked_quote=locked, carrier_id=app_.carrier_id, paid_now=first_premium,
                fee_now=fee_first,
            )
            if plan:
                # The surcharge part of the first instalment, to the pool.
                with money:
                    extra = plan_part(plan, "extra_parts", 0)
                    if extra > 0:
                        pool.collect(policy, 0.0, extra=extra)
        except Exception as error:
            # Hold the money again and give the application back to the queue;
            # if the applicant has spent it in the meantime, the application
            # cannot be honoured and is closed, and they are told why.
            with money:
                try:
                    wallets.debit(app_.holder, app_.first_payment, app_.app_id, kind="escrow")
                    app_.released = False
                    applications.reopen(app_)
                except WalletError:
                    applications.close(app_, "rejected", by="protocol",
                                       note="the premium could not be taken when the policy was written; "
                                            "the held amount had been spent")
            if isinstance(error, (HTTPException, Refused)):
                raise error
            logger.exception("approval of %s failed", app_.app_id)
            raise Refused(409, safe_detail(error, fallback="the policy could not be written")) from error
        with money:
            applications.close(app_, "approved", by=reviewer, note=request.note,
                               checked=list(request.checked), policy_id=policy.policy_id)
            documents.purge(app_.app_id)
        try:
            papers.give(app_.holder, "decision", f"Your cover is in force, {policy.policy_id}",
                        (f"The application {app_.app_id} was approved and the policy "
                         f"{policy.policy_id} is registered on the chain. The premium that was "
                         "held has been taken."),
                        about=policy.policy_id)
        except Exception:
            logger.exception("could not write the decision paper for %s", app_.app_id)
        give_papers(app_.holder, policy, (policy.metadata or {}).get("contract", ""),
                    (policy.metadata or {}).get("contract_hash", ""))
        return {"application": with_documents(app_), "policy": policy.to_dict()}

    # -- payouts off the protocol -------------------------------------------

    # -- balance coming in ------------------------------------------------

    @app.get("/api/funding")
    async def funding_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        """How to add balance here, and every request this address has made."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        return {"how": {**funding.destinations.describe(), "watched": watcher.describe()},
                "requests": [r.to_dict() for r in funding.mine(address)[:20]]}

    @app.post("/api/funding")
    async def funding_ask(request: FundingAsk, http: Request, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """Announce a transfer: the reply carries where to send it and the
        reference to write on it."""
        guard(http, "funding", limit=10, window=600.0)
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        verdict = pipeline.check(Action(stage="funding", address=address, amount=float(request.amount or 0.0),
                                        wallet=(request.sender or "").strip()))
        if not verdict.allowed:
            raise refused_by_policy(verdict)
        try:
            with money:
                req = funding.request(address, request.model_dump())
        except FundingError as error:
            raise Refused(422, str(error)) from error
        return {"request": req.to_dict(), "how": funding.destinations.describe()}

    @app.post("/api/funding/{request_id}/cancel")
    async def funding_cancel(request_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        try:
            with money:
                req = funding.cancel(address, request_id[:32])
        except FundingError as error:
            raise Refused(409, str(error)) from error
        return {"request": req.to_dict()}

    def give_papers(holder: str, policy: Any, contract_text: str, contract_hash: str,
                    *, held: bool = False) -> None:
        """Put the confirmation, the terms and the withdrawal notice in the
        buyer's box.

        There is no email address to send them to, so this is the giving: the
        order confirmed without delay (6563 m.4(1)), the terms as accepted,
        and the reminder of the right to withdraw. The reminder is written
        whether or not the information went out a day ahead, because a
        purchase made in one sitting never is, and Directive (EU) 2023/2673
        answers that case with a reminder within the day.

        A policy stands whether or not this succeeds; a missing paper is
        logged, not raised at the buyer.
        """
        try:
            from ..protocol.cancellation import withdrawal as withdrawal_of
            reference = policy.policy_id
            when = dt.datetime.fromtimestamp(policy.bought_at, dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC")
            what = policy.peril.title_for(policy.subject)
            where = policy.peril.describe_subject(policy.subject)
            money = f"{policy.premium:,.2f} USDC"
            papers.give(
                holder, "confirmation",
                f"Your order, {reference}",
                (f"{what}: {where}. Cover of {policy.limit:,.0f} USDC for {policy.term_days:g} days, "
                 f"for {money}. Ordered {when}."
                 + (" The premium is held, not taken, until the company that would issue it has decided."
                    if held else " The cover is in force and registered on the chain.")),
                about=reference)
            if contract_text:
                papers.give(holder, "terms", f"The contract you accepted, {reference}",
                            contract_text, about=reference, terms_hash=contract_hash or "")
            right = withdrawal_of(policy)
            if right.get("days"):
                until = (dt.datetime.fromtimestamp(right["until"], dt.timezone.utc).strftime("%d %b %Y")
                         if right.get("until") else "")
                papers.give(
                    holder, "withdrawal", f"Your right to withdraw, {reference}",
                    (f"You may withdraw from this contract within {right['days']:g} days, "
                     + (f"until {until}, " if until else "")
                     + f"under {right['law']}. Cancel it on the My cover page; what comes back is "
                       f"due within {right['refund_within_days']:g} days of the notice. "
                       "Nothing needs to be said about why."),
                    about=reference)
        except Exception:      # a paper is a copy; the cover is the thing
            logger.exception("could not write the papers for %s", getattr(policy, "policy_id", "?"))

    @app.get("/api/operator/funnel")
    async def operator_funnel(days: int = Query(30, ge=1, le=400),
                              token: str | None = Depends(bearer),
                              operator: str | None = Header(None, alias="x-operator-token")) -> dict[str, Any]:
        """How many got as far as each stage. Counts of requests, never of
        people: this protocol cannot tell two requests from one buyer apart
        and has nothing that could be made to."""
        reviewer_of(operator, token)
        return {**counting.funnel(days),
                "by_day": [d.to_dict() for d in counting.since(days)]}

    @app.get("/api/papers")
    async def papers_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The list, without the words: the box is drawn from this."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        mine = papers.mine(address)
        return {"papers": [p.summary() for p in mine],
                "unread": sum(1 for p in mine if not p.opened_at)}

    @app.get("/api/papers/{paper_id}")
    async def paper_open(paper_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """One paper, and the note that it was opened. Opening is the moment
        worth recording, so reading it is what records it."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        try:
            return {"paper": papers.open(address, paper_id).to_dict()}
        except PaperError as error:
            raise HTTPException(404, str(error)) from error

    # -- the profile: wallets and an X account joined to this address --------

    def profile_of(address: str) -> dict[str, Any]:
        via = "privy" if address in accounts._by_user.values() else "device"
        return {"address": address, "via": via,
                "links": [l.to_dict() for l in links.mine(address)],
                "payout": payouts.preference(address).to_dict(),
                "x_enabled": privy_verifier is not None}

    # -- the things a person owns, for filling a purchase -----------------------

    @app.get("/api/assets")
    async def assets_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        return {"assets": [a.to_dict() for a in assets.mine(address)]}

    @app.post("/api/assets")
    async def assets_save(body: dict[str, Any], http: Request, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """Write a home, a car or a field down, or change one. Behind the
        session: it moves no money and is seen by its owner alone."""
        guard(http, "auth", limit=30, window=60.0)
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        if not isinstance(body, dict) or len(json.dumps(body)) > 4000:
            raise Refused(422, "that is not an entry")
        try:
            with money:
                item = assets.save(address, body, clean_address=clean_address)
        except AssetError as error:
            raise Refused(422, str(error)) from error
        return {"asset": item.to_dict(), "assets": [a.to_dict() for a in assets.mine(address)]}

    @app.post("/api/assets/{asset_id}/remove")
    async def assets_remove(asset_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        try:
            with money:
                assets.remove(address, asset_id[:24])
        except AssetError as error:
            raise Refused(404, str(error)) from error
        return {"assets": [a.to_dict() for a in assets.mine(address)]}

    @app.get("/api/profile")
    async def profile(token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        return profile_of(address)

    @app.post("/api/profile/links/start")
    async def profile_link_start(request: WalletLinkStart, http: Request,
                                 token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The text a Solana or Ethereum wallet signs to be linked here."""
        guard(http, "auth", limit=30, window=60.0)
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        try:
            return links.start(address, request.kind, request.address)
        except (LinkError, PayoutError) as error:
            raise Refused(422, str(error)) from error

    @app.post("/api/profile/links")
    async def profile_link(request: WalletLinkRequest, http: Request) -> dict[str, Any]:
        """Join a wallet to the account: signed by the device over the wallet
        named, and by the wallet over the text it was given."""
        guard(http, "auth", limit=30, window=60.0)
        account = signed(request.account, "link-wallet", request.nonce, request.signature,
                         {"kind": request.kind, "address": request.address})
        verdict = pipeline.check(Action(stage="link", address=account, wallet=request.address.strip()))
        if not verdict.allowed:
            raise refused_by_policy(verdict)
        try:
            with money:
                link = links.add(account, request.kind, request.address, nonce=request.wallet_nonce,
                                 signature=request.wallet_signature)
        except (LinkError, PayoutError) as error:
            raise Refused(422, str(error)) from error
        return {"link": link.to_dict(), "profile": profile_of(account)}

    @app.post("/api/profile/links/{link_id}/remove")
    async def profile_unlink(link_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        try:
            with money:
                links.remove(address, link_id[:24])
        except LinkError as error:
            raise Refused(404, str(error)) from error
        return profile_of(address)

    @app.post("/api/profile/x")
    async def profile_x(request: XLinkRequest, http: Request, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """An X account, as Privy verified it: the identity token names the
        accounts joined to this Privy user, signed by Privy."""
        guard(http, "auth", limit=30, window=60.0)
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        if privy_verifier is None:
            raise Refused(404, "signing in through Privy is not enabled here")
        try:
            subject, joined = await run_in_threadpool(privy_verifier.linked_accounts, request.identity_token)
        except PrivyError as error:
            raise Refused(401, str(error)) from error
        if accounts.of(subject) != address:
            raise Refused(409, "that Privy sign in belongs to another account")
        x = next((a for a in joined if a.get("type") == "twitter_oauth" and a.get("username")), None)
        if x is None:
            raise Refused(422, "no X account is joined to this sign in yet")
        try:
            with money:
                link = links.add_x(address, str(x["username"]), str(x.get("subject") or ""))
        except LinkError as error:
            raise Refused(422, str(error)) from error
        return {"link": link.to_dict(), "profile": profile_of(address)}

    @app.get("/api/operator/funding")
    async def operator_funding(
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Transfers announced and not yet seen: the operator checks the bank
        statement or the explorer and confirms what arrived."""
        reviewer_of(operator, token)
        waiting = [{**r.to_dict(), "account": r.account, "sender": r.sender} for r in funding.waiting()]
        recent = sorted((r for r in funding.requests.values() if not r.open), key=lambda r: -r.created_at)[:30]
        return {"how": {**funding.destinations.describe(), "watched": watcher.describe()}, "waiting": waiting,
                "recent": [{**r.to_dict(), "account": r.account} for r in recent]}

    @app.post("/api/operator/funding/{request_id}")
    async def operator_funding_decide(
        request_id: str, request: FundingDecision,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        reviewer = reviewer_of(operator, token)
        try:
            with money:
                if request.status == "received":
                    req = funding.confirm(request_id[:32], float(request.received or 0.0), by=reviewer,
                                          note=request.note)
                elif request.status == "cancelled":
                    req = funding.reject(request_id[:32], by=reviewer, note=request.note)
                else:
                    raise FundingError("received or cancelled")
        except FundingError as error:
            raise Refused(422, str(error)) from error
        return {"request": {**req.to_dict(), "account": req.account}}

    @app.get("/api/payouts")
    async def payouts_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        """Where your payouts go, and every one that has left for a bank."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        return {
            "preference": payouts.preference(address).to_dict(),
            "orders": [o.to_dict() for o in payouts.for_account(address)[:50]],
            **payouts.describe(),
        }

    @app.get("/api/payouts/options")
    async def payouts_options() -> dict[str, Any]:
        return payouts.describe()

    @app.post("/api/payouts/preference")
    async def payouts_choose(request: PayoutRequest, http: Request) -> dict[str, Any]:
        """Choose where payouts go. Signed over the destination itself, so a
        captured request cannot redirect someone's money elsewhere."""
        guard(http, "payout", limit=10, window=60.0)
        account = signed(request.account, "payout", request.nonce, request.signature,
                         request.terms())
        before = payouts.preferences.get(account)
        try:
            pref = payouts.set_preference(account, request.terms())
        except PayoutError as error:
            raise Refused(422, str(error)) from error
        if pref.method != "wallet":
            verdict = pipeline.check(Action(stage="cashout", address=account, destination=pref.key()))
            if not verdict.allowed:
                with payouts.lock:
                    if before is not None:
                        payouts.preferences[account] = before
                    else:
                        payouts.preferences.pop(account, None)
                raise refused_by_policy(verdict)
        return {"preference": pref.to_dict()}

    @app.post("/api/payouts/cashout")
    async def payouts_cashout(request: CashoutRequest, http: Request) -> dict[str, Any]:
        """Send part of the balance where the payouts go: capital taken back
        from the pool, returns on it, a payout that arrived before a bank was
        chosen. The amount leaves the address now; the operator (or the rail)
        makes the transfer and marks the order, and a failed one comes back."""
        guard(http, "payout", limit=10, window=60.0)
        amount = bounded(request.amount, "amount", 0.0, MAX_LIMIT)
        account = signed(request.account, "cashout", request.nonce, request.signature,
                         {"amount": amount})
        pref = payouts.preference(account)
        if pref.method != "wallet":
            verdict = pipeline.check(Action(stage="cashout", address=account,
                                            destination=pref.key(), amount=amount))
            if not verdict.allowed:
                raise refused_by_policy(verdict)
        try:
            with money:
                order = payouts.cashout(account, amount)
        except WalletError as error:
            raise Refused(402, safe_detail(error, fallback="insufficient balance")) from error
        except PayoutError as error:
            raise Refused(422, str(error)) from error
        return {"order": order.to_dict(), "wallet": wallets.require(account).as_dict()}

    @app.post("/api/payouts/callback")
    async def payouts_callback(request: Request) -> dict[str, Any]:
        """A payment partner reporting what happened to an order, signed with
        the secret this server shares with it."""
        import hashlib as _hashlib
        import hmac as _hmac

        if not rail_secret:
            raise Refused(404, "not found")
        raw = await request.body()
        given = request.headers.get("x-clause-signature", "")
        expected = _hmac.new(rail_secret.encode(), raw, _hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(given, expected):
            raise Refused(401, "not authorised")
        try:
            body = RailCallback.model_validate_json(raw)
            order = payouts.settle(body.order_id, body.status, reference=body.reference,
                                   note=body.note, by="rail")
        except (PayoutError, ValueError) as error:
            raise Refused(422, safe_detail(error, fallback="that report was refused")) from error
        return {"order": order.to_dict()}

    @app.get("/api/operator/payouts")
    async def operator_payouts(
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Orders waiting for a transfer, with the full destination: whoever
        makes the transfer has to see where it goes."""
        reviewer_of(operator, token)
        companies = {c.address: c for c in registry.carriers.values() if c.address}
        rows = []
        for order in payouts.open_orders():
            pref = payouts.preferences.get(order.account)
            row = {**order.to_dict(), "account": order.account,
                   "pay_to": pref.destination() if pref else None, "company": None, "name_check": None}
            company = companies.get(order.account)
            if company is not None:
                # Money a company takes out should reach an account in the
                # company's own name; whoever makes the transfer sees whether
                # the name on the bank account is the registered one.
                row["company"] = company.name
                if pref is not None and pref.method == "bank":
                    row["name_check"] = "match" if kyb.name_match(company.name, pref.holder_name) >= 0.6 else "mismatch"
            rows.append(row)
        recent = sorted((o for o in payouts.orders.values() if o.status in ("paid", "failed")),
                        key=lambda o: -o.created_at)[:30]
        return {"rail": payouts.rail.name, "open": rows, "recent": [o.to_dict() for o in recent]}

    @app.post("/api/operator/payouts/{order_id}")
    async def operator_payout_decide(
        order_id: str, request: PayoutDecision,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        reviewer = reviewer_of(operator, token)
        try:
            with money:
                order = payouts.settle(order_id, request.status, reference=request.reference,
                                       note=request.note, by=reviewer)
        except PayoutError as error:
            raise Refused(409, str(error)) from error
        return {"order": order.to_dict()}

    # -- partners: cover sold inside someone else's product ------------------

    def partner_of(key: str | None, authorization: str | None) -> Any:
        supplied = key or (authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None)
        try:
            return partners.authenticate(supplied)
        except PartnerError as error:
            raise Refused(401, str(error)) from error

    def partner_policy(partner: Any, policy: Any) -> dict[str, Any]:
        row = policy.to_dict()
        meta = policy.metadata or {}
        row["external_ref"] = meta.get("external_ref")
        row["commission"] = round(float(meta.get("commission", 0.0)), 2)
        row["proof"] = f"/api/lineage/{policy.policy_id}"
        return row

    @app.post("/api/operator/partners")
    async def operator_partner_create(
        request: PartnerCreate,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Admit a partner. The key and the webhook secret are shown once."""
        reviewer = reviewer_of(operator, token)
        unknown = [p for p in request.perils if p not in REGISTRY]
        if unknown:
            raise Refused(422, "unknown peril: " + ", ".join(unknown))
        try:
            partner, key = partners.create(
                name=request.name, commission=request.commission, perils=request.perils,
                countries=request.countries, webhook_url=request.webhook_url, created_by=reviewer)
        except PartnerError as error:
            raise Refused(422, str(error)) from error
        with money:
            wallets.connect(partner.account, fund=False, custody="partner")
            if request.fund > 0 and settings.faucet:
                wallets.credit(partner.account, min(request.fund, 1_000_000.0), "demonstration", kind="faucet")
        return {"partner": partner.to_dict(), "api_key": key,
                "webhook_secret": partner.webhook_secret,
                "note": "the key is shown once; only its hash is kept"}

    @app.get("/api/operator/partners")
    async def operator_partners(
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        reviewer_of(operator, token)
        rows = []
        for partner in partners.partners.values():
            account = wallets.get(partner.account)
            rows.append({**partner.to_dict(), "balance": round(account.balance, 2) if account else 0.0,
                         "deliveries": partners.deliveries(partner.partner_id, 5)})
        return {"partners": rows}

    @app.post("/api/operator/partners/{partner_id}/{action}")
    async def operator_partner_action(
        partner_id: str, action: str,
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        reviewer_of(operator, token)
        try:
            partner = partners.require(partner_id)
        except PartnerError as error:
            raise Refused(404, str(error)) from error
        if action == "suspend":
            partner.status = "suspended"
            return {"partner": partner.to_dict()}
        if action == "activate":
            partner.status = "active"
            return {"partner": partner.to_dict()}
        if action == "rotate":
            partner, key = partners.rotate(partner_id)
            return {"partner": partner.to_dict(), "api_key": key}
        raise Refused(404, "not found")

    @app.get("/api/partner/v1/me")
    async def partner_me(
        key: str | None = Header(None, alias="x-clause-key"),
        authorization: str | None = Header(None),
    ) -> dict[str, Any]:
        partner = partner_of(key, authorization)
        account = wallets.get(partner.account)
        return {"partner": partner.to_dict(),
                "balance": round(account.balance, 2) if account else 0.0,
                "deliveries": partners.deliveries(partner.partner_id, 20)}

    @app.post("/api/partner/v1/quote")
    async def partner_quote(
        request: QuoteRequest, http: Request,
        key: str | None = Header(None, alias="x-clause-key"),
        authorization: str | None = Header(None),
    ) -> dict[str, Any]:
        """A price for a customer, with what the partner keeps of it."""
        partner = partner_of(key, authorization)
        guard(http, "partner-quote", limit=60, window=60.0)
        answer = await price(request)
        commission = Partners.commission_on(partner, answer["premium"], answer.get("expense_load", 0.0))
        return {**answer, "partner": {"commission": round(commission, 2),
                                       "net_cost": round(answer["premium"] - commission, 2)}}

    @app.post("/api/partner/v1/policies")
    async def partner_bind(
        request: PartnerBind, http: Request,
        key: str | None = Header(None, alias="x-clause-key"),
        authorization: str | None = Header(None),
    ) -> dict[str, Any]:
        """Bind cover for a customer. Idempotent on external_ref: sending the
        same reference again returns the policy already bound, so a retry
        after a timeout can never buy twice."""
        partner = partner_of(key, authorization)
        guard(http, "partner-bind", limit=60, window=60.0)
        ref = request.external_ref.strip()
        with partners.lock:
            existing = partner.refs.get(ref)
            if existing == "binding":
                raise Refused(409, "that reference is being bound right now")
            if existing and existing in pool.policies:
                return {"policy": partner_policy(partner, pool.policies[existing]), "replayed": True}
            # Reserved, so two requests with one reference cannot both bind.
            partner.refs[ref] = "binding"
        try:

            subject = clean_subject(request.subject)
            limit = bounded(request.limit, "limit", MIN_LIMIT, MAX_LIMIT)
            term_days = bounded(request.term_days, "term_days", MIN_TERM_DAYS, MAX_TERM_DAYS)
            value_at_risk = bounded(request.interest.value_at_risk, "value_at_risk", MIN_LIMIT, MAX_LIMIT)
            size = clean_subject(request.interest.size) if request.interest.size is not None else None
            try:
                country = get_peril(request.peril).risk_country(subject) or request.interest.country.upper()
                partners.allows(partner, request.peril, country)
            except PartnerError as error:
                raise Refused(403, str(error)) from error
            except (KeyError, ValueError) as error:
                raise Refused(422, "unknown peril") from error

            # Who the cover belongs to.
            if request.beneficiary.address:
                holder = looks_like_address(request.beneficiary.address)
                wallets.connect(holder, fund=False)
            elif request.beneficiary.payout:
                holder = beneficiary_address(partner.partner_id, ref)
                wallets.connect(holder, fund=False, custody="partner-customer")
            else:
                raise Refused(422, "say who the cover belongs to: the customer's address, "
                                   "or the bank account or mobile wallet their payouts go to")
            if request.beneficiary.payout:
                try:
                    payouts.set_preference(holder, request.beneficiary.payout)
                except PayoutError as error:
                    raise Refused(422, str(error)) from error
                if payouts.preference(holder).method == "wallet" and not request.beneficiary.address:
                    raise Refused(422, "a customer without an address needs a bank account or mobile wallet")

            # The partner screened the customer; that is accepted for sanctions
            # screening on small cover and for nothing else.
        except BaseException:
            with partners.lock:
                if partner.refs.get(ref) == "binding":
                    partner.refs.pop(ref, None)
            raise
        vouched = frozenset({"sanctions_clear"}) if limit <= PARTNER_SCREENED_LIMIT else frozenset()
        try:
            policy, armed, ruling = await issue(
                holder=holder, peril=request.peril, subject=subject, limit=limit,
                term_days=term_days, declared=request.interest, size=size,
                value_at_risk=value_at_risk, settlement="stablecoin",
                attestations=request.attestations, max_premium=request.max_premium,
                payer=partner.account, satisfied=vouched,
                metadata={"partner": partner.partner_id, "external_ref": ref,
                          "sold_by": partner.name},
                commission_to=partner.account, commission_to_partner=partner,
            )
        except BaseException:
            with partners.lock:
                if partner.refs.get(ref) == "binding":
                    partner.refs.pop(ref, None)
            raise
        partners.record(partner, ref, policy, float(policy.metadata.get("commission", 0.0)))
        partners.notify(partner, {"type": "policy.bound", "policy_id": policy.policy_id,
                                  "external_ref": ref, "premium": round(policy.premium, 2),
                                  "limit": round(policy.limit, 2)})
        return {"policy": partner_policy(partner, policy), "compliance": ruling.to_dict()}

    @app.get("/api/partner/v1/policies")
    async def partner_policies(
        external_ref: str | None = Query(None, max_length=64),
        key: str | None = Header(None, alias="x-clause-key"),
        authorization: str | None = Header(None),
    ) -> dict[str, Any]:
        partner = partner_of(key, authorization)
        ids = ([partner.refs[external_ref]] if external_ref and external_ref in partner.refs
               else [] if external_ref else list(partner.refs.values()))
        rows = [partner_policy(partner, pool.policies[i]) for i in ids if i in pool.policies]
        rows.sort(key=lambda r: r["bought_at"], reverse=True)
        return {"count": len(rows), "items": rows[:200]}

    @app.get("/api/partner/v1/policies/{policy_id}")
    async def partner_policy_one(
        policy_id: str,
        key: str | None = Header(None, alias="x-clause-key"),
        authorization: str | None = Header(None),
    ) -> dict[str, Any]:
        partner = partner_of(key, authorization)
        found = pool.policies.get(policy_id)
        if found is None or (found.metadata or {}).get("partner") != partner.partner_id:
            raise HTTPException(404, f"no policy {policy_id}")
        return {"policy": partner_policy(partner, found), "lineage": chain.lineage(policy_id)}

    # -- Rider's mandate ------------------------------------------------------

    @app.get("/api/mandate")
    async def mandate_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        current = mandates.current(address)
        return {"mandate": current.to_dict() if current else None,
                "rider_can_buy": bool(rider_key_hash and rider is not None and rider.can_buy),
                "cooling_off_hours": COOLING_OFF_HOURS}

    @app.post("/api/mandate")
    async def mandate_sign(request: MandateRequest, http: Request) -> dict[str, Any]:
        """Let Rider buy cover for this address, inside limits signed here.

        The token that comes back is shown once and is held by the browser.
        It authorises nothing beyond these terms, and a new mandate or a
        revocation ends it."""
        guard(http, "mandate", limit=10, window=60.0)
        try:
            terms = parse_terms(request.model_dump(), set(REGISTRY))
        except MandateError as error:
            raise Refused(422, str(error)) from error
        account = signed(request.account, "mandate", request.nonce, request.signature, terms)
        presented = []
        for body in request.attestations:
            try:
                presented.append(Attestation(
                    subject=account, claim=Claim(body.claim), verifier_id=body.verifier_id,
                    issued_at=finite(body.issued_at, "issued_at"),
                    expires_at=finite(body.expires_at, "expires_at"),
                    country=body.country, signature=body.signature))
            except ValueError as error:
                raise Refused(422, "that is not an attestation this protocol knows") from error
        need = eligibility.requirement(limit=terms["max_limit_per_policy"], professional=False,
                                       country=request.country.upper())
        standing = eligibility.check(address=account, attestations=presented, requirement=need)
        if not standing.ok:
            raise HTTPException(451, {"reasons": [
                "before Rider can buy for you, you need: "
                + ", ".join(c.value.replace("_", " ") for c in standing.missing)] + list(standing.reasons),
                "eligibility": standing.to_dict()})
        held = tuple(sorted({a.claim.value for a in standing.held}))
        try:
            mandate, token = mandates.create(
                account, terms, country=request.country, claims=held,
                claims_expire_at=min((a.expires_at for a in standing.held), default=None))
        except MandateError as error:
            raise Refused(422, str(error)) from error
        return {"mandate": mandate.to_dict(), "token": token,
                "note": "keep this on this device; it is shown once"}

    @app.post("/api/mandate/revoke")
    async def mandate_revoke(request: CancelRequest, http: Request) -> dict[str, Any]:
        guard(http, "mandate", limit=10, window=60.0)
        account = signed(request.account, "mandate", request.nonce, request.signature,
                         {"revoke": True})
        return {"revoked": mandates.revoke(account)}

    @app.post("/api/rider/purchase")
    async def rider_purchase(
        request: RiderPurchase, http: Request,
        rider_key: str | None = Header(None, alias="x-clause-rider-key"),
        authorization: str | None = Header(None),
    ) -> dict[str, Any]:
        """Rider buying under a mandate. Reachable only with the key the
        Latch holds and injects, and only within the mandate's signed terms."""
        import hashlib as _hashlib
        import hmac as _hmac

        if not rider_key_hash:
            raise Refused(404, "not found")
        supplied = rider_key or (authorization[7:] if authorization and authorization.lower().startswith("bearer ") else "")
        digest = _hashlib.sha256((supplied or "").encode()).hexdigest()
        if not _hmac.compare_digest(digest, rider_key_hash):
            raise Refused(401, "not authorised")
        guard(http, "rider-buy", limit=10, window=60.0)
        try:
            mandate = mandates.authenticate(request.mandate_token)
            limit = bounded(request.limit, "limit", MIN_LIMIT, MAX_LIMIT)
            ceiling = mandates.check(mandate, peril=request.peril, limit=limit)
        except MandateError as error:
            raise Refused(403, str(error)) from error
        if request.max_premium is not None:
            ceiling = min(ceiling, float(request.max_premium))
        subject = clean_subject(request.subject)
        term_days = bounded(request.term_days, "term_days", MIN_TERM_DAYS, MAX_TERM_DAYS)
        value_at_risk = bounded(request.interest.value_at_risk, "value_at_risk", MIN_LIMIT, MAX_LIMIT)
        size = clean_subject(request.interest.size) if request.interest.size is not None else None
        declared = request.interest.model_copy(update={"country": mandate.country})
        policy, armed, ruling = await issue(
            holder=mandate.account, peril=request.peril, subject=subject, limit=limit,
            term_days=term_days, declared=declared, size=size, value_at_risk=value_at_risk,
            settlement="stablecoin", attestations=[], max_premium=ceiling,
            satisfied=frozenset(mandate.claims),
            metadata={"bought_by": "rider", "mandate": mandate.mandate_id,
                      "cancel_until": time.time() + COOLING_OFF_HOURS * 3600.0},
        )
        mandates.record(mandate, policy)
        return {"policy": policy.to_dict(), "mandate": mandate.to_dict()}

    @app.get("/api/policies/{policy_id}/cancellation")
    async def policy_cancellation(policy_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """Whether this policy can be cancelled now, and what would come back."""
        from ..protocol.cancellation import assess
        address = session_of(token)
        found = pool.policies.get(policy_id)
        if found is None or address is None or found.holder != address:
            raise HTTPException(404, f"no policy {policy_id}")
        return assess(found)

    @app.get("/api/cancellation/terms")
    async def cancellation_terms(country: str = Query("", max_length=2),
                                 peril: str = Query("", max_length=32),
                                 term_days: float = Query(365, gt=0, le=MAX_TERM_DAYS)) -> dict[str, Any]:
        """What a buyer can do after buying, before they buy."""
        from ..protocol.cancellation import MISTAKE_SECONDS, UNFORESEEABLE, cooling_off_for
        rule = cooling_off_for(country)
        return {"mistake_hours": MISTAKE_SECONDS / 3600, "cooling_off_days":
                rule.days if term_days > rule.short_cover_days else 0,
                "law": rule.law, "statutory": rule.statutory,
                "pro_rata_after": peril in UNFORESEEABLE}

    @app.post("/api/policies/{policy_id}/cancel")
    async def policy_cancel(policy_id: str, request: CancelRequest, http: Request) -> dict[str, Any]:
        """Cancel at the holder's request: signed, and on the terms assess() gives."""
        from ..protocol.cancellation import assess  # noqa: F811
        guard(http, "cancel", limit=10, window=60.0)
        account = signed(request.account, "cancel", request.nonce, request.signature,
                         {"policy_id": policy_id})
        found = pool.policies.get(policy_id)
        if found is None or found.holder != account:
            raise HTTPException(404, f"no policy {policy_id}")
        with money:
            terms = assess(found)
            if not terms["allowed"]:
                raise Refused(409, terms["reason"])
            try:
                refund = pool.cancel(found, refund=terms["refund"],
                                     note=f"cancelled at the holder's request: {terms['reason']}")
            except PoolError as error:
                raise Refused(409, safe_detail(error, fallback="that policy cannot be cancelled")) from error
            chain.withdraw(found)
            if terms["basis"] in ("mistake", "rider", "cooling_off"):
                refund += return_fee(found)
            if found.metadata.get("carrier"):
                registry.reconcile(pool.policies.values())
        meta = found.metadata or {}
        if meta.get("mandate"):
            mandates.release(meta["mandate"], refund)
        partner = partners.partners.get(meta.get("partner", ""))
        if partner is not None:
            partners.notify(partner, {"type": "policy.cancelled", "policy_id": policy_id,
                                      "external_ref": meta.get("external_ref"),
                                      "refund": round(refund, 2)})
        # The notice, and what is due when: the rules give thirty days to pay
        # back what comes back; here it went back in the same step.
        from ..protocol.cancellation import REFUND_WITHIN_DAYS
        notified = time.time()
        found.metadata["withdrawal"] = {"notified_at": notified, "basis": terms["basis"], "refund": round(refund, 2),
                                        "refund_due_by": notified + REFUND_WITHIN_DAYS * 86400.0,
                                        "refunded_at": notified if refund > 0 else None}
        return {"policy": found.to_dict(), "refund": round(refund, 2), "basis": terms["basis"],
                "withdrawal": found.metadata["withdrawal"]}

    # -- the pool ---------------------------------------------------------

    @app.get("/api/pool")
    async def pool_summary() -> dict[str, Any]:
        return {
            **pool.summary(),
            "providers": [p.to_dict() for p in pool.providers.values()],
        }

    @app.get("/api/pool/risk")
    async def pool_risk() -> dict[str, Any]:
        return {**pool.risk_view(), "declined": list(reversed(app.state.declined))[:8]}

    @app.get("/api/pool/ledger")
    async def pool_ledger(limit: int = Query(60, ge=1, le=500)) -> dict[str, Any]:
        entries = [entry.to_dict() for entry in pool.ledger[-limit:]][::-1]
        return {"items": entries}

    @app.post("/api/pool/deposit")
    async def deposit(request: CapitalRequest, http: Request) -> dict[str, Any]:
        """Put capital behind the book. Signed, because it moves money."""
        guard(http, "capital", limit=10, window=60.0)
        amount = bounded(request.amount, "amount", MIN_LIMIT, MAX_LIMIT)
        terms: dict[str, Any] = {"amount": amount}
        if request.tranche is not None:
            terms["tranche"] = request.tranche
        account = signed(
            request.account, "deposit", request.nonce, request.signature, terms,
        )
        try:
            shares = await run_in_threadpool(
                lambda: pool.deposit(account, amount, tranche=request.tranche))
        except WalletError as error:
            raise Refused(402, safe_detail(error, fallback="insufficient balance")) from error
        except PoolError as error:
            raise Refused(400, safe_detail(error, fallback="that deposit was refused")) from error
        return {"shares": shares, "pool": pool.summary()}

    @app.post("/api/pool/withdraw")
    async def withdraw(request: WithdrawRequest, http: Request) -> dict[str, Any]:
        """Take capital back, but only what is not standing behind live cover."""
        guard(http, "capital", limit=10, window=60.0)
        shares = bounded(request.shares, "shares", 1e-9, MAX_LIMIT)
        terms = {"shares": shares}
        if request.tranche is not None:
            terms["tranche"] = request.tranche
        account = signed(
            request.account, "withdraw", request.nonce, request.signature, terms,
        )
        try:
            amount = await run_in_threadpool(
                lambda: pool.withdraw(account, shares, tranche=request.tranche))
        except PoolError as error:
            raise Refused(409, safe_detail(error, fallback="that withdrawal was refused")) from error
        return {"amount": amount, "pool": pool.summary()}

    # -- the chain --------------------------------------------------------

    @app.get("/api/chain")
    async def chain_state() -> dict[str, Any]:
        return {
            "stats": chain.stats(),
            "pending": chain.pending(),
            "settlements": chain.recent_settlements(30),
            "blocks": chain.recent_blocks(80),
            "aggregations": chain.recent_aggregations(12),
        }

    @app.get("/api/chain/readings")
    async def readings() -> dict[str, Any]:
        return {"items": chain.edge_readings()}

    @app.post("/api/chain/inject")
    async def inject(
        reference: str = Query(..., max_length=256),
        field: str = Query(..., max_length=48),
        value: float = Query(...),
        final: bool = Query(True),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Attest a value on a source, to demonstrate settlement on demand.

        A catastrophe arriving on its own schedule is the honest way to watch
        this protocol, and also a poor way to show it to anyone in the time
        they have. This writes a reading the same way the simulated world
        would, and everything downstream runs untouched: the chain still
        evaluates the predicates, the pool still checks it can pay, and the
        payout is still the one the policy's structure specifies.
        """
        settings.require_operator(operator)
        finite(value, "value")
        reading = chain.attest(reference, field, value, final=final)
        if reading is None:
            raise Refused(404, "no such source")
        return {
            "reference": reference,
            "fields": dict(reading.fields),
            "aggregations": chain.recent_aggregations(4),
        }

    @app.post("/api/chain/silence")
    async def silence(
        reference: str = Query(..., max_length=256),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """Stop a source publishing, to show what the protocol does about it.

        This is here because the failure it triggers is the one parametric
        designs usually leave undefined, and a demo that cannot reach it is
        hiding the most important part.
        """
        settings.require_operator(operator)
        if not chain.silence(reference):
            raise Refused(404, "no such source")
        return {"silenced": reference}

    # -- live -------------------------------------------------------------

    @app.get("/api/stream")
    async def stream(http: Request) -> StreamingResponse:
        """The live feed. Capped, because each open stream costs a simulation.

        The pool view on this stream runs a full capital calculation every few
        seconds, per connected client. Without a cap, opening connections is a
        cheap way to multiply the server's work by however many you like.
        """
        guard(http, "stream", limit=6, window=60.0)
        if streams["open"] >= MAX_STREAM_CLIENTS:
            raise Refused(503, "too many live connections; try again shortly")

        async def events() -> AsyncIterator[bytes]:
            last_height = 0
            last_slow = 0.0
            streams["open"] += 1
            try:
                while True:
                    stats = chain.stats()
                    now = time.time()

                    if stats["height"] != last_height:
                        last_height = stats["height"]
                        yield _sse(
                            "tick",
                            {
                                "stats": stats,
                                "settlements": chain.recent_settlements(12),
                                "blocks": chain.recent_blocks(60),
                                "pending": chain.pending(),
                            },
                        )

                    if now - last_slow > 4.0:
                        last_slow = now
                        yield _sse(
                            "pool",
                            {
                                "pool": pool.summary(),
                                "risk": pool.risk_view(),
                            },
                        )

                    await asyncio.sleep(0.4)
            except asyncio.CancelledError:
                return
            finally:
                streams["open"] = max(0, streams["open"] - 1)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "cache-control": "no-cache",
                "connection": "keep-alive",
                "x-accel-buffering": "no",
            },
        )

    @app.get("/api/live/quakes")
    async def live_quakes(
        http: Request, country: str | None = Query(None, min_length=2, max_length=2)
    ) -> dict[str, Any]:
        """Earthquakes recorded in the past day, worldwide or in one country.

        Shown, not priced: nothing here enters a premium or a settlement. Each
        row links to the USGS record, which is the thing to trust over this.
        A country with fewer than a handful of events today is shown its past
        week instead, and "window" says which.
        """
        guard(http, "live", limit=60, window=60.0)
        day = await run_in_threadpool(quakes_now.read)
        code = country.upper() if country else None
        items = select_quakes(day["items"], code)
        reply = {**day, "items": items, "country": code, "window": "day"}
        if code and len(items) < QUIET_DAY:
            week = await run_in_threadpool(quakes_week.read)
            # The week holds the day, so it is shown whenever it was asked
            # for; an empty week is then said as a week, which is the truth.
            wider = select_quakes(week["items"], code)
            if len(wider) >= len(items) and week["fetched_at"]:
                reply = {**week, "items": wider, "country": code, "window": "week"}
        return reply

    weather_feeds: dict[str, Any] = {}

    @app.get("/api/live/weather")
    async def live_weather(
        http: Request, country: str | None = Query("TR", max_length=2)
    ) -> dict[str, Any]:
        """Today's rain, wind and sky at the country's main places, from
        Open-Meteo, or at a sample of the world's cities when no country is
        named. Shown, not priced: the covers settle on the sources named in
        each policy, not on a forecast."""
        from ..live import weather_feed
        guard(http, "live", limit=60, window=60.0)
        code = (country or "").upper()
        if code and len(code) != 2:
            raise Refused(422, "a two letter country code, or none for the world")
        feed = weather_feeds.get(code or "world")
        if feed is None:
            feed = weather_feed(code, **live_kw)
            if feed is None:
                return {"available": False, "country": code, "items": []}
            weather_feeds[code or "world"] = feed
        reply = await run_in_threadpool(feed.read)
        return {**reply, "country": code or None, "available": True,
                "attribution": "Weather data by Open-Meteo.com, CC BY 4.0"}

    @app.get("/api/live/flights")
    async def live_flights(
        http: Request, country: str | None = Query(None, min_length=2, max_length=2)
    ) -> dict[str, Any]:
        """Flight delays in force now, for the United States or one country.

        The United States comes from the FAA, the only live delay feed that is
        public and licensed for any use. Elsewhere there is a feed only when a
        FlightAware AeroAPI key is set on the server. Without one, the reply
        says there is none, with "available": false, and the page repeats it
        rather than showing an empty band as if nothing were late.
        """
        guard(http, "live", limit=60, window=60.0)
        code = country.upper() if country else None
        if code == "US" or (code is None and flights_world is None):
            feed = await run_in_threadpool(flights_now.read)
            return {**feed, "country": code, "available": True}
        if code is None:
            feed = await run_in_threadpool(flights_world.read)
            return {**feed, "items": feed["items"][:40], "country": None, "available": True}
        if flights_world is None:
            return {"items": [], "country": code, "available": False, "source": None,
                    "coverage": "there is no public live flight delay feed for this country",
                    "stale": False, "fetched_at": None, "age_seconds": None}
        feed = await run_in_threadpool(flights_world.read)
        items = [row for row in feed["items"] if row.get("country") == code][:40]
        return {**feed, "items": items, "country": code, "available": True}

    # -- the public chain beside this one -----------------------------------

    @app.get("/api/anchor")
    async def anchor_status() -> dict[str, Any]:
        """What the public chain has been told: the contracts, the signer,
        the last root of the book and the recent intents with their
        transactions. Readable by anyone; it is the public record's index."""
        return anchor.status()

    @app.get("/api/policies/{policy_id}/anchor")
    async def policy_anchor(policy_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """One policy on the public chain: its token's mint and burn, its
        settlement, and its proof of inclusion in the last anchored root,
        with every hash a person needs to check it themselves. The holder
        also sees where the token is held and which of their own wallets
        it could go to."""
        found = pool.policies.get(policy_id)
        if found is None:
            raise HTTPException(404, f"no policy {policy_id}")
        out = {"mode": anchor.config.mode, "chain": anchor.status()["chain"],
               "contracts": anchor.status()["contracts"],
               "proof": anchor.proof(policy_id), "held": anchor.held_by(policy_id), **anchor.for_policy(policy_id)}
        if session_of(token) == found.holder:
            out["wallets"] = [checksum_evm(a) for a in links.wallets_of(found.holder, "evm")]
        return out

    @app.post("/api/policies/{policy_id}/anchor/claim")
    async def policy_anchor_claim(policy_id: str, request: ClaimRequest,
                                  token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The holder asks for the token in their own wallet: one they have
        linked on their profile, proved by its signature. Not yet sent, the
        mint is pointed there; already on the chain, it is burned and
        minted again to the wallet, in that order."""
        found = pool.policies.get(policy_id)
        if found is None or session_of(token) != found.holder:
            raise HTTPException(404, f"no policy {policy_id}")
        linked = [checksum_evm(a) for a in links.wallets_of(found.holder, "evm")]
        if not linked:
            raise Refused(409, "link an Ethereum wallet on your profile first; the token goes only to a wallet you have proved is yours")
        wanted = request.address or linked[0]
        if wanted.lower() not in {a.lower() for a in linked}:
            raise Refused(409, "that is not one of your linked wallets")
        if "token" not in (found.metadata or {}) or (found.metadata["token"] or {}).get("burned_at"):
            raise Refused(409, "this policy has no live token")
        queued = anchor.claim(found, wanted)
        return {"queued": [dict(i.to_dict(), tx_url=anchor.tx_url(i.tx_hash)) for i in queued],
                "held": anchor.held_by(policy_id), "wallet": checksum_evm(wanted)}

    @app.post("/api/operator/anchor/run")
    async def anchor_run(
        token: str | None = Depends(bearer),
        operator: str | None = Header(None, alias="x-operator-token"),
    ) -> dict[str, Any]:
        """One cycle now rather than on the timer: a root if the book moved,
        then whatever is pending, sent."""
        reviewer_of(operator, token)
        report = await asyncio.to_thread(anchor.run_once)
        return {"report": report, "anchor": anchor.status()}

    # -- the calculation agent's rulebook ---------------------------------------

    RULEBOOK_SUBJECTS = {
        "earthquake": {"location": "IST-KADIKOY", "radius_km": 50},
        "storm": {"latitude": 40.99, "longitude": 29.03, "radius_km": 50, "place": "Kadıköy"},
        "vehicle_flood": {"latitude": 40.99, "longitude": 29.03, "radius_km": 50, "place": "Kadıköy"},
        "drought": {"station": "TR-KONYA", "distance_km": 6.0, "hectares": 50.0},
        "flight_delay": {"route": "TK-IST-LHR", "flight_number": "TK1979", "departure_date": _soon()},
    }

    @app.get("/api/rulebook")
    async def rulebook_all() -> dict[str, Any]:
        """How a reading becomes the number a policy settles on, peril by
        peril: sources and their order, what is final and when it is
        frozen, the tests, the chain's attestation rule, the silence
        deadline, the objection window, the successor rule. The same text
        is section 10 of every contract."""
        from ..protocol import rulebook
        out = {}
        for key in rulebook.RULES:
            deadline, missing = None, ""
            try:
                peril_ = get_peril(key)
                src = peril_.data_source(peril_.validate_subject(RULEBOOK_SUBJECTS.get(key, {})))
                deadline, missing = src.settlement_deadline_days, src.on_missing_data
            except Exception:
                pass
            out[key] = rulebook.for_peril(key, deadline_days=deadline, on_missing_data=missing,
                                          attestation=chain.aggregator.describe())
        return {"version": rulebook.VERSION, "attestation": chain.aggregator.describe(),
                "objection_days": rulebook.OBJECTION_DAYS, "perils": out}

    # -- complaints: on the policy, on the company's clock, to the ombudsman ----

    def complaint_role(c: Any, token: str | None, operator: str | None) -> str | None:
        """Who is looking: the holder, the company it was raised against, the
        operator; or nobody, which reads as not found."""
        address = session_of(token)
        if address and address == c.holder:
            return "holder"
        carrier = registry.carriers.get(c.carrier_id)
        if address and carrier is not None and carrier.address == address:
            return "company"
        try:
            reviewer_of(operator, token)
            return "operator"
        except Exception:
            return None

    def complaint_view(c: Any) -> dict[str, Any]:
        route = route_for(c.country)
        carrier = registry.carriers.get(c.carrier_id)
        return {**c.to_dict(), "carrier": carrier.name if carrier else None,
                "route": {"body": route.body, "answer_days": route.answer_days, "note": route.note,
                          "links": [{"name": n, "url": u} for n, u in route.links]}}

    def complaint_package(c: Any) -> dict[str, Any]:
        policy = pool.policies.get(c.policy_id)
        carrier = registry.carriers.get(c.carrier_id)
        return Complaints.package(
            c, policy=policy.to_dict() if policy else None,
            contract_hash=(policy.metadata or {}).get("contract_hash") if policy else None,
            lineage=chain.lineage(c.policy_id), settlements=[x.to_dict() for x in chain.settlements if x.policy_id == c.policy_id],
            carrier={"carrier_id": carrier.carrier_id, "name": carrier.name, "domicile": carrier.domicile,
                     "contact": carrier.contact} if carrier else None)

    @app.post("/api/policies/{policy_id}/complaints")
    async def complaint_open(policy_id: str, request: ComplaintOpen, http: Request,
                             token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The holder raises a complaint on their policy. The company's time
        to answer starts now and is visible to both sides."""
        guard(http, "complaint", limit=5, window=3600.0)
        found = pool.policies.get(policy_id)
        if found is None or session_of(token) != found.holder:
            raise HTTPException(404, f"no policy {policy_id}")
        try:
            c = complaints.open(found, subject=request.subject, text=request.text)
        except ComplaintError as error:
            raise Refused(422, str(error)) from error
        return {"complaint": complaint_view(c)}

    @app.get("/api/complaints")
    async def complaints_mine(token: str | None = Depends(bearer)) -> dict[str, Any]:
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        return {"complaints": [complaint_view(c) for c in complaints.for_holder(address)]}

    @app.get("/api/complaints/{complaint_id}")
    async def complaint_read(complaint_id: str, token: str | None = Depends(bearer),
                             operator: str | None = Header(None, alias="x-operator-token")) -> dict[str, Any]:
        c = complaints.get(complaint_id)
        role = complaint_role(c, token, operator) if c else None
        if c is None or role is None:
            raise HTTPException(404, "no such complaint")
        return {"complaint": complaint_view(c), "viewer": role}

    @app.post("/api/complaints/{complaint_id}/messages")
    async def complaint_message(complaint_id: str, request: ComplaintMessage, token: str | None = Depends(bearer),
                                operator: str | None = Header(None, alias="x-operator-token")) -> dict[str, Any]:
        """A message on the thread, from whichever side is writing. The
        company's first message stops its clock."""
        c = complaints.get(complaint_id)
        role = complaint_role(c, token, operator) if c else None
        if c is None or role is None:
            raise HTTPException(404, "no such complaint")
        try:
            complaints.reply(complaint_id, who=role, text=request.text)
        except ComplaintError as error:
            raise Refused(409, str(error)) from error
        return {"complaint": complaint_view(c)}

    @app.post("/api/complaints/{complaint_id}/close")
    async def complaint_close(complaint_id: str, request: ComplaintClose, token: str | None = Depends(bearer),
                              operator: str | None = Header(None, alias="x-operator-token")) -> dict[str, Any]:
        c = complaints.get(complaint_id)
        role = complaint_role(c, token, operator) if c else None
        if c is None or role is None:
            raise HTTPException(404, "no such complaint")
        if role == "holder":
            raise Refused(409, "the holder withdraws a complaint by saying so on the thread; the company or the operator closes it")
        try:
            complaints.close(complaint_id, by=role, resolution=request.resolution)
        except ComplaintError as error:
            raise Refused(409, str(error)) from error
        return {"complaint": complaint_view(c)}

    @app.post("/api/complaints/{complaint_id}/escalate")
    async def complaint_escalate(complaint_id: str, token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The holder takes it to the ombudsman, and gets the file to attach."""
        c = complaints.get(complaint_id)
        if c is None or session_of(token) != c.holder:
            raise HTTPException(404, "no such complaint")
        try:
            complaints.escalate(complaint_id)
        except ComplaintError as error:
            raise Refused(409, str(error)) from error
        return {"complaint": complaint_view(c), "package": complaint_package(c)}

    @app.get("/api/complaints/{complaint_id}/package")
    async def complaint_file(complaint_id: str, format: str = Query("json", max_length=4),
                             token: str | None = Depends(bearer),
                             operator: str | None = Header(None, alias="x-operator-token")):
        """Everything the ombudsman's application asks for, as the record
        stands: the policy, its contract hash, the readings and settlements,
        the thread with its timestamps, and where to take it."""
        from fastapi.responses import PlainTextResponse
        c = complaints.get(complaint_id)
        role = complaint_role(c, token, operator) if c else None
        if c is None or role is None:
            raise HTTPException(404, "no such complaint")
        package = complaint_package(c)
        if format == "text":
            return PlainTextResponse(Complaints.package_text(package), media_type="text/plain; charset=utf-8",
                                     headers={"content-disposition": f'attachment; filename="{complaint_id}.txt"'})
        return package

    @app.get("/api/company/complaints")
    async def company_complaints(carrier_id: str = Query(..., max_length=80),
                                 token: str | None = Depends(bearer)) -> dict[str, Any]:
        """The company's complaints, the overdue ones first, with its clock."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        carrier = registry.carriers.get(carrier_id)
        if carrier is None or carrier.address != address:
            raise HTTPException(404, "no such company on this account")
        rows = complaints.for_carrier(carrier_id)
        return {"complaints": [complaint_view(c) for c in rows], "summary": complaints.summary(rows)}

    # -- bordereaux: what was written, what was paid, whether it adds up ------

    def bordereau_for(kind: str, carrier_id: str | None, month: str, *, private: bool) -> dict[str, Any]:
        from ..protocol import bordereaux
        names = {c.carrier_id: c.name for c in registry.carriers.values()}
        month = month or fees.months(carrier_id)[:1][0] if fees.months(carrier_id) else (month or month_of_now())
        with money:
            policies_ = list(pool.policies.values())
            risk = bordereaux.risk_bordereau(policies_, carrier_id=carrier_id, month=month, names=names, private=private)
            claims = bordereaux.claims_bordereau(policies_, list(chain.settlements), carrier_id=carrier_id, month=month)
        if kind == "risk":
            return risk
        if kind == "claims":
            return claims
        statement = fees.statement(carrier_id, month, names=names) if carrier_id else None
        if not carrier_id:
            rows = fees.statements(month, names=names)
            statement = {k: round(sum(float(r.get(k, 0.0)) for r in rows), 2) for k in
                         ("fronting_fees", "fronting_fees_returned", "platform_fees", "platform_fees_returned", "net_to_company")}
        return bordereaux.reconciliation(risk, claims, statement)

    def month_of_now() -> str:
        from ..protocol.fees import month_of
        return month_of(time.time())

    def bordereau_reply(kind: str, carrier_id: str | None, month: str, format_: str, *, private: bool):
        from ..protocol import bordereaux
        if kind not in ("risk", "claims", "reconciliation"):
            raise Refused(422, "kind is risk, claims or reconciliation")
        book = bordereau_for(kind, carrier_id, month, private=private)
        if format_ == "csv":
            from fastapi.responses import PlainTextResponse
            name = f"{carrier_id or 'all'}-{book['month']}-{kind}.csv"
            return PlainTextResponse(bordereaux.to_csv(book), media_type="text/csv; charset=utf-8",
                                     headers={"content-disposition": f'attachment; filename="{name}"'})
        return {"bordereau": book, "months": fees.months(carrier_id)}

    @app.get("/api/company/bordereaux")
    async def company_bordereaux(carrier_id: str = Query(..., max_length=80), month: str = Query("", max_length=7),
                                 kind: str = Query("risk", max_length=16), format: str = Query("json", max_length=4),
                                 token: str | None = Depends(bearer)):
        """The company's three bordereaux for a month: risk (what was bound),
        claims (what was paid, what was returned) and the reconciliation
        against the fee ledger. JSON, or CSV in the shape a bordereau desk
        loads."""
        address = session_of(token)
        if address is None:
            raise Refused(401, "sign in first")
        carrier = registry.carriers.get(carrier_id)
        if carrier is None or carrier.address != address:
            raise HTTPException(404, "no such company on this account")
        return bordereau_reply(kind, carrier_id, month, format, private=carrier.role is not Role.REINSURER)

    @app.get("/api/operator/bordereaux")
    async def operator_bordereaux(carrier_id: str = Query("", max_length=80), month: str = Query("", max_length=7),
                                  kind: str = Query("risk", max_length=16), format: str = Query("json", max_length=4),
                                  token: str | None = Depends(bearer),
                                  operator: str | None = Header(None, alias="x-operator-token")):
        reviewer_of(operator, token)
        return bordereau_reply(kind, carrier_id or None, month, format, private=False)

    @app.get("/api/operator/complaints")
    async def operator_complaints(token: str | None = Depends(bearer),
                                  operator: str | None = Header(None, alias="x-operator-token")) -> dict[str, Any]:
        reviewer_of(operator, token)
        rows = sorted(complaints.complaints.values(), key=lambda c: (c.status != "open", c.deadline_at))
        return {"complaints": [complaint_view(c) for c in rows], "summary": complaints.summary(rows)}

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        last_root = anchor.latest_root()
        return {
            "status": "ok",
            "version": __version__,
            "anchor": {"mode": anchor.config.mode, "chain": anchor.config.chain["name"],
                       "pending": sum(1 for i in anchor.intents.values() if i.status == "pending"),
                       "last_root_epoch": last_root.payload.get("epoch") if last_root else None,
                       "last_error": anchor.last_error},
            "chain": chain.stats(),
            "pool": {
                "balance": round(pool.balance, 2),
                "open_policies": len(pool.open_policies),
            },
        }

    # -- interface --------------------------------------------------------

    @app.get("/")
    async def index() -> Any:
        """The API host has no page of its own. In production the site lives
        on its own host, so a person who lands here is sent there. A
        developer running only this service has no such host, and gets the
        site out of the repository, from here."""
        from fastapi.responses import RedirectResponse
        if settings.allowed_origins:
            return RedirectResponse(settings.allowed_origins[0], status_code=302)
        page = SITE_ROOT / "index.html"
        if not page.is_file():
            raise HTTPException(500, "the site is not in this checkout")
        return FileResponse(page)

    # The site's own files: its translations, the map and the sign in bundle.
    # This is for the developer case only, and it is mounted last so that
    # every route above is matched first. In production nothing is served
    # from here: the site has a host, that host has the headers, and two
    # copies of a page on two origins is one copy too many.
    if not settings.allowed_origins and SITE_ROOT.is_dir():
        app.mount("/", StaticFiles(directory=SITE_ROOT), name="site")

    return app


_DEMO_KEYS: dict[str, Any] = {}
# Company names by id, filled by create_app so a token can name its issuer.
_CARRIER_NAMES: dict[str, str] = {}
# Where the site lives, filled by create_app so a token in a stranger's wallet
# carries a way back to the record it is about. Empty when the API is running
# on its own, and then the token simply has no outward link.
_SITE_ORIGIN = ""


# Demonstration top ups: how much one press adds, and the most an address may hold.
FAUCET_TOP_UP = 100_000.0
FAUCET_CEILING = 1_000_000.0


# The thing insured, drawn plainly, in a hundred by a hundred box. A token is
# read at the size of a thumbnail in a list of tokens, and at that size a
# generated trace says "this is a Clause policy" but not which kind. The
# subject says which kind before a word is read.
# What a marketplace puts on a filter button. The peril's full name says how it
# is measured as well as what it covers, which is a sentence, and a sentence on
# a filter button is a truncated sentence.
_PERIL_LABELS = {
    "earthquake": "Earthquake",
    "storm": "Storm",
    "drought": "Drought",
    "flight_delay": "Flight delay",
    "vehicle_flood": "Vehicle flood",
}

_PERIL_MARKS = {
    "earthquake": (
        "M14 50 50 20 86 50M24 46V84H76V46M42 84V62H58V84",          # a house
        "M50 92a26 9 0 0 0 0 0M22 90q28 10 56 0M8 96q42 14 84 0",    # ground, moving
    ),
    "storm": (
        "M10 52 50 22 90 52M22 48V84H78V48M44 84V64H58V84",          # a house
        "M2 26q16-8 30 0M2 38q24-10 42 0M2 62q12-6 22 0",            # wind across it
    ),
    "drought": (
        "M50 8v12M50 46v12M22 33h12M66 33h12M31 14l8 8M69 14l-8 8"
        "M31 52l8-8M69 52l-8-8M50 22a11 11 0 1 1 0 22 11 11 0 1 1 0-22",   # a sun
        "M4 70q46-12 92 0M4 82q46-12 92 0M4 94q46-12 92 0",           # furrows
    ),
    "flight_delay": (
        "M6 62 44 52 62 22l10 3-8 30 28 4 5 6-30 10-10 16-8-1 2-15-18 3Z",  # a plane
        "M8 88h84",                                                   # the ground it is late to
    ),
    "vehicle_flood": (
        "M16 62l8-18h52l8 18M12 62h76v14H12ZM26 76a6 6 0 1 0 12 0M62 76a6 6 0 1 0 12 0",  # a car
        "M2 84q12-7 24 0t24 0 24 0 24 0M2 94q12-7 24 0t24 0 24 0 24 0",   # water
    ),
}


# How much cover the token stands for, as a band. It is the limit and nothing
# else: a grade of size, not a grade of quality, and a small policy is a small
# policy. The metal it names is spent on the edge and on one stamp, never on
# the trace, so the card still has one loud thing and it is the state.
_TIERS = (
    (500_000.0, "DIAMOND",  "#CFEBFF", "#7FC4E8"),
    (250_000.0, "PLATINUM", "#E3E8EE", "#9AA6B4"),
    (100_000.0, "GOLD",     "#F5CD63", "#C08A15"),
    ( 25_000.0, "SILVER",   "#D3DAE2", "#8E98A6"),
    (      0.0, "BRONZE",   "#D79A66", "#8C5A31"),
)


def _tier(limit: float) -> tuple[str, str, str]:
    for floor, name, light, dark in _TIERS:
        if limit >= floor:
            return name, light, dark
    return _TIERS[-1][1], _TIERS[-1][2], _TIERS[-1][3]


def _peril_mark(key: str, x: float, y: float, size: float, colour: str) -> str:
    """The insured thing, quiet, behind the index that decides it."""
    shape = _PERIL_MARKS.get(key)
    if not shape:
        return ""
    k = size / 100.0
    body, detail = shape
    return (f'<g transform="translate({x:.0f} {y:.0f}) scale({k:.3f})" fill="none" '
            f'stroke="{colour}" stroke-width="3" stroke-linecap="round" '
            f'stroke-linejoin="round" opacity=".16">'
            f'<path d="{body}"/><path d="{detail}" opacity=".7"/></g>')


def _token_art(policy: Any, seed: int, tone: str) -> str:
    """The index this policy watches, drawn, and the line it has to cross.

    Every token used to be the same card with different words on it: eleven
    labelled fields, a sixty-four character hash nobody can read, and a
    sentence of small print. A wallet already shows the fields — that is what
    the attributes are for — so repeating them in the picture only made the
    picture a form.

    What a wallet cannot show is the shape of the bargain, so that is what the
    picture is now: the index running across the card and the level at which
    this policy starts paying, drawn as a line it either reaches or does not.
    The trace is generated from the policy id and the hash of its terms, so no
    two are alike and the drawing is a function of the contract rather than an
    ornament laid on top of it.

    Nothing here is a promise. The trace is not a forecast and is not drawn
    from any reading; it is the peril's own signature, and the only figure it
    carries is the trigger the buyer chose.
    """
    W = 840
    top, bottom = 250.0, 560.0          # the band the figure lives in
    left, right = 70.0, W - 70.0

    state = seed & 0xFFFFFFFFFFFF
    def rnd() -> float:
        """A repeatable stream: the same policy always draws the same card."""
        nonlocal state
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFF
        return state / 0xFFFFFFFFFFFF

    below = str(getattr(policy.curve.direction, "value", policy.curve.direction)) == "below"
    # Where the trigger sits in the band, and which way the trace approaches it.
    line_y = top + (bottom - top) * (0.34 if below else 0.42)

    points: list[tuple[float, float]] = []
    span = right - left
    if policy.peril_key == "earthquake":
        # quiet, then one burst that carries the whole event
        peak = 0.38 + rnd() * 0.24
        n = 78
        for i in range(n + 1):
            x = left + span * i / n
            d = abs(i / n - peak)
            envelope = max(0.0, 1.0 - (d / 0.11) ** 2)
            wobble = (rnd() - 0.5) * 10
            swing = envelope * (bottom - line_y) * 1.45 * (1 if i % 2 else -1)
            points.append((x, bottom - 40 - swing * (0.5 + rnd() * 0.6) + wobble))
    elif policy.peril_key == "drought":
        # a season that does not fill: a curve settling below the line
        n = 46
        fall = 0.55 + rnd() * 0.35
        for i in range(n + 1):
            k = i / n
            x = left + span * k
            y = top + 40 + (bottom - top - 80) * (k ** (1.0 / (0.45 + fall)))
            points.append((x, y + (rnd() - 0.5) * 7))
    elif policy.peril_key == "flight_delay":
        # scheduled, then the step the delay puts in
        n = 44
        at = 0.44 + rnd() * 0.2
        for i in range(n + 1):
            k = i / n
            x = left + span * k
            y = bottom - 60 if k < at else bottom - 60 - (bottom - line_y) * 1.25
            points.append((x, y + (rnd() - 0.5) * 5))
    elif policy.peril_key == "storm":
        # a gust train: fewer, longer swings under one rising envelope
        n = 44
        crest = 0.44 + rnd() * 0.22
        for i in range(n + 1):
            k = i / n
            x = left + span * k
            envelope = max(0.0, 1.0 - ((k - crest) / 0.46) ** 2)
            swing = envelope * (bottom - line_y) * 1.25 * (1 if i % 2 else -0.45)
            points.append((x, bottom - 50 - swing * (0.55 + rnd() * 0.5)))
    else:
        # rain on a day, and the water it leaves: the line climbs and stays up
        n = 60
        onset = 0.3 + rnd() * 0.2
        rise = 0.0
        for i in range(n + 1):
            k = i / n
            x = left + span * k
            if k > onset:
                rise = min(1.0, rise + (0.055 + rnd() * 0.05))
            points.append((x, bottom - 50 - rise * (bottom - line_y) * 1.3 + (rnd() - 0.5) * 6))

    trace = "M" + " ".join(f"{x:.1f} {max(top - 10, min(bottom + 10, y)):.1f}" for x, y in points)

    weather = ""
    if policy.peril_key == "vehicle_flood":
        drops = []
        for _ in range(34):
            x = left + span * rnd()
            y = top + (line_y - top - 20) * rnd()
            drops.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x - 3:.1f}" y2="{y + 13:.1f}"/>')
        weather = ('<g stroke="#5C6A78" stroke-width="1.6" stroke-linecap="round" opacity=".55">'
                   + "".join(drops) + '</g>')

    # The terms hash, as a bar rather than as sixty-four characters: the same
    # information, in a form that can be compared at a glance.
    digest = hashlib.sha256(str(seed).encode()).digest()
    bars = []
    for i in range(32):
        h = 6 + (digest[i] / 255.0) * 26
        bars.append(f'<rect x="{70 + i * 22:.0f}" y="{766 - h:.1f}" width="10" '
                    f'height="{h:.1f}" rx="2" fill="#2A3644"/>')

    cross = ""
    met = [(x, y) for x, y in points if (y > line_y if below else y < line_y)]
    if met:
        cx, cy = met[0]
        cross = (f'<circle cx="{cx:.1f}" cy="{line_y:.1f}" r="7" fill="{tone}" opacity=".9"/>'
                 f'<circle cx="{cx:.1f}" cy="{line_y:.1f}" r="14" fill="none" stroke="{tone}" opacity=".35"/>')

    return (
        _peril_mark(policy.peril_key, W - 322, top - 34, 240, "#E9EFF5")
        + f'<line x1="{left}" y1="{line_y:.1f}" x2="{right}" y2="{line_y:.1f}" '
        'stroke="#5C6A78" stroke-width="1.5" stroke-dasharray="7 7"/>'
        f'<path d="{trace}" fill="none" stroke="{tone}" stroke-width="2.4" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        + weather + cross + "".join(bars)
    )


def token_metadata(policy: Any) -> dict[str, Any]:
    """The policy token: the bargain as a picture, the terms as attributes.

    A wallet renders attributes itself, in the reader's own interface, so the
    image does not repeat them. What it carries instead is the one thing no
    list of traits can show: the index this cover watches and the level it has
    to reach, drawn from the policy's own id so that every token is its own.
    """
    import base64
    from html import escape

    token = policy.metadata["token"]
    meta = policy.metadata or {}
    peril = policy.peril
    what = peril.describe_subject(policy.subject)
    title = peril.title_for(policy.subject)
    unit = peril.unit_for(policy.subject)
    steps = policy.curve.describe(unit)
    carrier = meta.get("carrier")
    carrier = (_CARRIER_NAMES.get(carrier) or carrier) if carrier else None
    issuer = (meta.get("interest") or {}).get("country", "")
    status = policy.status.value
    contract_hash = str(meta.get("contract_hash") or token.get("terms_hash") or "")

    # The palette the rest of this protocol uses, so a token in a wallet and
    # the page it came from are plainly the same thing.
    tone = {"active": "#FF6A2B", "paid": "#24D3A5"}.get(status, "#7A8895")
    tier, metal_light, metal_dark = _tier(policy.limit)
    W = 840
    seed = int.from_bytes(
        hashlib.sha256((policy.policy_id + contract_hash).encode()).digest()[:8], "big")

    curve = (peril.curve_in_mm(policy.subject, policy.curve)
             if policy.peril_key == "drought" else policy.curve)
    level = curve.attachment
    trigger = (f"M{level:g}" if "magnitude" in unit
               else f"{level:g} {unit}" if unit else f"{level:g}")

    def t(x, y, text, size=14, fill="#E9EFF5", weight="400",
          family="ui-sans-serif,system-ui,sans-serif", anchor="start", spacing=0, opacity=1):
        return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
                f'font-family="{family}" text-anchor="{anchor}" letter-spacing="{spacing}" '
                f'opacity="{opacity}">{escape(str(text))}</text>')

    mono = "ui-monospace,SFMono-Regular,Menlo,monospace"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {W}">'
        '<defs>'
        f'<radialGradient id="glow" cx="50%" cy="46%" r="62%">'
        f'<stop offset="0" stop-color="{tone}" stop-opacity=".16"/>'
        '<stop offset="1" stop-color="#07090D" stop-opacity="0"/></radialGradient>'
        '<pattern id="dots" width="28" height="28" patternUnits="userSpaceOnUse">'
        '<circle cx="1" cy="1" r="1" fill="#E9EFF5" opacity=".05"/></pattern>'
        '<linearGradient id="metal" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{metal_light}"/>'
        f'<stop offset=".5" stop-color="{metal_dark}"/>'
        f'<stop offset="1" stop-color="{metal_light}"/></linearGradient>'
        '</defs>'
        f'<rect width="{W}" height="{W}" fill="#07090D"/>'
        f'<rect width="{W}" height="{W}" fill="url(#dots)"/>'
        f'<rect width="{W}" height="{W}" fill="url(#glow)"/>'
        f'<rect x="2" y="2" width="{W-4}" height="{W-4}" rx="40" fill="none" '
        'stroke="url(#metal)" stroke-width="3" opacity=".7"/>'
        f'<rect x="13" y="13" width="{W-26}" height="{W-26}" rx="31" fill="none" '
        'stroke="#1D2631" stroke-width="1.5"/>'

        # the mark, and which policy this is
        '<path d="M70 92h34l17-44 26 84 22-62 17 22h34" fill="none" stroke="#FF6A2B" '
        'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
        + f'<path d="M{W-206} 84l9-11 9 11-9 11Z" fill="url(#metal)" opacity=".9"/>'
        + t(W - 178, 90, tier, 15, "url(#metal)", "700", mono, anchor="start", spacing=4)
        + t(W - 70, 124, policy.policy_id, 19, "#8D9BA9", "500", mono, anchor="end")

        # the bargain, drawn
        + _token_art(policy, seed, tone)
        + t(70, 235, trigger, 22, "#E9EFF5", "600", mono)
        + t(70, 208, "PAYS FROM", 12, "#7A8895", "600", mono, spacing=4)

        # what it is worth, as one number
        + t(70, 664, f"{policy.limit:,.0f}", 92, "#E9EFF5", "700",
            "ui-sans-serif,system-ui,sans-serif", spacing=-3)
        + t(70, 700, f"USDC · {title}", 19, "#8D9BA9", "500")

        # the terms hash sits behind the bar above; the state, and the lock
        + f'<circle cx="77" cy="{800}" r="5" fill="{tone}"/>'
        + t(92, 805, status.upper(), 13, tone, "700", mono, spacing=3)
        + t(W - 70, 805, "NON-TRANSFERABLE", 13, "#7A8895", "600", mono, anchor="end", spacing=3)
        + '</svg>'
    )
    # Drought's subject line carries the area and the season as well as the
    # place, which is right on the page and too long for a chip. The place is
    # what belongs on the chip; the rest is in the description's first
    # sentence, where it is read in full.
    where = (peril.station(policy.subject).name
             if policy.peril_key == "drought" else what)

    # An attribute is a label a reader filters on, and every viewer shortens one
    # that does not fit. So the ladder, which is three clauses long and is the
    # substance of the bargain, is written out in the description where it is
    # read in full, and the attributes stay short enough to survive a chip.
    meta_out: dict[str, Any] = {
        "name": f"Clause policy {policy.policy_id}",
        "description": (f"{title}: {what}. Cover of {policy.limit:,.0f} USDC, paying from "
                        f"{trigger}. It pays in steps: " + "; ".join(steps) + ". "
                        "The drawing is this policy's own index and the level it "
                        "has to reach, generated from the policy id and the hash of its terms. "
                        f"Its tier, {tier.title()}, is the band the cover falls in: a grade "
                        "of size, not a grade of quality. "
                        "This token belongs to the address that bought the cover and cannot be "
                        "transferred."),
        "image": "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode(),
        "locked": True,
        "transferable": False,
        "token": token,
        "burned": bool(token.get("burned_at")),
        "attributes": [
            {"trait_type": "Tier", "value": tier.title()},
            {"trait_type": "Peril", "value": _PERIL_LABELS.get(policy.peril_key, title)},
            {"trait_type": "Where", "value": where},
            {"trait_type": "Limit (USDC)", "value": round(policy.limit, 2),
             "display_type": "number"},
            {"trait_type": "Pays from", "value": trigger},
            {"trait_type": "Status", "value": status},
            {"trait_type": "Starts", "value": int(policy.starts_at), "display_type": "date"},
            {"trait_type": "Ends", "value": int(policy.ends_at), "display_type": "date"},
            {"trait_type": "Issued by", "value": (carrier or "the Clause pool")
                + (f" ({issuer})" if issuer else "")},
            {"trait_type": "Minted in block", "value": token.get("minted_block"),
             "display_type": "number"},
            {"trait_type": "Terms hash", "value": token["terms_hash"]},
        ],
    }
    # Who holds it is not an attribute: a viewer already names the owner, and a
    # trait that differs for every token is noise in a rarity count.
    if _SITE_ORIGIN:
        meta_out["external_url"] = f"{_SITE_ORIGIN}/#/proof/{policy.policy_id}"
    return meta_out


def _seed_verifiers(engine: EligibilityEngine) -> list[str]:
    """The firms whose statements this build accepts.

    In a deployment these are the identity providers the carriers already use,
    and their public keys arrive out of band. Here they are generated at start
    so the demonstration has someone who can sign, which also means a statement
    from a previous run stops verifying when the process restarts. That is the
    honest behaviour for a key nobody has escrowed, and it is stated rather than
    hidden: no verifier in this build is a real firm.
    """
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    import base64

    seeded: list[str] = []
    for verifier_id, name, claims, countries in (
        (
            "demo-identity",
            "Demonstration identity verifier",
            frozenset({Claim.SANCTIONS_CLEAR, Claim.IDENTITY_BASIC,
                       Claim.IDENTITY_ENHANCED, Claim.RESIDENCY}),
            frozenset(),
        ),
        (
            "demo-professional",
            "Demonstration professional counterparty verifier",
            frozenset({Claim.PROFESSIONAL}),
            frozenset(),
        ),
    ):
        key = ec.generate_private_key(ec.SECP256R1())
        raw = key.public_key().public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        )
        engine.trust(Verifier(
            verifier_id=verifier_id, name=name,
            public_key=base64.urlsafe_b64encode(raw).decode().rstrip("="),
            claims=claims, countries=countries,
        ))
        # Kept so the demonstration endpoint can issue statements. A deployment
        # never holds a verifier's private key, and this one is not persisted.
        _DEMO_KEYS[verifier_id] = key
        seeded.append(verifier_id)
    return seeded


def _sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


# ---------------------------------------------------------------------------
# A book to open with
# ---------------------------------------------------------------------------


_DEMO_LABELS = ("kadikoy.apt", "konak.shop", "adiyaman.coop", "ankara.office", "konya.farm", "edirne.farm",
                "cukurova.farm", "urfa.farm", "traveller.a", "traveller.b", "traveller.c", "traveller.d")
_demo_addresses: set[str] = set()


def is_synthetic(policy: Any) -> bool:
    """A policy the demonstration wrote for itself: the opening book and the
    arrivals. Marked on the record since 1.7.0; recognised by the holder's
    derived address before that, so an older book is read the same way."""
    if (policy.metadata or {}).get("synthetic"):
        return True
    if not _demo_addresses:
        _demo_addresses.update(derive_address(f"clause/demo/{label}") for label in _DEMO_LABELS)
        _demo_addresses.update(derive_address(f"clause/demo/buyer.{n:04d}") for n in range(10_000))
    return policy.holder in _demo_addresses


def _address(wallets: Wallets, label: str, funding: float) -> str:
    """A deterministic address for a seeded participant, funded to act.

    The label is used only to make the demo reproducible. It is not stored
    anywhere and the protocol never sees it: only the address it derives.
    """
    address = derive_address(f"clause/demo/{label}")
    wallets.connect(address, fund=False)
    if funding > 0:
        wallets.credit(address, funding, "demo funding", kind="faucet")
    return address


def _on_paper(registry: Any, *, peril: str, limit: float, term_days: float,
              country: str = "TR") -> str | None:
    """Put a protocol written policy on a registered carrier's paper.

    The opening book and the arrivals are not people at a keyboard, so they skip
    the parts of the gate that are about a person: the interest declaration, the
    attestations. They do not skip the licence. A policy in this book is on a
    named company's paper or it is not written, which is the whole point of the
    registry existing.
    """
    placement = registry.place(
        country=country, peril=peril, limit=limit, term_days=term_days,
        asset=SettlementAsset.FIAT, reach=Reach.RETAIL,
    )
    best = placement.best
    if best is None or not placement.placed:
        return None
    registry.record(best.carrier.carrier_id, limit)
    return best.carrier.carrier_id


def _soon(extra: int = 0) -> str:
    """A departure a fortnight out, plus ``extra`` days: the seeded flights
    must always be ahead of today."""
    return (dt.date.today() + dt.timedelta(days=14 + extra)).isoformat()


def _seed(pool: Pool, chain: Chain, wallets: Wallets, registry: Any = None) -> None:
    """Open with capital and a spread book, so the first screen shows a protocol.

    An empty pool would price its first policy at the cost of standing behind
    it alone, which is true but tells a visitor nothing about how the pricing
    actually works.
    """
    # Sized so the capital rules actually bind. A pool many times larger than its
    # book would be solvent by accident and would teach a visitor nothing.
    # Across the three tranches, so the page can show the order losses run in.
    for label, capital, tranche in (
        ("lp.anadolu", 1_900_000.0, "senior"),
        ("lp.marmara", 1_100_000.0, "mezzanine"),
        ("lp.retail", 500_000.0, "first_loss"),
    ):
        pool.deposit(_address(wallets, label, capital), capital, tranche=tranche)

    opening = [
        ("earthquake", {"location": "IST-KADIKOY", "radius_km": 50.0}, 180_000, 365, "kadikoy.apt"),
        ("earthquake", {"location": "IZM-KONAK", "radius_km": 50.0}, 140_000, 365, "konak.shop"),
        ("earthquake", {"location": "ADY-MERKEZ", "radius_km": 50.0}, 120_000, 365, "adiyaman.coop"),
        ("earthquake", {"location": "ANK-CANKAYA", "radius_km": 25.0}, 90_000, 365, "ankara.office"),
        ("drought", {"station": "TR-KONYA", "distance_km": 6.0, "hectares": 60.0}, 85_000, 150, "konya.farm"),
        ("drought", {"station": "TR-EDIRNE", "distance_km": 4.0, "hectares": 80.0}, 70_000, 150, "edirne.farm"),
        ("drought", {"station": "TR-ADANA", "distance_km": 9.0, "hectares": 55.0}, 65_000, 140, "cukurova.farm"),
        ("drought", {"station": "TR-SANLIURFA", "distance_km": 22.0, "hectares": 40.0}, 55_000, 140, "urfa.farm"),
        ("flight_delay", {"route": "TK-IST-LHR", "flight_number": "TK1979", "departure_date": _soon()}, 1_500, 2, "traveller.a"),
        ("flight_delay", {"route": "TK-IST-JFK", "flight_number": "TK0003", "departure_date": _soon()}, 2_000, 2, "traveller.b"),
        ("flight_delay", {"route": "PC-SAW-ESB", "flight_number": "PC2310", "departure_date": _soon(1)}, 800, 2, "traveller.c"),
        ("flight_delay", {"route": "BA-LHR-IST", "flight_number": "BA0676", "departure_date": _soon(1)}, 1_200, 2, "traveller.d"),
    ]

    for peril, subject, limit, term, label in opening:
        try:
            policy = pool.write(
                peril_key=peril, subject=subject, limit=limit,
                term_days=term, holder=_address(wallets, label, limit),
            )
            if registry is not None:
                carrier_id = _on_paper(
                    registry, peril=peril, limit=limit, term_days=term
                )
                if carrier_id:
                    policy.metadata["carrier"] = carrier_id
            policy.metadata["synthetic"] = True
            chain.register(policy)
        except PoolError as error:
            logger.info("opening book skipped a policy: %s", error)

    # One source is taken offline on purpose. The policy written against it can
    # settle neither way, and watching the protocol return the premium rather
    # than keep it is the point of having the case in the demo at all.
    chain.silence("api.meteo.example/v1/station/TR-SANLIURFA/cumulative")


async def _arrivals(
    pool: Pool, chain: Chain, wallets: Wallets,
    declined: list[dict[str, Any]], registry: Any = None, *, every: float = 8.0,
) -> None:
    """A trickle of new buyers, so the book keeps turning over.

    Each arrival is priced against the book as it stands at that moment, which
    is also the point: the same cover gets cheaper as the pool diversifies and
    dearer as it concentrates, and watching that happen is more convincing than
    reading that it would.
    """
    import random

    rng = random.Random(4242)
    candidates: list[tuple[str, dict[str, Any], tuple[float, float], float]] = [
        ("earthquake", {"location": "IST-KADIKOY", "radius_km": 50.0}, (60_000, 180_000), 365),
        ("earthquake", {"location": "IST-BAKIRKOY", "radius_km": 50.0}, (60_000, 160_000), 365),
        ("earthquake", {"location": "IZM-KONAK", "radius_km": 50.0}, (50_000, 140_000), 365),
        ("earthquake", {"location": "ADY-MERKEZ", "radius_km": 50.0}, (50_000, 130_000), 365),
        ("earthquake", {"location": "ANK-CANKAYA", "radius_km": 25.0}, (40_000, 110_000), 365),
        ("drought", {"station": "TR-KONYA", "distance_km": 7.0, "hectares": 55.0}, (40_000, 95_000), 150),
        ("drought", {"station": "TR-EDIRNE", "distance_km": 5.0, "hectares": 70.0}, (40_000, 85_000), 150),
        ("drought", {"station": "TR-ADANA", "distance_km": 11.0, "hectares": 60.0}, (35_000, 80_000), 140),
        ("flight_delay", {"route": "TK-IST-LHR", "flight_number": "TK1979", "departure_date": _soon(7)}, (900, 2_400), 2),
        ("flight_delay", {"route": "TK-IST-AMS", "flight_number": "TK1953", "departure_date": _soon(7)}, (900, 2_200), 2),
        ("flight_delay", {"route": "LH-FRA-IST", "flight_number": "LH1302", "departure_date": _soon(8)}, (800, 2_000), 2),
    ]
    from ..perils import STORM
    if STORM.territory:
        # Only where the wind model was built: a deployment without it has
        # nothing to price a storm arrival against.
        candidates.append(("storm", {"latitude": 40.15, "longitude": 26.41, "place": "Çanakkale"}, (30_000, 120_000), 365))
        candidates.append(("storm", {"latitude": 41.00, "longitude": 39.72, "place": "Trabzon"}, (30_000, 100_000), 365))

    counter = 0
    while True:
        await asyncio.sleep(every)
        counter += 1
        peril, subject, (low, high), term = rng.choice(candidates)
        subject = dict(subject)
        if peril == "flight_delay":
            subject["flight_number"] = f"{subject['flight_number'][:2]}{rng.randint(100, 9999)}"

        try:
            # The pricing simulation is not async, so it runs off the event loop
            # to keep the interface responsive while a quote is worked out.
            policy = await asyncio.to_thread(
                pool.write,
                peril_key=peril,
                subject=subject,
                limit=float(rng.randint(int(low), int(high))),
                term_days=term,
                holder=_address(wallets, f"buyer.{counter:04d}", float(high)),
            )
            with pool.lock:
                if registry is not None:
                    # What each company is carrying, recomputed from the open book
                    # rather than tracked incrementally, so cover that has since
                    # expired stops occupying capacity.
                    registry.reconcile(pool.policies.values())
                    carrier_id = _on_paper(
                        registry, peril=peril, limit=policy.limit, term_days=term
                    )
                    if carrier_id:
                        policy.metadata["carrier"] = carrier_id
                policy.metadata["synthetic"] = True
                chain.register(policy)
        except PoolError as error:
            # A refusal is the capital rules working, not a fault.
            declined.append(
                {
                    "at": time.time(),
                    "peril": peril,
                    "subject": subject,
                    "reason": str(error),
                }
            )
            del declined[:-25]
            logger.info("arrival declined: %s", error)
        except Exception:  # never let a buyer take the server down
            logger.exception("arrival failed")


def serve(
    *, host: str = "127.0.0.1", port: int = 8000, speed: float = 1.0,
    trials: int = 12_000,
) -> None:
    import uvicorn

    uvicorn.run(
        create_app(trials=trials, speed=speed),
        host=host,
        port=port,
        log_level="warning",
        timeout_graceful_shutdown=5,
    )
