"""What a buyer has to prove, and the reason we never hold the proof.

"Will we ask the buyer to verify some information?" is the right question and it
has a wrong answer that most crypto insurance products give: collect passports
into a database, call it compliance, and become the thing worth attacking. A
protocol that holds ten thousand scanned passports has not reduced anyone's risk,
it has concentrated it, and the moment it is breached every one of those people
is worse off than if they had never been covered.

So the protocol asks for proof and refuses to hold it.

Attestations, not documents
---------------------------
A verifier the carrier already trusts, the kind of firm that runs identity
checks for banks today, does the actual checking: sees the document, keeps it
under whatever regime already governs it, and issues a short signed statement:

    this address passed identity verification at this level,
    on this date, and the statement expires on that one.

The buyer's device holds that statement and presents it. Clause verifies the
signature against the verifier's registered public key and learns one bit per
claim. It never sees a document, a name, a number or a face, and there is
nothing in its storage that a thief would want. This is the shape Rialo
describes under IPC, where identity attributes and eligibility proofs live in
private execution rather than on the public ledger, and it is also simply the
better design regardless of the chain.

What is required scales with what is at stake
---------------------------------------------
Nobody should verify their identity to insure a delayed flight for two hundred.
The requirements come from the size of the cover and the channel it goes
through, so a small policy asks for almost nothing and a large one asks for what
a large one has always asked for:

    every policy         the address is not sanctioned
    above a small limit  identity verified to a basic standard
    above a large limit  identity verified to an enhanced standard
    professional lines   the buyer really is a professional counterparty
    some countries       residence in the country whose carrier is issuing

Checked again before the money leaves
-------------------------------------
A sanctions screening is true on the day it is made and can stop being true the
next. An attestation therefore expires, and the payout path re-runs this whole
check against the attestations as they stand then. A buyer who was added to a
list after binding does not get paid by a protocol that stopped looking, which
is what Rialo means when it says compliance is re-evaluated on every execution
rather than assumed at setup.

Revocation, honestly
--------------------
A verifier can revoke a statement before it expires, and the protocol keeps a
revocation set it is told about. It does not pretend this is instant: an
attestation is trusted until its issuer says otherwise or it expires, and the
expiry windows here are short for exactly that reason.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from .auth import AuthError, _b64, _unb64, _to_der, load_public_key

# How stale a screening may be before it must be redone. Short, because the
# lists it screens against change daily.
SANCTIONS_VALIDITY_DAYS = 30

# Cover above this much, in the unit of account, needs a verified identity.
IDENTITY_THRESHOLD = 10_000.0

# Cover above this much needs the enhanced standard, which is where source of
# funds and beneficial ownership questions live.
ENHANCED_THRESHOLD = 100_000.0


class Claim(str, Enum):
    """The statements a verifier can make about an address."""

    SANCTIONS_CLEAR = "sanctions_clear"
    IDENTITY_BASIC = "identity_basic"
    IDENTITY_ENHANCED = "identity_enhanced"
    PROFESSIONAL = "professional"
    RESIDENCY = "residency"


# Reading them in order of strength, so a stronger claim satisfies a weaker one.
IMPLIES: dict[Claim, frozenset[Claim]] = {
    Claim.IDENTITY_ENHANCED: frozenset({Claim.IDENTITY_BASIC}),
}


class EligibilityError(RuntimeError):
    """An attestation that cannot be accepted as presented."""


@dataclass(frozen=True, slots=True)
class Verifier:
    """A firm whose statements this protocol will accept, and its key."""

    verifier_id: str
    name: str
    public_key: str              # P-256, the same curve as everything else here
    claims: frozenset[Claim]     # what it is trusted to state
    countries: frozenset[str] = frozenset()   # empty means anywhere

    def trusted_for(self, claim: Claim, country: str | None = None) -> bool:
        if claim not in self.claims:
            return False
        if self.countries and country and country.upper() not in self.countries:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifier_id": self.verifier_id,
            "name": self.name,
            "claims": sorted(c.value for c in self.claims),
            "countries": sorted(self.countries),
        }


@dataclass(frozen=True, slots=True)
class Attestation:
    """One signed statement about one address. No document, one bit per claim."""

    subject: str                 # the address it is about
    claim: Claim
    verifier_id: str
    issued_at: float
    expires_at: float
    # The only payload a claim may carry, and only where the claim needs one:
    # a country for residency, nothing for the rest. Deliberately not a place to
    # put a name, a number or a date of birth.
    country: str | None = None
    signature: str = ""

    @property
    def message(self) -> str:
        """Exactly the bytes the verifier signs. Nothing implicit."""
        return (
            f"clause-attestation:v1:{self.subject}:{self.claim.value}:"
            f"{self.verifier_id}:{int(self.issued_at)}:{int(self.expires_at)}:"
            f"{(self.country or '').upper()}"
        )

    @property
    def fingerprint(self) -> str:
        """A handle for revocation that reveals nothing about the subject."""
        return hashlib.blake2b(self.message.encode(), digest_size=16).hexdigest()

    def live(self, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return self.issued_at <= now < self.expires_at

    def satisfies(self, claim: Claim) -> bool:
        return claim == self.claim or claim in IMPLIES.get(self.claim, frozenset())

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim.value,
            "verifier_id": self.verifier_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "country": self.country,
            "live": self.live(),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class Requirement:
    """What this particular purchase has to show."""

    claims: tuple[Claim, ...]
    country: str | None
    because: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [c.value for c in self.claims],
            "country": self.country,
            "because": list(self.because),
        }


@dataclass(frozen=True, slots=True)
class Eligibility:
    """Whether the buyer may proceed, and exactly what is missing if not."""

    ok: bool
    held: tuple[Attestation, ...]
    missing: tuple[Claim, ...]
    reasons: tuple[str, ...]
    requirement: Requirement

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "held": [a.to_dict() for a in self.held],
            "missing": [c.value for c in self.missing],
            "reasons": list(self.reasons),
            "requirement": self.requirement.to_dict(),
        }


WHY = {
    Claim.SANCTIONS_CLEAR: (
        "every policy, everywhere: no carrier may knowingly cover a sanctioned "
        "person, and the screening is only good for a month"
    ),
    Claim.IDENTITY_BASIC: (
        f"cover above {IDENTITY_THRESHOLD:,.0f}: the carrier's regulator requires "
        f"it to know who its policyholder is"
    ),
    Claim.IDENTITY_ENHANCED: (
        f"cover above {ENHANCED_THRESHOLD:,.0f}: the enhanced standard, which is "
        f"where source of funds is asked about"
    ),
    Claim.PROFESSIONAL: (
        "this is an index contract rather than consumer insurance, and it may "
        "only be sold to an informed counterparty"
    ),
    Claim.RESIDENCY: (
        "the carrier issuing this is licensed for residents of one country and "
        "may not write outside it"
    ),
}


class EligibilityEngine:
    """Registered verifiers, and the check that runs twice."""

    def __init__(self, verifiers: Iterable[Verifier] = ()) -> None:
        self.verifiers: dict[str, Verifier] = {v.verifier_id: v for v in verifiers}
        # Fingerprints a verifier has told us to stop trusting.
        self.revoked: set[str] = set()

    def trust(self, verifier: Verifier) -> Verifier:
        self.verifiers[verifier.verifier_id] = verifier
        return verifier

    def revoke(self, fingerprint: str) -> None:
        self.revoked.add(fingerprint)

    # -- what is needed ---------------------------------------------------

    def requirement(
        self, *, limit: float, professional: bool, country: str,
        residency_required: bool = False,
    ) -> Requirement:
        claims: list[Claim] = [Claim.SANCTIONS_CLEAR]
        because: list[str] = [WHY[Claim.SANCTIONS_CLEAR]]

        if limit > ENHANCED_THRESHOLD:
            claims.append(Claim.IDENTITY_ENHANCED)
            because.append(WHY[Claim.IDENTITY_ENHANCED])
        elif limit > IDENTITY_THRESHOLD:
            claims.append(Claim.IDENTITY_BASIC)
            because.append(WHY[Claim.IDENTITY_BASIC])

        if professional:
            claims.append(Claim.PROFESSIONAL)
            because.append(WHY[Claim.PROFESSIONAL])

        if residency_required:
            claims.append(Claim.RESIDENCY)
            because.append(WHY[Claim.RESIDENCY])

        return Requirement(tuple(claims), country.upper(), tuple(because))

    # -- verifying what is presented --------------------------------------

    def verify(self, attestation: Attestation, *, now: float | None = None) -> None:
        """Check one statement's signature, freshness and issuer. Raises if bad."""
        verifier = self.verifiers.get(attestation.verifier_id)
        if verifier is None:
            raise EligibilityError("that verifier is not trusted here")
        if not verifier.trusted_for(attestation.claim, attestation.country):
            raise EligibilityError(
                "that verifier is not trusted to make that statement"
            )
        if not attestation.live(now=now):
            raise EligibilityError("that statement has expired")
        if attestation.fingerprint in self.revoked:
            raise EligibilityError("that statement was withdrawn by its issuer")
        if attestation.claim is Claim.SANCTIONS_CLEAR:
            age = (time.time() if now is None else now) - attestation.issued_at
            if age > SANCTIONS_VALIDITY_DAYS * 86400:
                raise EligibilityError("that screening is too old to rely on")

        key = load_public_key(verifier.public_key)
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec

            key.verify(
                _to_der(_unb64(attestation.signature)),
                attestation.message.encode(),
                ec.ECDSA(hashes.SHA256()),
            )
        except AuthError:
            raise
        except Exception as error:  # noqa: BLE001 - any failure is the same failure
            raise EligibilityError("that statement does not verify") from error

    def check(
        self,
        *,
        address: str,
        attestations: Iterable[Attestation],
        requirement: Requirement,
        now: float | None = None,
    ) -> Eligibility:
        """Everything the buyer presented, against everything this purchase needs."""
        good: list[Attestation] = []
        reasons: list[str] = []

        for attestation in attestations:
            if attestation.subject != address:
                reasons.append("a statement was about a different address")
                continue
            try:
                self.verify(attestation, now=now)
            except (EligibilityError, AuthError) as error:
                reasons.append(str(error))
                continue
            good.append(attestation)

        missing: list[Claim] = []
        for claim in requirement.claims:
            if not any(a.satisfies(claim) for a in good):
                missing.append(claim)
                continue
            if claim is Claim.RESIDENCY and requirement.country:
                held = [a for a in good if a.satisfies(claim)]
                if not any(
                    (a.country or "").upper() == requirement.country for a in held
                ):
                    missing.append(claim)
                    reasons.append(
                        f"residency was attested for another country, and the "
                        f"carrier here is licensed for {requirement.country}"
                    )

        return Eligibility(
            ok=not missing,
            held=tuple(good),
            missing=tuple(missing),
            reasons=tuple(reasons),
            requirement=requirement,
        )

    def recheck_at_settlement(
        self, *, address: str, attestations: Iterable[Attestation],
        requirement: Requirement, now: float | None = None,
    ) -> Eligibility:
        """The same check, before the payout runs.

        Not a formality. A screening that was clean at binding expires inside a
        month, and a statement its issuer has withdrawn stops counting the
        moment we are told. A protocol that checked once would pay a person it
        is no longer permitted to pay, and would find out from a regulator.
        """
        return self.check(
            address=address, attestations=attestations,
            requirement=requirement, now=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifiers": [v.to_dict() for v in self.verifiers.values()],
            "thresholds": {
                "identity": IDENTITY_THRESHOLD,
                "enhanced": ENHANCED_THRESHOLD,
                "sanctions_validity_days": SANCTIONS_VALIDITY_DAYS,
            },
            "revoked": len(self.revoked),
        }
