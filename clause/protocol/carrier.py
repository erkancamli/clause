"""Who is allowed to issue the policy, and where.

The earlier version of this protocol answered the licensing question with a
table of countries hard coded into the source. That was the right instinct and
the wrong shape. It made the law look like a property of the software, so the
only way to reach a new country was to edit a Python file, and it quietly
implied that the operator held every licence the table described. Neither is
true of any insurance business that exists.

What is actually true is narrower and more useful: **a policy is issued by a
company that holds a licence to issue it where the risk is.** For property that
is where the property stands, whoever owns it and wherever they live; for cover
that follows a person, such as a flight, it is where that person lives.
Everything else follows from that one sentence. So this module holds companies rather than
countries, and a country becomes writable the moment a company that can write
there is registered, without a line of code changing.

Two roles, because real risk transfer has two
---------------------------------------------
    CARRIER     Issues the policy. Its name is on the contract, its regulator
                supervises it, and it must hold a licence for the buyer's
                country, the peril, and the kind of buyer. This is the only role
                that may face a consumer.

    REINSURER   Stands behind carriers with capital. Licensed where it is
                domiciled rather than where the buyer is, because it never
                faces the buyer. This is the layer a pool of onchain capital
                actually belongs at, and it is the structure Ensuro operates
                under a Bermuda licence.

Clause is registered in both roles and gets no special treatment in either. Its
reinsurance entity provides capacity wherever a cedant is licensed, and in the
places it holds a licence of its own it is also a carrier, matched by the same
function that matches everyone else. There is no branch in this file that says
"unless it is us".

Why a registry rather than a list
---------------------------------
Three things fall out of it that the table could not do:

    The map is earned.      A country appears on the coverage map because a
                            licensed company said it would write there, not
                            because someone typed it in. `coverage()` is the
                            honest answer to "where do you operate".

    Refusal is specific.    A buyer in a country with no carrier is told that
                            no licensed carrier is registered for their country
                            and peril, which is a fact about the registry. The
                            old answer, "no rule has been established", was a
                            fact about our documentation.

    The licence expires.    A licence has a date on it. A registry can let one
                            lapse and stop matching on it in the same second;
                            a table in the source cannot, and would keep selling.

Checked again on every execution
--------------------------------
Rialo publishes identity, privacy and compliance as a protocol level concern
under the name IPC, and the behaviour it describes is the one this module is
built for: compliance is not assumed at setup, it is re-evaluated during each
execution, and if it fails the execution aborts with no state transition. A
carrier whose licence lapses between binding a policy and paying it is exactly
that case. So the matching function is pure and cheap enough to run twice: once
when cover is bound, and again before the payout leaves.

Nothing here is legal advice. What the code guarantees is narrower: the protocol
cannot issue a policy that no registered company claims a licence for, because
the lookup is in the path rather than in a document.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable

# The pool's own figures, and what a company that states neither is priced at,
# so nothing moves for a company registered before either was asked for.
from ..pricing.engine import COST_OF_CAPITAL, EXPENSE_RATIO, loads_for

# A licence within this many days of expiry still binds, but the carrier is
# told. Cover written on the last day of a licence is cover that outlives it.
RENEWAL_WARNING_DAYS = 60

# No single carrier may take more than this share of the book, whatever its
# stated capacity. One company failing should not take the protocol with it.
CARRIER_CONCENTRATION_LIMIT = 0.45


class Role(str, Enum):
    CARRIER = "carrier"        # issues the policy, faces the buyer
    REINSURER = "reinsurer"    # stands behind carriers with capital


class Status(str, Enum):
    PENDING = "pending"        # registered, licence not yet verified
    ACTIVE = "active"
    SUSPENDED = "suspended"    # by the operator, or by its own regulator
    WITHDRAWN = "withdrawn"    # left, voluntarily


class Reach(str, Enum):
    """Who a licence permits the holder to sell to."""

    RETAIL = "retail"              # consumers
    PROFESSIONAL = "professional"  # informed counterparties only


class Settlement(str, Enum):
    STABLECOIN = "stablecoin"
    FIAT = "fiat"


class CarrierError(RuntimeError):
    """A registration or a licence that cannot be accepted as stated."""


@dataclass(frozen=True, slots=True)
class Review:
    """One decision a person took about one company, kept.

    Activation is the single step in this protocol that a human performs, and a
    step performed by a human with no record of who performed it is not a
    review, it is a button. So every activation and every suspension writes a
    line here: when, which way, who said they did it, and what they said they
    checked.

    The name is self declared and the record says so. One shared operator token
    cannot prove which person held it, and a field that implied otherwise would
    be worse than an honest one: this is a log of what was asserted at the time,
    which is what an auditor asking "who let this company in" actually needs.
    """

    at: float
    action: str                     # "activated" or "suspended"
    reviewer: str = ""              # self declared, see above
    note: str = ""                  # what the reviewer says they checked
    checks: dict[str, Any] = field(default_factory=dict)   # the checklist as it stood, item by item

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "action": self.action,
            "checks": dict(self.checks),
            "reviewer": self.reviewer or "operator",
            "reviewer_self_declared": True,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class Licence:
    """One permission, in one country, as the company states it.

    Stated, not proven. This protocol cannot verify a licence number against a
    regulator's register from inside a block, and pretending otherwise would be
    worse than admitting it. What it does instead is record who claimed what,
    when, and under whose supervision, and expose that to the buyer: the
    interface names the carrier and its regulator on the policy, which is the
    same check a person makes when buying insurance anywhere.
    """

    country: str                    # ISO 3166-1 alpha-2, uppercase
    authority: str                  # the regulator that issued it
    reference: str                  # the number, as the regulator records it
    perils: frozenset[str]          # peril keys this licence covers
    reach: Reach
    settlement: frozenset[Settlement]
    expires_at: float
    verified_at: float | None = None   # when the operator checked the register

    def __post_init__(self) -> None:
        if len(self.country) != 2 or not self.country.isalpha():
            raise CarrierError("a licence names a country as two letters")
        if not self.authority.strip() or not self.reference.strip():
            raise CarrierError("a licence names its authority and its number")
        if not self.perils:
            raise CarrierError("a licence covers at least one peril")
        if not self.settlement:
            raise CarrierError("a licence permits at least one settlement asset")

    def live(self, *, now: float | None = None) -> bool:
        return self.expires_at > (time.time() if now is None else now)

    def expiring(self, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return self.live(now=now) and (
            self.expires_at - now < RENEWAL_WARNING_DAYS * 86400
        )

    def covers(
        self, *, country: str, peril: str, reach: Reach, asset: Settlement,
        now: float | None = None,
    ) -> bool:
        return (
            self.country == country.upper()
            and peril in self.perils
            and asset in self.settlement
            and (self.reach is Reach.RETAIL or reach is Reach.PROFESSIONAL)
            and self.live(now=now)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "country": self.country,
            "authority": self.authority,
            "reference": self.reference,
            "perils": sorted(self.perils),
            "reach": self.reach.value,
            "settlement": sorted(s.value for s in self.settlement),
            "expires_at": self.expires_at,
            "expiring_soon": self.expiring(),
            "live": self.live(),
            "verified_at": self.verified_at,
        }


@dataclass(frozen=True, slots=True)
class Appetite:
    """What a company will write, beyond what it is permitted to write.

    A licence says what is lawful. Appetite says what the underwriter actually
    wants, which is always narrower and is the thing that changes weekly. Kept
    separate so that tightening appetite never looks like losing a licence.
    """

    max_limit: float                       # per policy, in the unit of account
    max_term_days: float
    perils: frozenset[str]                 # a subset of what it is licensed for
    excluded_countries: frozenset[str] = frozenset()
    min_premium: float = 0.0

    def wants(self, *, country: str, peril: str, limit: float, term_days: float) -> bool:
        return (
            peril in self.perils
            and country.upper() not in self.excluded_countries
            and limit <= self.max_limit + 1e-9
            and term_days <= self.max_term_days + 1e-9
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_limit": round(self.max_limit, 2),
            "max_term_days": self.max_term_days,
            "perils": sorted(self.perils),
            "excluded_countries": sorted(self.excluded_countries),
            "min_premium": round(self.min_premium, 2),
        }


@dataclass
class Carrier:
    """A company registered to issue cover, or to stand behind someone who does."""

    carrier_id: str
    name: str
    role: Role
    domicile: str                      # where the company itself is supervised
    licences: tuple[Licence, ...]
    appetite: Appetite
    # Capacity is the most cover this company will have in force at once. It is
    # the company's own limit on itself, and the protocol holds it to it.
    capacity: float
    # The share of premium the carrier takes for putting its paper in front. The
    # rest reaches the pool that carries the risk.
    fronting_fee: float = 0.0
    # What this company charges for the risk itself, which is the part of a
    # price that is genuinely its own.
    #
    # A price has three parts: the expected loss, what the capital it ties up
    # must earn, and what it costs to run. Only the first is the model's answer
    # and every company reads the same one -- no insurer disputes an exceedance
    # curve, they dispute what to charge for it. The other two are the
    # company's own numbers, and they were a single figure held by the pricing
    # engine, so nine companies quoted one price to the penny and differed only
    # in the fee on top. A well capitalised company with a thin cost base
    # offers a keener price; a company that will write a bigger line usually
    # wants more for it. Both are said here.
    cost_of_capital: float = COST_OF_CAPITAL
    expense_ratio: float = EXPENSE_RATIO
    # What this company offers beyond the protocol's own terms, shown to a
    # buyer choosing between companies: days of cooling off beyond the law,
    # and how many days a fiat payout takes to reach a bank.
    extra_cooling_off_days: float = 0.0
    fiat_payout_days: float = 3.0
    fees_earned: float = 0.0
    status: Status = Status.PENDING
    # A carrier is an address like everyone else: it signs its registration and
    # its own changes, and its fee settles to it.
    address: str | None = None
    contact: str = ""
    # A stand in, put here so the shape of the protocol can be demonstrated
    # without a real company agreeing to anything. Everything that displays a
    # company carries this through, because a fabricated insurer that looks
    # real is the single most misleading thing this codebase could publish.
    specimen: bool = False
    # What anchors the claim: the Legal Entity Identifier, the company's own
    # domain, documents it uploaded, and what the automatic checks found. See
    # protocol/kyb.py. None of it activates anything.
    lei: str = ""
    domain: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    verification: dict[str, Any] | None = None
    # The operator's checklist, item by item: who confirmed what, where, when.
    vetting: dict[str, Any] = field(default_factory=dict)
    review_due_at: float | None = None      # when the checks are due again
    mersis: str = ""                        # Türkiye: the central registry number
    tax_number: str = ""                    # Türkiye: vergi kimlik numarası
    registered_at: float = field(default_factory=time.time)
    in_force: float = 0.0              # cover currently on its paper
    written: int = 0                   # policies issued, for the record
    # Every human decision taken about this company, oldest first. Never
    # rewritten: a suspension appends, it does not erase the activation that
    # came before it.
    reviews: tuple[Review, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise CarrierError("a company has a name")
        if self.capacity <= 0:
            raise CarrierError("a company with no capacity cannot write")
        if not 0.0 <= self.fronting_fee < 0.5:
            raise CarrierError("a fronting fee between zero and half the premium")
        # Bounded, because these set the price a buyer pays. A company that
        # wanted nothing for its capital would be pricing below the risk, and
        # one that wanted half of it a year is not a market participant.
        if not 0.0 < self.cost_of_capital <= 0.5:
            raise CarrierError("a cost of capital above zero and no more than half a year's return")
        if not 0.0 <= self.expense_ratio <= 0.5:
            raise CarrierError("an expense ratio between zero and half the expected loss")
        if self.role is Role.CARRIER and not self.licences:
            raise CarrierError("a carrier holds at least one licence")


    # -- what it can do ---------------------------------------------------

    def headroom(self) -> float:
        return max(0.0, self.capacity - self.in_force)

    def licence_for(
        self, *, country: str, peril: str, reach: Reach, asset: Settlement,
        now: float | None = None,
    ) -> Licence | None:
        for licence in self.licences:
            if licence.covers(
                country=country, peril=peril, reach=reach, asset=asset, now=now
            ):
                return licence
        return None

    def countries(self, *, now: float | None = None) -> set[str]:
        return {l.country for l in self.licences if l.live(now=now)}

    def folded(self) -> dict[str, Any]:
        """The little a reader needs of a stand in they will not open.

        There are three of these in every country now, and the register folds
        all of them behind one line, so sending each one's licence, appetite
        and ledger put two thirds of a megabyte on the wire to be thrown away.
        This is what the folded line actually reads.
        """
        return {"carrier_id": self.carrier_id, "name": self.name, "role": self.role.value,
                "domicile": self.domicile, "status": self.status.value,
                "countries": sorted(self.countries()), "specimen": True, "folded": True}

    def to_dict(self, *, private: bool = False) -> dict[str, Any]:
        out = {
            "carrier_id": self.carrier_id,
            "name": self.name,
            "role": self.role.value,
            "domicile": self.domicile,
            "status": self.status.value,
            "countries": sorted(self.countries()),
            "licences": [l.to_dict() for l in self.licences],
            "appetite": self.appetite.to_dict(),
            "capacity": round(self.capacity, 2),
            "in_force": round(self.in_force, 2),
            "headroom": round(self.headroom(), 2),
            "fronting_fee": self.fronting_fee,
            "cost_of_capital": self.cost_of_capital,
            "expense_ratio": self.expense_ratio,
            "extra_cooling_off_days": self.extra_cooling_off_days,
            "fiat_payout_days": self.fiat_payout_days,
            "fees_earned": round(self.fees_earned, 2),
            "policies_written": self.written,
            "specimen": self.specimen,
            "registered_at": self.registered_at,
        }
        out["lei"] = self.lei
        out["review_due_at"] = self.review_due_at
        if private:
            out["contact"] = self.contact
            out["address"] = self.address
            out["domain"] = self.domain
            out["mersis"] = self.mersis
            out["tax_number"] = self.tax_number
            out["evidence"] = [{k: v for k, v in e.items() if k != "stored"} for e in self.evidence]
            out["verification"] = self.verification
            out["vetting"] = {k: dict(v) for k, v in self.vetting.items()}
            out["reviews"] = [r.to_dict() for r in self.reviews]
        return out


@dataclass(frozen=True, slots=True)
class Offer:
    """One company's answer to one buyer's request."""

    carrier: Carrier
    licence: Licence
    fronting_fee: float
    headroom: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "carrier_id": self.carrier.carrier_id,
            "name": self.carrier.name,
            "domicile": self.carrier.domicile,
            "authority": self.licence.authority,
            "licence": self.licence.reference,
            "country": self.licence.country,
            "fronting_fee": self.fronting_fee,
            "headroom": round(self.headroom, 2),
            "specimen": self.carrier.specimen,
        }


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a risk would be placed, or why it cannot be."""

    placed: bool
    offers: tuple[Offer, ...]
    reinsurers: tuple[Carrier, ...]
    reasons: tuple[str, ...]
    # The company the buyer chose, when they chose; else the cheapest.
    chosen: str | None = None
    # Whether anyone held a licence for this at all, before appetite, room and
    # concentration were looked at. "Nobody is licensed here" and "somebody is
    # licensed and full" are different answers and the buyer is owed the right
    # one; without this the caller cannot tell them apart.
    licensed: bool = False
    # The companies that are licensed for this and still did not offer, each
    # with the reason. A carrier that fills up used to disappear from the list
    # leaving nothing behind, so a buyer seeing one company could not tell
    # whether that was all there was or all that had room left, and neither
    # could we. Now the list is short by name and by reason.
    held_back: tuple[tuple[str, str], ...] = ()

    def best_for(self, *, expected_loss: float = 0.0, marginal_capital: float = 0.0,
                 term_days: float = 365.0) -> Offer | None:
        """The buyer's choice, or the cheapest paper with room for it.

        Cheapest by what the buyer pays, which used to be the same as the
        lowest fronting fee and no longer is: companies price the risk
        themselves now, so the one that adds the smallest fee can still be
        dearer than one that adds a larger fee to a keener price. Given the
        risk's own two numbers this compares the totals; without them it falls
        back to the fee, which is all there is to go on.

        Ties break on headroom, so a busy carrier is not filled before a quiet
        one.
        """
        if not self.offers:
            return None
        if self.chosen:
            for offer in self.offers:
                if offer.carrier.carrier_id == self.chosen:
                    return offer
            return None
        if expected_loss > 0 or marginal_capital > 0:
            def costs(o: Offer) -> tuple[float, float]:
                said = priced_by(o.carrier, expected_loss=expected_loss,
                                 marginal_capital=marginal_capital, term_days=term_days)
                return (said["total"], -o.headroom)
            return min(self.offers, key=costs)
        return min(self.offers, key=lambda o: (o.fronting_fee, -o.headroom))

    @property
    def best(self) -> Offer | None:
        """The choice with nothing known about the risk. See best_for."""
        return self.best_for()

    def to_dict(self) -> dict[str, Any]:
        best = self.best
        return {
            "placed": self.placed,
            "carrier": best.to_dict() if best else None,
            "alternatives": [o.to_dict() for o in self.offers if o is not best],
            "reinsurers": [
                {"carrier_id": r.carrier_id, "name": r.name, "domicile": r.domicile}
                for r in self.reinsurers
            ],
            "reasons": list(self.reasons),
        }


class Registry:
    """Every registered company, and the matching that puts a risk on paper."""

    def __init__(self) -> None:
        self.carriers: dict[str, Carrier] = {}

    # -- registration -----------------------------------------------------

    def register(self, carrier: Carrier) -> Carrier:
        if carrier.carrier_id in self.carriers:
            raise CarrierError(f"{carrier.carrier_id} is already registered")
        refusal = unlawful_settlement(carrier)
        if refusal:
            raise CarrierError(refusal)
        self.carriers[carrier.carrier_id] = carrier
        return carrier

    def require(self, carrier_id: str) -> Carrier:
        found = self.carriers.get(carrier_id)
        if found is None:
            raise CarrierError("no such company")
        return found

    def activate(
        self, carrier_id: str, *, reviewer: str = "", note: str = "",
        now: float | None = None, checks: dict[str, Any] | None = None,
        review_after_days: float = 365.0,
    ) -> Carrier:
        """Mark a company's licences as checked against the public register.

        Deliberately a separate step from registration, and deliberately manual.
        A company that has registered but not been checked is visible, quotable
        and unable to write anything, which is the correct state for a claim
        nobody has verified.

        The reviewer and the note are what the person at the keyboard said they
        did. They are kept because the alternative is a protocol where companies
        become able to issue policies and nothing records how.
        """
        carrier = self.require(carrier_id)
        now = time.time() if now is None else now
        carrier.licences = tuple(
            Licence(
                country=l.country, authority=l.authority, reference=l.reference,
                perils=l.perils, reach=l.reach, settlement=l.settlement,
                expires_at=l.expires_at, verified_at=now,
            )
            for l in carrier.licences
        )
        carrier.status = Status.ACTIVE
        carrier.review_due_at = now + review_after_days * 86400.0
        carrier.reviews += (Review(
            at=now, action="activated",
            reviewer=reviewer.strip()[:80], note=note.strip()[:400],
            checks={k: dict(v) for k, v in (checks or {}).items()},
        ),)
        return carrier

    def suspend(
        self, carrier_id: str, reason: str = "", *, reviewer: str = "",
        now: float | None = None,
    ) -> Carrier:
        carrier = self.require(carrier_id)
        carrier.status = Status.SUSPENDED
        carrier.reviews += (Review(
            at=time.time() if now is None else now, action="suspended",
            reviewer=reviewer.strip()[:80], note=reason.strip()[:400],
        ),)
        return carrier

    # -- matching ---------------------------------------------------------

    def place(
        self, *, country: str, peril: str, limit: float, term_days: float,
        asset: Settlement, reach: Reach = Reach.RETAIL,
        book_capacity: float | None = None, now: float | None = None,
        chosen: str | None = None,
    ) -> Placement:
        """Which registered company, if any, may issue this policy.

        Pure and cheap: it reads the registry and returns, so it can be run when
        cover is bound and again before a payout, which is what the protocol
        does. The reasons it returns are the ones shown to the buyer, so they
        describe the registry rather than our paperwork.
        """
        country = country.upper()
        offers: list[Offer] = []
        reasons: list[str] = []
        held_back: list[tuple[str, str]] = []

        licensed_here = False
        for carrier in self.carriers.values():
            if carrier.role is not Role.CARRIER:
                continue
            if carrier.status is not Status.ACTIVE:
                continue
            licence = carrier.licence_for(
                country=country, peril=peril, reach=reach, asset=asset, now=now
            )
            if licence is None:
                continue
            licensed_here = True
            if not carrier.appetite.wants(
                country=country, peril=peril, limit=limit, term_days=term_days
            ):
                held_back.append((carrier.name, (
                    f"writes this peril but not at this size: its most is "
                    f"{carrier.appetite.max_limit:,.0f}"
                    if limit > carrier.appetite.max_limit else
                    f"writes this peril but not for this long: its most is "
                    f"{carrier.appetite.max_term_days:g} days"
                    if term_days > carrier.appetite.max_term_days else
                    "does not want this risk")))
                continue
            room = carrier.headroom()
            if room < limit:
                held_back.append((carrier.name, (
                    f"full: {room:,.0f} of room left and this needs {limit:,.0f}")))
                continue
            if book_capacity and carrier.in_force + limit > (
                book_capacity * CARRIER_CONCENTRATION_LIMIT
            ):
                held_back.append((carrier.name, (
                    f"already carries {CARRIER_CONCENTRATION_LIMIT:.0%} of the book, "
                    f"which is as much as any one company may")))
                continue
            offers.append(Offer(carrier, licence, carrier.fronting_fee, room))

        if not offers:
            if not licensed_here:
                reasons.append(
                    f"no licensed carrier is registered to write {peril} cover in "
                    f"{country} for this kind of buyer, paid in {asset.value}"
                )
            else:
                reasons.append(
                    f"a carrier is licensed in {country} but none will take this "
                    f"risk at this size or term right now"
                )

        reinsurers = tuple(
            c for c in self.carriers.values()
            if c.role is Role.REINSURER and c.status is Status.ACTIVE
            and c.headroom() >= limit
        )
        if offers and not reinsurers:
            reasons.append(
                "no reinsurer has capacity to stand behind this, so the carrier "
                "would be carrying it alone"
            )

        if chosen and offers and not any(o.carrier.carrier_id == chosen for o in offers):
            reasons.append("the company you chose cannot issue this cover; choose another")
            offers = []
        return Placement(
            placed=bool(offers) and bool(reinsurers),
            licensed=licensed_here,
            offers=tuple(offers),
            reinsurers=reinsurers,
            reasons=tuple(reasons),
            chosen=chosen,
            held_back=tuple(held_back),
        )

    # -- the map ----------------------------------------------------------

    def coverage(self, *, now: float | None = None) -> dict[str, dict[str, Any]]:
        """Where cover can be written, assembled from who is registered.

        This is the coverage map, and it is a consequence rather than a claim. A
        country is on it because a company that may write there said so.
        """
        out: dict[str, dict[str, Any]] = {}
        for carrier in self.carriers.values():
            if carrier.role is not Role.CARRIER or carrier.status is not Status.ACTIVE:
                continue
            for licence in carrier.licences:
                if not licence.live(now=now):
                    continue
                entry = out.setdefault(
                    licence.country,
                    {
                        "country": licence.country, "carriers": [], "perils": set(),
                        "authorities": set(), "retail": False,
                        "settlement": set(), "capacity": 0.0, "specimen": True,
                    },
                )
                if carrier.name not in entry["carriers"]:
                    entry["carriers"].append(carrier.name)
                entry["specimen"] = entry.get("specimen", True) and carrier.specimen
                entry["perils"] |= licence.perils & carrier.appetite.perils
                entry["authorities"].add(licence.authority)
                entry["retail"] = entry["retail"] or licence.reach is Reach.RETAIL
                entry["settlement"] |= {s.value for s in licence.settlement}
                entry["capacity"] += carrier.headroom()

        for entry in out.values():
            entry["perils"] = sorted(entry["perils"])
            entry["authorities"] = sorted(entry["authorities"])
            entry["settlement"] = sorted(entry["settlement"])
            entry["capacity"] = round(entry["capacity"], 2)
        return out

    def backed(self) -> bool:
        """Whether any active reinsurer has room to stand behind anything.

        The same condition placement applies to a single risk, asked of the
        registry as a whole, so the coverage map cannot call a country open
        that placement would then refuse for want of a reinsurer.
        """
        return any(
            c.role is Role.REINSURER and c.status is Status.ACTIVE and c.headroom() > 0
            for c in self.carriers.values()
        )

    def summary(self) -> dict[str, Any]:
        active = [c for c in self.carriers.values() if c.status is Status.ACTIVE]
        return {
            "companies": len(self.carriers),
            "active": len(active),
            "carriers": len([c for c in active if c.role is Role.CARRIER]),
            "reinsurers": len([c for c in active if c.role is Role.REINSURER]),
            "countries": len(self.coverage()),
            "capacity": round(sum(c.headroom() for c in active), 2),
        }

    # -- the book ---------------------------------------------------------

    def reconcile(self, policies: Iterable[Any]) -> None:
        """Recompute what each company is carrying, from the open book itself.

        Incrementing on write and decrementing on settlement is the obvious way
        and the wrong one: a policy can end four ways and every path that forgets
        to decrement leaks capacity until the company is full of cover that
        expired months ago. Deriving it from the book cannot drift, because the
        book is the fact and this is a view of it.
        """
        carried: dict[str, float] = {}
        for policy in policies:
            if not getattr(policy, "is_open", False):
                continue
            carrier_id = (policy.metadata or {}).get("carrier")
            if carrier_id:
                carried[carrier_id] = carried.get(carrier_id, 0.0) + policy.limit
        for carrier_id, carrier in self.carriers.items():
            carrier.in_force = carried.get(carrier_id, 0.0)

    def record(self, carrier_id: str, limit: float) -> None:
        carrier = self.require(carrier_id)
        carrier.in_force += limit
        carrier.written += 1

    def release(self, carrier_id: str, limit: float) -> None:
        carrier = self.carriers.get(carrier_id)
        if carrier is not None:
            carrier.in_force = max(0.0, carrier.in_force - limit)


# ---------------------------------------------------------------------------
# The companies this build starts with
# ---------------------------------------------------------------------------

YEAR = 365 * 86400
EVERY_PERIL = frozenset({"earthquake", "drought", "flight_delay", "vehicle_flood", "storm"})
BOTH_ASSETS = frozenset({Settlement.STABLECOIN, Settlement.FIAT})
FIAT_ONLY = frozenset({Settlement.FIAT})


def specimen_registry(*, now: float | None = None) -> Registry:
    """Stand in companies, so the shape of the protocol can be demonstrated.

    An earlier version of this function invented insurance companies: plausible
    names, and licence references in the exact format the regulator uses, like
    ``SEDDK/2026/0912`` and ``FRN 812440``. Those were published on a live site
    that presents itself as insurance infrastructure. A visitor had no way to
    tell they were invented, one of those numbers may well belong to a real
    firm, and a person could reasonably have concluded that a licensed Turkish
    insurer stood behind cover they were about to buy. That is not a rough edge
    in a demonstration; it is the one kind of falsehood this whole codebase
    exists to make impossible, published by the codebase itself.

    So nothing here has a name a real company could have, no reference here is
    formatted like a licence number, and every record carries ``specimen``,
    which the API returns and the interface prints on the policy. What stays is
    the structure, which is the part worth showing: two roles, licences that are
    per country and per peril and per kind of buyer, appetite separate from
    permission, and a settlement asset that comes from the licence.

    A real deployment calls none of this. It starts with an empty registry and
    fills it as companies register and have their licences checked, which is why
    `create_app` only loads these when the demonstration switch is on, the same
    switch that hands out pretend money.
    """
    now = time.time() if now is None else now
    registry = Registry()

    def specimen(**kwargs) -> Carrier:
        return Carrier(specimen=True, contact="specimen, not a company", **kwargs)

    # The capital layer. A reinsurer never faces a buyer, so it needs no licence
    # where the buyer is: this is the layer a pool of onchain capital can
    # lawfully sit at today, which is the structure Ensuro operates under a
    # Bermuda licence.
    registry.register(specimen(
        carrier_id="specimen-reinsurer",
        name="Specimen Reinsurer (not a real company)",
        role=Role.REINSURER,
        domicile="BM",
        licences=(Licence(
            country="BM", authority="Bermuda Monetary Authority",
            reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
            reach=Reach.PROFESSIONAL, settlement=BOTH_ASSETS,
            expires_at=now + 3 * YEAR,
        ),),
        appetite=Appetite(max_limit=2_000_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=40_000_000,
    ))

    # Türkiye, twice. Two carriers in one country is not decoration: with one, a
    # country closes the moment that company fills up, and the concentration
    # rule guarantees it will.
    registry.register(specimen(
        carrier_id="specimen-tr-one",
        name="Specimen Carrier A, Türkiye (not a real company)",
        role=Role.CARRIER,
        domicile="TR",
        licences=(Licence(
            country="TR", authority="SEDDK would supervise a real one",
            reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=FIAT_ONLY,
            expires_at=now + YEAR,
        ),),
        appetite=Appetite(max_limit=500_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=8_000_000,
        fronting_fee=0.06,
        cost_of_capital=0.1,
        expense_ratio=0.11,
        fiat_payout_days=1.0,
        extra_cooling_off_days=16.0,
    ))

    registry.register(specimen(
        carrier_id="specimen-tr-two",
        name="Specimen Carrier B, Türkiye (not a real company)",
        role=Role.CARRIER,
        domicile="TR",
        licences=(Licence(
            country="TR", authority="SEDDK would supervise a real one",
            reference="SPECIMEN, no licence exists",
            perils=frozenset({"earthquake", "drought"}),
            reach=Reach.RETAIL, settlement=FIAT_ONLY,
            expires_at=now + 2 * YEAR,
        ),),
        appetite=Appetite(
            max_limit=300_000, max_term_days=400,
            perils=frozenset({"earthquake", "drought"}),
        ),
        capacity=6_000_000,
        fronting_fee=0.075,
        cost_of_capital=0.13,
        expense_ratio=0.09,
        fiat_payout_days=5.0,
    ))

    # And a third, licensed for exactly what B is not. Two carriers only keep a
    # country open for the perils they both write: B is licensed for earthquake
    # and drought, so on the day A filled up, storm, vehicle flood and flight
    # delay had nobody at all and three of the five covers on offer could not be
    # bought in Türkiye. That is what happened. The rule the registry has to
    # hold is not "two carriers per country" but "two per peril per country",
    # and test_carrier_cover.py now fails if it stops holding.
    registry.register(specimen(
        carrier_id="specimen-tr-three",
        name="Specimen Carrier D, Türkiye (not a real company)",
        role=Role.CARRIER,
        domicile="TR",
        licences=(Licence(
            country="TR", authority="SEDDK would supervise a real one",
            reference="SPECIMEN, no licence exists",
            perils=frozenset({"storm", "vehicle_flood", "flight_delay"}),
            reach=Reach.RETAIL, settlement=FIAT_ONLY,
            expires_at=now + 2 * YEAR,
        ),),
        appetite=Appetite(
            max_limit=400_000, max_term_days=400,
            perils=frozenset({"storm", "vehicle_flood", "flight_delay"}),
        ),
        capacity=7_000_000,
        fronting_fee=0.068,
        cost_of_capital=0.12,
        expense_ratio=0.08,
        fiat_payout_days=3.0,
        extra_cooling_off_days=7.0,
    ))

    # Two more, licensed for everything, so that a buyer in Türkiye is choosing
    # between five companies and not being handed one. They are deliberately at
    # opposite ends of every axis a buyer can see: E is the cheapest paper in
    # the country and makes you wait a week for the money and will not write a
    # large cover; F costs the most and pays the next day and gives a month to
    # change your mind. Between them the list stops being a formality.
    registry.register(specimen(
        carrier_id="specimen-tr-four",
        name="Specimen Carrier E, Türkiye (not a real company)",
        role=Role.CARRIER,
        domicile="TR",
        licences=(Licence(
            country="TR", authority="SEDDK would supervise a real one",
            reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=FIAT_ONLY,
            expires_at=now + 2 * YEAR,
        ),),
        appetite=Appetite(max_limit=150_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=4_000_000,
        fronting_fee=0.02,
        cost_of_capital=0.18,
        expense_ratio=0.04,
        fiat_payout_days=7.0,
    ))

    registry.register(specimen(
        carrier_id="specimen-tr-five",
        name="Specimen Carrier F, Türkiye (not a real company)",
        role=Role.CARRIER,
        domicile="TR",
        licences=(Licence(
            country="TR", authority="SEDDK would supervise a real one",
            reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=FIAT_ONLY,
            expires_at=now + 2 * YEAR,
        ),),
        appetite=Appetite(max_limit=500_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=9_000_000,
        fronting_fee=0.09,
        cost_of_capital=0.09,
        expense_ratio=0.14,
        fiat_payout_days=1.0,
        extra_cooling_off_days=30.0,
    ))

    registry.register(specimen(
        carrier_id="specimen-tr-six",
        name="Specimen Carrier G, Türkiye (not a real company)",
        role=Role.CARRIER,
        domicile="TR",
        licences=(Licence(
            country="TR", authority="SEDDK would supervise a real one",
            reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=FIAT_ONLY,
            expires_at=now + 2 * YEAR,
        ),),
        appetite=Appetite(max_limit=250_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=5_000_000,
        fronting_fee=0.045,
        cost_of_capital=0.14,
        expense_ratio=0.07,
        fiat_payout_days=2.0,
        extra_cooling_off_days=3.0,
    ))

    # One that passports across Europe and reaches a professional market
    # elsewhere, so the interface has a consumer refusal to show.
    registry.register(specimen(
        carrier_id="specimen-eu",
        name="Specimen Carrier C, Europe (not a real company)",
        role=Role.CARRIER,
        domicile="IE",
        licences=(
            Licence(
                country="IE", authority="the Central Bank of Ireland would supervise a real one",
                reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
                reach=Reach.RETAIL, settlement=BOTH_ASSETS,
                expires_at=now + 2 * YEAR,
            ),
            Licence(
                country="DE", authority="BaFin would supervise a real one, on a freedom of services basis",
                reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
                reach=Reach.RETAIL, settlement=FIAT_ONLY,
                expires_at=now + 2 * YEAR,
            ),
            Licence(
                country="AE", authority="the DFSA would supervise a real one",
                reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
                reach=Reach.PROFESSIONAL, settlement=BOTH_ASSETS,
                expires_at=now + YEAR,
            ),
        ),
        appetite=Appetite(max_limit=1_000_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=12_000_000,
        fronting_fee=0.045,
        cost_of_capital=0.1,
        expense_ratio=0.1,
    ))

    # And a second across the same three, for the reason the third Turkish one
    # exists: a country with one carrier is a country that closes when that
    # carrier fills, and a buyer with one company to choose from is not
    # choosing. The invariant is two per peril per country, and
    # test_carrier.py holds it for every country in this registry rather than
    # for the ones somebody remembered.
    registry.register(specimen(
        carrier_id="specimen-eu-two",
        name="Specimen Carrier E, Europe (not a real company)",
        role=Role.CARRIER,
        domicile="DE",
        licences=(
            Licence(
                country="DE", authority="BaFin would supervise a real one",
                reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
                reach=Reach.RETAIL, settlement=FIAT_ONLY,
                expires_at=now + 3 * YEAR,
            ),
            Licence(
                country="IE", authority="the Central Bank of Ireland would supervise a real one, on a freedom of services basis",
                reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
                reach=Reach.RETAIL, settlement=FIAT_ONLY,
                expires_at=now + 3 * YEAR,
            ),
            Licence(
                country="AE", authority="the DFSA would supervise a real one",
                reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
                reach=Reach.PROFESSIONAL, settlement=BOTH_ASSETS,
                expires_at=now + 2 * YEAR,
            ),
        ),
        appetite=Appetite(max_limit=750_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=9_000_000,
        fronting_fee=0.052,
        cost_of_capital=0.115,
        expense_ratio=0.095,
        fiat_payout_days=2.0,
        extra_cooling_off_days=14.0,
    ))

    for carrier_id in list(registry.carriers):
        registry.activate(carrier_id, now=now)
    return registry


# Places where nobody lives, and countries under comprehensive sanctions, which
# no insurer anywhere would write for and which a stand in should not pretend to.
_NO_SPECIMEN = frozenset({
    "AQ", "BV", "HM", "TF", "GS", "UM", "PN", "IO", "CX", "CC", "NF", "SJ", "TK",
    "CU", "IR", "KP", "SY",
})
# Where the central bank has banned paying with crypto assets, a stand in's
# licence settles in the local currency only, as a real one's would.
#: Countries whose own law forbids paying in crypto assets. Türkiye's 2021
#: central bank regulation prohibits using them in payments, directly or
#: indirectly, and prohibits payment and e-money institutions from
#: intermediating transfers to crypto platforms; the others are the same kind
#: of rule.
#:
#: What this set binds is **where a company is supervised**, not where a risk
#: happens to sit. The regulation binds institutions, so a company supervised
#: in Türkiye may not pay in stablecoin to anyone, anywhere, and a company
#: supervised elsewhere is answerable to its own regulator instead. The other
#: half of the rule, who may be *paid* that way, is the buyer's country of
#: residence and lives in compliance.py, because it is a question about a
#: person rather than about a licence.
#:
#: It is exported because shaping a licence is not the same as enforcing a
#: rule: a company that claims it may settle in stablecoin where the law
#: binding it says otherwise is refused at registration rather than believed.
PAYMENT_BAN_COUNTRIES = frozenset({"TR", "CN", "DZ", "BD", "EG", "MA", "NP", "IQ", "QA", "TN"})
#: The old name, kept so nothing that imports it breaks. It read as though the
#: country of the risk decided the rail, which is what it used to do and was
#: the wrong question.
FIAT_ONLY_COUNTRIES = PAYMENT_BAN_COUNTRIES
_FIAT_ONLY_COUNTRIES = PAYMENT_BAN_COUNTRIES


def unlawful_settlement(carrier: Carrier) -> str:
    """Why this company may not be registered as it stands, or "".

    A company supervised where paying in crypto assets is prohibited may not
    declare a licence that settles in stablecoin -- in any country, to any
    buyer. The prohibition binds the institution, not the policy, so it cannot
    be escaped by writing the risk somewhere else.

    Asked at the door and not in ``Carrier.__post_init__``, which was where it
    went first. A dataclass's validation runs wherever the class is built, and
    one of those places is reading the saved book back off disk. The live book
    already held a Turkish company that had declared it could settle in USDC,
    so the new rule refused to load the record, the book would not open, and
    the service died on startup and kept dying. A rule about what may be
    accepted must not be asked of what was already accepted: the door refuses,
    and :func:`lawful_settlement` repairs what is already inside.
    """
    if carrier.domicile.upper() not in PAYMENT_BAN_COUNTRIES:
        return ""
    for licence in carrier.licences:
        if Settlement.STABLECOIN in licence.settlement:
            return (f"a company supervised in {carrier.domicile.upper()} may not "
                    f"settle in stablecoin: the law binding it prohibits paying "
                    f"in crypto assets, and that holds wherever it writes")
    return ""


def lawful_settlement(registry: "Registry") -> int:
    """Take stablecoin off the licences of companies that may not offer it.

    For books written before the rule existed. The company keeps its licence
    and its country; what it loses is a settlement asset it was never entitled
    to declare, which is the narrowest repair that makes the book lawful. The
    alternative -- refusing to load it -- is what took the service down.
    """
    mended = 0
    for carrier_id, carrier in list(registry.carriers.items()):
        if not unlawful_settlement(carrier):
            continue
        licences = tuple(
            replace(licence, settlement=frozenset(
                a for a in licence.settlement if a is not Settlement.STABLECOIN))
            if Settlement.STABLECOIN in licence.settlement else licence
            for licence in carrier.licences
        )
        # A licence that settled in nothing else is not a licence to write at
        # all; it is dropped rather than left as an empty permission.
        licences = tuple(l for l in licences if l.settlement)
        registry.carriers[carrier_id] = replace(carrier, licences=licences)
        mended += 1
    return mended


def world_specimens(*, now: float | None = None) -> list[Carrier]:
    """One stand in carrier for every inhabited country, and the reinsurer.

    For demonstrating the protocol everywhere at once without registering two
    hundred companies by hand. Each is a specimen like the four above: a name
    no real company could have, no licence reference, the flag the interface
    prints on every policy. Where a peril cannot be priced in a country the
    licence still lists it and the country says it is waiting on a model,
    which is the truth.
    """
    from ..countries import NAMES

    now = time.time() if now is None else now

    # Three in every country, not one. A single stand in per country meant a
    # buyer anywhere outside Türkiye, Japan and Germany was handed a company
    # rather than offered a choice, and a list of one is not a market. They
    # differ on the things a buyer can actually see and weigh: what the company
    # charges on top of the premium, how long a bank payout takes, and how many
    # days beyond the law it gives to change your mind. The cheapest is the
    # slowest and the dearest pays next day, because that is the trade every
    # real market makes.
    #
    # The suffix matters more than it looks: the unsuffixed id is the one an
    # older saved book already holds, so it keeps its terms exactly, and the
    # two new ones are added beside it rather than renumbering anything.
    KINDS = (
        ("", "", 0.05, 3.0, 0.0, 1_000_000.0),
        ("-2", " B", 0.028, 5.0, 0.0, 3_000_000.0),
        ("-3", " C", 0.075, 1.0, 14.0, 5_000_000.0),
    )
    out = []
    for code, name in sorted(NAMES.items()):
        if code in _NO_SPECIMEN:
            continue
        for suffix, letter, fee, days, extra, capacity in KINDS:
            out.append(Carrier(
                specimen=True, contact="specimen, not a company",
                carrier_id=f"specimen-{code.lower()}{suffix}",
                name=f"Specimen Carrier{letter}, {name} (not a real company)",
                role=Role.CARRIER, domicile=code,
                licences=(Licence(
                    country=code,
                    authority="the national insurance supervisor would supervise a real one",
                    reference="SPECIMEN, no licence exists", perils=EVERY_PERIL,
                    reach=Reach.RETAIL,
                    # Keyed on the domicile, which for a stand in is the same
                    # code, but says which of the two it is being read as.
                    settlement=FIAT_ONLY if code in PAYMENT_BAN_COUNTRIES else BOTH_ASSETS,
                    expires_at=now + 2 * YEAR,
                ),),
                appetite=Appetite(max_limit=500_000, max_term_days=400, perils=EVERY_PERIL),
                capacity=capacity, fronting_fee=fee, fiat_payout_days=days,
                extra_cooling_off_days=extra,
            ))
    return out


def add_world_specimens(registry: "Registry", *, now: float | None = None) -> int:
    """Register and approve every stand in not already there. Returns how many."""
    now = time.time() if now is None else now
    added = 0
    if "specimen-reinsurer" not in registry.carriers:
        for carrier in specimen_registry(now=now).carriers.values():
            if carrier.carrier_id not in registry.carriers:
                registry.register(carrier)
                added += 1
    covered = {lic.country for c in registry.carriers.values()
               if c.specimen and c.role is Role.CARRIER
               for lic in c.licences if lic.reach is Reach.RETAIL}
    for carrier in world_specimens(now=now):
        if carrier.carrier_id in registry.carriers:
            have = registry.carriers[carrier.carrier_id]
            # Switched off and on again: a stand in this build suspended
            # comes back; one a reviewer suspended stays suspended.
            if (have.status is Status.SUSPENDED and have.reviews
                    and have.reviews[-1].note == "stand in companies switched off"):
                registry.activate(have.carrier_id, note="stand in companies switched on", now=now)
                added += 1
            continue
        if carrier.domicile in covered and carrier.carrier_id == f"specimen-{carrier.domicile.lower()}":
            continue
        registry.register(carrier)
        registry.activate(carrier.carrier_id, now=now)
        added += 1
    return added


def refresh_specimens(registry: "Registry", *, now: float | None = None) -> int:
    """Bring a stand in's licences up to this build's, keeping its record.

    A book saved by an earlier build carries the stand ins with the perils
    that build knew. A new peril would then be refused everywhere with "a
    company is registered here, but not for this risk", which is true of the
    file and false of the demonstration. A stand in the earlier build did not
    have at all is the same problem and the worse half of it: the day Türkiye
    gained a third carrier so that storm, vehicle flood and flight delay would
    not close when the first one filled, a running deployment kept its saved
    two and stayed closed. So one is registered here if it is missing.

    Only specimens are touched, and only their licences, appetite and
    existence: a real company's licence is what it registered, and nothing
    here rewrites that. Status and reviews stay as they are, so a stand in a
    reviewer suspended stays suspended.
    """
    now = time.time() if now is None else now
    current = {c.carrier_id: c for c in specimen_registry(now=now).carriers.values()}
    current.update({c.carrier_id: c for c in world_specimens(now=now)})
    refreshed = 0
    world = {c.carrier_id for c in world_specimens(now=now)}
    for carrier_id, fresh in current.items():
        have = registry.carriers.get(carrier_id)
        if have is None:
            # A stand in this build has and the saved registry does not. The
            # per-country ones are the switch's business (add_world_specimens
            # puts them in when it is on, retire takes them out when it is
            # off), so only the named few are added back here.
            if carrier_id in world:
                continue
            registry.register(fresh)
            registry.activate(carrier_id, now=now)
            refreshed += 1
            continue
        if not have.specimen:
            continue
        same = (tuple(l.perils for l in have.licences) == tuple(l.perils for l in fresh.licences)
                and have.appetite.perils == fresh.appetite.perils)
        if same:
            continue
        have.licences = fresh.licences
        have.appetite = fresh.appetite
        refreshed += 1
    return refreshed


def retire_world_specimens(registry: "Registry", *, now: float | None = None) -> int:
    """The switch turned off: suspend every stand in carrier still active.

    Suspended rather than deleted, so the policies already on their paper
    still name who issued them and still settle."""
    retired = 0
    for carrier in registry.carriers.values():
        if (carrier.specimen and carrier.carrier_id.startswith(f"specimen-{carrier.domicile.lower()}")
                and carrier.carrier_id not in (
                    "specimen-tr-one", "specimen-tr-two", "specimen-tr-three")
                and carrier.status is Status.ACTIVE):
            registry.suspend(carrier.carrier_id, "stand in companies switched off", now=now)
            retired += 1
    return retired


# The old name, kept so nothing that imported it breaks, and deliberately not
# the name used anywhere new: "opening" suggested these were the companies a
# deployment opens with, and they are not companies at all.
opening_registry = specimen_registry


def priced_by(carrier: Carrier, *, expected_loss: float, marginal_capital: float,
              term_days: float) -> dict[str, float]:
    """One company's price for a risk the model has already measured.

    The simulation runs once. What it produces is the expected loss and the
    capital this policy ties up on top of the book already written, and both
    are facts about the risk rather than about whoever writes it. What each
    company then charges for them is its own: the return its capital must
    earn, and what it costs to run.

    So nine companies share one Monte Carlo and quote nine prices. Before this
    they shared the price as well, to the penny, and differed only in the fee
    they added afterwards, which made a market of nine look like a monopoly
    with nine names.
    """
    risk_load, expense_load, premium = loads_for(
        expected_loss=expected_loss, marginal_capital=marginal_capital,
        term_days=term_days, cost_of_capital=carrier.cost_of_capital,
        expense_ratio=carrier.expense_ratio,
    )
    fee = premium * carrier.fronting_fee
    return {
        "expected_loss": round(float(expected_loss), 2),
        "risk_load": round(risk_load, 2),
        "expense_load": round(expense_load, 2),
        "premium": round(premium, 2),
        "fee": round(fee, 2),
        "total": round(premium + fee, 2),
    }


def most_it_will_write(carrier: Carrier) -> float:
    """The largest single policy this company would put its name to now.

    Two limits, and the smaller binds: what its underwriters will take on one
    risk, and what is left of the book it said it would carry. A buyer
    comparing companies is comparing this as much as the price, because a
    keener price on a smaller line is a different offer, not a better one.
    """
    return round(max(0.0, min(carrier.appetite.max_limit, carrier.headroom())), 2)
