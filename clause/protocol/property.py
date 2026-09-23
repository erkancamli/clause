"""Properties, and who has already proved that one is theirs.

Nothing stopped two people insuring the same flat, or one person insuring it
twice. For a parametric cover that is not a loophole at the edge, it is the
centre: this pays on an index rather than on a loss, so two policies on one
home pay twice for the same earthquake, and nobody has to file a claim for it
to happen. Indemnity insurance is protected from that by the loss itself —
you cannot be paid twice for one roof. Here the protection has to be written.

What is and is not wrong
------------------------
A building being insured by several people is ordinary and right. Every flat
in a block has its own owner; a landlord and a tenant hold different interests
in the same rooms; a lender holds a third. None of that is double insurance.

Two things are wrong, and both were possible:

    the same person holding two covers on the same thing for the same peril,
    which pays twice for one event; and

    somebody insuring a property they have no interest in, which is a wager
    on a stranger's misfortune and is why insurable interest exists at all.

So the register holds three rules:

    a   one holder, one property, one peril: a second cover while the first
        is in force is refused, and the policy they already hold is named.

    b   every holder together: cover in force on one property cannot exceed
        what the property is worth. Flats in one block are separate
        properties; a building with no flat named is one.

    c   each holder alone: their cover cannot exceed the interest they
        declared and, where it was checked, the interest they proved.

What "verified" means, and what it does not
-------------------------------------------
A property is verified for a holder when an issuing company accepts the paper
that shows it is theirs — a title deed, a lease, a registration — which is a
decision a person makes on a document, recorded with who made it. It is not a
search of a land registry: this protocol holds no such connection and does not
pretend to. Where a national register can be called, that call belongs here
and the record says which of the two it was.

Verification is what makes rule (c) more than a number somebody typed, and it
is what lets a property be exclusive: once a flat is proved to be one
person's, another address cannot insure that flat. Exclusivity is claimed only
for an address that names a single dwelling. An address with no flat number in
a block of them is the building, not a home in it, and treating it as one
person's would lock out every neighbour.
"""

from __future__ import annotations

import hashlib
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable


class PropertyError(ValueError):
    """A refusal this module makes. The message is safe to show."""


def fold(text: str) -> str:
    """Case, accents and spacing off, so one street is not two properties.

    "Atatürk Cad." and "ATATURK CAD" are the same street written by two
    people, and a register that made them different properties would enforce
    none of its rules.
    """
    lowered = str(text or "").translate(str.maketrans({"İ": "i", "I": "i", "ı": "i"})).lower()
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFKD", lowered)
        if not unicodedata.combining(ch)
    )
    return " ".join(ch for ch in stripped.split() if ch)


@dataclass(frozen=True, slots=True)
class PropertyKey:
    """What identifies one property, and whether it identifies a home in it."""

    property_id: str
    #: True when the address names a single dwelling — a flat number, or a
    #: house or shop at its own street number. Only these can be exclusive.
    unit_level: bool
    where: str      # the address as one line, for saying which property


def key_for(
    address: dict[str, Any] | None,
    *,
    country: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    building: str = "",
) -> PropertyKey | None:
    """The key for an address, or None when there is not enough to identify one.

    The coordinate is rounded to about a hundred metres and joined to the
    street and number, so that a street name spelled two ways still lands on
    one property and two streets of the same name in two cities do not merge.
    """
    address = address or {}
    street = fold(address.get("street", ""))
    number = fold(address.get("number", ""))
    flat = fold(address.get("flat", ""))
    city = fold(address.get("city", ""))
    postcode = fold(address.get("postcode", ""))
    if not street or not (city or postcode):
        return None
    cell = ""
    if latitude is not None and longitude is not None:
        cell = f"{round(float(latitude), 3):.3f},{round(float(longitude), 3):.3f}"
    parts = [country.upper(), city, postcode, street, number, flat, cell]
    digest = hashlib.blake2b("|".join(parts).encode(), digest_size=10).hexdigest()
    unit = bool(flat) or (building in ("house", "shop") and bool(number))
    line = ", ".join(
        str(address.get(k, "")) for k in ("street", "number", "flat", "postcode", "city")
        if address.get(k)
    )
    return PropertyKey(f"PRP-{digest.upper()}", unit, line)


@dataclass(slots=True)
class Holding:
    """One holder's proved interest in one property."""

    property_id: str
    holder: str
    where: str
    unit_level: bool
    value_at_risk: float
    verified_at: float
    verified_by: str            # the carrier that accepted the paper
    by_register: bool = False   # a national register answered, rather than a person
    application_id: str = ""
    country: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_id": self.property_id, "holder": self.holder, "where": self.where,
            "unit_level": self.unit_level, "value_at_risk": round(self.value_at_risk, 2),
            "verified_at": self.verified_at, "verified_by": self.verified_by,
            "by_register": self.by_register, "application_id": self.application_id,
            "country": self.country,
        }


@dataclass(slots=True)
class Cover:
    """A policy in force on a property, as the register needs to see it."""

    property_id: str
    holder: str
    peril: str
    limit: float
    policy_id: str


class Register:
    """Which properties are proved to be whose, and what is in force on them."""

    def __init__(self) -> None:
        self.holdings: dict[str, Holding] = {}      # "property_id|holder"
        self.in_force: list[Cover] = []
        self.lock = threading.RLock()

    # -- what is proved ---------------------------------------------------

    @staticmethod
    def pair(property_id: str, holder: str) -> str:
        return f"{property_id}|{holder}"

    def verify(
        self, key: PropertyKey, holder: str, *, value_at_risk: float, by: str,
        by_register: bool = False, application_id: str = "", country: str = "",
        now: float | None = None,
    ) -> Holding:
        """Record that a holder proved this property is theirs."""
        with self.lock:
            held = Holding(
                property_id=key.property_id, holder=holder, where=key.where,
                unit_level=key.unit_level, value_at_risk=float(value_at_risk),
                verified_at=now if now is not None else time.time(),
                verified_by=by, by_register=by_register,
                application_id=application_id, country=country.upper(),
            )
            self.holdings[self.pair(key.property_id, holder)] = held
            return held

    def holding(self, property_id: str, holder: str) -> Holding | None:
        return self.holdings.get(self.pair(property_id, holder))

    def holders_of(self, property_id: str) -> list[Holding]:
        return [h for h in self.holdings.values() if h.property_id == property_id]

    def mine(self, holder: str) -> list[Holding]:
        return [h for h in self.holdings.values() if h.holder == holder]

    # -- what is in force -------------------------------------------------

    def reconcile(self, policies: Iterable[Any]) -> None:
        """Rebuild the in-force index from the book.

        Read rather than kept, for the same reason the carrier registry reads
        its own exposure from the book: two records of one fact drift, and the
        book is the one that decides. What is read is the property identifier
        the policy carries, never an address: the address is not on the policy
        record, on purpose, and this does not put it there.
        """
        covers: list[Cover] = []
        for policy in policies:
            if not getattr(policy, "is_open", False):
                continue
            meta = getattr(policy, "metadata", None) or {}
            # The identifier the policy carries. The address is not on the
            # record and must not be put there, so a policy written before
            # this existed names no property and is not counted; what it
            # cannot do is make the register wrong about the ones that do.
            place = meta.get("property") or {}
            property_id = str(place.get("id") or "")
            if not property_id:
                continue
            covers.append(Cover(
                property_id=property_id, holder=getattr(policy, "holder", ""),
                peril=getattr(policy, "peril_key", ""), limit=float(getattr(policy, "limit", 0.0)),
                policy_id=getattr(policy, "policy_id", ""),
            ))
        with self.lock:
            self.in_force = covers

    def on(self, property_id: str, *, peril: str = "", holder: str = "") -> list[Cover]:
        return [
            c for c in self.in_force
            if c.property_id == property_id
            and (not peril or c.peril == peril)
            and (not holder or c.holder == holder)
        ]

    # -- the three rules --------------------------------------------------

    def may_write(
        self, key: PropertyKey, holder: str, *, peril: str, limit: float,
        declared: float, property_value: float | None = None,
    ) -> tuple[bool, list[str]]:
        """Whether this cover may be written on this property, and why not."""
        reasons: list[str] = []
        with self.lock:
            # (a) The same holder, the same property, the same peril.
            already = self.on(key.property_id, peril=peril, holder=holder)
            if already:
                reasons.append(
                    f"you already hold cover on this property for this peril "
                    f"({already[0].policy_id}); a second one would pay twice for "
                    f"one event, so it is refused rather than sold"
                )

            # (c) This holder's own cover against what they declared. Across
            # every peril, not within one: an interest of fifty thousand in a
            # flat is fifty thousand whether the wind or the ground takes it,
            # and forty of earthquake beside forty of storm is eighty on a
            # fifty thousand flat. That is what a sum insured means.
            held = self.holding(key.property_id, holder)
            ceiling = min(declared, held.value_at_risk) if held else declared
            mine = sum(c.limit for c in self.on(key.property_id, holder=holder))
            if ceiling > 0 and mine + limit > ceiling + 0.01:
                reasons.append(
                    f"cover of {mine + limit:,.0f} on this property would be more "
                    f"than the {ceiling:,.0f} you have at risk in it"
                )

            # (b) Everybody's cover against what the property is worth, across
            # every peril for the same reason.
            if property_value and property_value > 0:
                everyone = sum(c.limit for c in self.on(key.property_id))
                if everyone + limit > property_value + 0.01:
                    reasons.append(
                        f"cover on this property already comes to {everyone:,.0f} of "
                        f"its {property_value:,.0f}; another {limit:,.0f} would insure "
                        f"it for more than it is worth"
                    )

            # Exclusivity, and only for an address that names one home.
            if key.unit_level:
                others = [h for h in self.holders_of(key.property_id) if h.holder != holder]
                if others and self.holding(key.property_id, holder) is None:
                    reasons.append(
                        "this home has already been proved to belong to somebody "
                        "else; if it is yours, the company that issues the cover "
                        "will want to see the paper that says so"
                    )
        return (not reasons), reasons
