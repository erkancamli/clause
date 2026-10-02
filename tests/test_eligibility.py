"""What a buyer has to prove, and why the protocol never holds the proof.

The design claim being tested is narrow and worth stating: this protocol can
enforce identity and sanctions requirements without ever seeing a document, a
name or a number. If these tests pass, there is nothing in this service's
storage that is worth stealing from the people who use it, and that is a
property of the code rather than a promise in a policy page.
"""

from __future__ import annotations

import base64
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from clause.protocol.eligibility import (
    ENHANCED_THRESHOLD,
    IDENTITY_THRESHOLD,
    SANCTIONS_VALIDITY_DAYS,
    Attestation,
    Claim,
    EligibilityEngine,
    EligibilityError,
    Verifier,
)

ADDRESS = "0x" + "ab" * 20
OTHER = "0x" + "cd" * 20


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class Firm:
    """An identity verifier: it looks at the document and signs one sentence."""

    def __init__(self, verifier_id="acme-id", claims=None, countries=frozenset()):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.verifier_id = verifier_id
        self.claims = claims or frozenset({
            Claim.SANCTIONS_CLEAR, Claim.IDENTITY_BASIC,
            Claim.IDENTITY_ENHANCED, Claim.RESIDENCY,
        })
        self.countries = countries

    @property
    def registration(self) -> Verifier:
        raw = self.key.public_key().public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        )
        return Verifier(
            verifier_id=self.verifier_id, name="Acme Identity",
            public_key=b64(raw), claims=self.claims, countries=self.countries,
        )

    def state(self, claim, *, subject=ADDRESS, issued_at=None, days=180,
              country=None, browser=False) -> Attestation:
        issued_at = time.time() if issued_at is None else issued_at
        draft = Attestation(
            subject=subject, claim=claim, verifier_id=self.verifier_id,
            issued_at=issued_at, expires_at=issued_at + days * 86400,
            country=country,
        )
        der = self.key.sign(draft.message.encode(), ec.ECDSA(hashes.SHA256()))
        if browser:
            r, s = decode_dss_signature(der)
            signature = b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        else:
            signature = b64(der)
        return Attestation(
            subject=draft.subject, claim=draft.claim,
            verifier_id=draft.verifier_id, issued_at=draft.issued_at,
            expires_at=draft.expires_at, country=draft.country,
            signature=signature,
        )


@pytest.fixture
def firm() -> Firm:
    return Firm()


@pytest.fixture
def engine(firm) -> EligibilityEngine:
    return EligibilityEngine([firm.registration])


def need(engine, *, limit=50_000.0, professional=False, country="TR", residency=False):
    return engine.requirement(
        limit=limit, professional=professional, country=country,
        residency_required=residency,
    )


# ---------------------------------------------------------------------------
# What is asked for scales with what is at stake
# ---------------------------------------------------------------------------


def test_a_small_policy_asks_only_that_you_are_not_sanctioned(engine) -> None:
    """Nobody should verify their identity to insure a delayed flight."""
    assert need(engine, limit=800.0).claims == (Claim.SANCTIONS_CLEAR,)


def test_a_larger_policy_asks_who_you_are(engine) -> None:
    assert Claim.IDENTITY_BASIC in need(engine, limit=IDENTITY_THRESHOLD + 1).claims


def test_a_large_policy_asks_the_enhanced_standard(engine) -> None:
    claims = need(engine, limit=ENHANCED_THRESHOLD + 1).claims
    assert Claim.IDENTITY_ENHANCED in claims
    assert Claim.IDENTITY_BASIC not in claims, "the stronger one stands in"


def test_the_two_thresholds_are_the_figures_they_are_meant_to_be() -> None:
    """Asked as figures, because asking at THRESHOLD + 1 asks the constant
    about itself: raised to 1e9 it would mean nobody is ever asked to verify
    their identity, and an independent pass measured 73 tests passing with
    exactly that.

    These are the amounts of cover at which more is asked of a buyer. Moving
    one is a compliance decision, so it fails here and is re-pinned
    deliberately.
    """
    assert IDENTITY_THRESHOLD == 10_000.0
    assert ENHANCED_THRESHOLD == 100_000.0


def test_what_is_asked_for_at_each_figure(engine) -> None:
    """The ladder itself, at amounts rather than at the constants, so a
    threshold that moves is seen from the outside."""
    assert need(engine, limit=800.0).claims == (Claim.SANCTIONS_CLEAR,)
    assert need(engine, limit=9_999.0).claims == (Claim.SANCTIONS_CLEAR,)
    at_ten = need(engine, limit=10_001.0).claims
    assert Claim.IDENTITY_BASIC in at_ten
    assert Claim.IDENTITY_ENHANCED not in at_ten
    at_a_hundred = need(engine, limit=100_001.0).claims
    assert Claim.IDENTITY_ENHANCED in at_a_hundred
    assert Claim.IDENTITY_BASIC not in at_a_hundred


def test_an_index_contract_asks_whether_you_are_really_a_professional(engine) -> None:
    assert Claim.PROFESSIONAL in need(engine, professional=True).claims


def test_every_requirement_says_why_each_thing_is_asked_for(engine) -> None:
    """A request for identification with no stated reason is how this goes wrong."""
    requirement = need(engine, limit=ENHANCED_THRESHOLD + 1, professional=True)
    assert len(requirement.because) == len(requirement.claims)
    assert all(text.strip() for text in requirement.because)


# ---------------------------------------------------------------------------
# The statement, and the ways of failing to make one
# ---------------------------------------------------------------------------


def test_a_correctly_signed_statement_passes(engine, firm) -> None:
    result = engine.check(
        address=ADDRESS, attestations=[firm.state(Claim.SANCTIONS_CLEAR)],
        requirement=need(engine, limit=800.0),
    )
    assert result.ok


def test_a_statement_from_a_browser_passes_too(engine, firm) -> None:
    """WebCrypto emits r then s raw. A verifier running in a page is plausible."""
    result = engine.check(
        address=ADDRESS,
        attestations=[firm.state(Claim.SANCTIONS_CLEAR, browser=True)],
        requirement=need(engine, limit=800.0),
    )
    assert result.ok


def test_a_statement_about_someone_else_does_not_count(engine, firm) -> None:
    """Otherwise one verified person carries everybody."""
    result = engine.check(
        address=ADDRESS,
        attestations=[firm.state(Claim.SANCTIONS_CLEAR, subject=OTHER)],
        requirement=need(engine, limit=800.0),
    )
    assert not result.ok
    assert "different address" in " ".join(result.reasons)


def test_a_forged_statement_does_not_verify(engine, firm) -> None:
    impostor = Firm(verifier_id=firm.verifier_id)      # same name, different key
    result = engine.check(
        address=ADDRESS, attestations=[impostor.state(Claim.SANCTIONS_CLEAR)],
        requirement=need(engine, limit=800.0),
    )
    assert not result.ok
    assert "does not verify" in " ".join(result.reasons)


def test_a_statement_from_a_firm_we_do_not_know_is_refused(engine) -> None:
    stranger = Firm(verifier_id="who-is-this")
    result = engine.check(
        address=ADDRESS, attestations=[stranger.state(Claim.SANCTIONS_CLEAR)],
        requirement=need(engine, limit=800.0),
    )
    assert not result.ok
    assert "not trusted" in " ".join(result.reasons)


def test_a_firm_can_only_state_what_it_is_trusted_for(engine) -> None:
    """A sanctions screener is not an accreditation body."""
    narrow = Firm(verifier_id="screener", claims=frozenset({Claim.SANCTIONS_CLEAR}))
    engine.trust(narrow.registration)
    result = engine.check(
        address=ADDRESS, attestations=[narrow.state(Claim.PROFESSIONAL)],
        requirement=need(engine, professional=True),
    )
    assert Claim.PROFESSIONAL in result.missing


def test_a_firm_trusted_in_one_country_cannot_speak_for_another() -> None:
    local = Firm(verifier_id="tr-only", countries=frozenset({"TR"}))
    engine = EligibilityEngine([local.registration])
    good = local.state(Claim.RESIDENCY, country="TR")
    bad = local.state(Claim.RESIDENCY, country="DE")
    assert engine.check(
        address=ADDRESS, attestations=[good, local.state(Claim.SANCTIONS_CLEAR)],
        requirement=need(engine, limit=800.0, residency=True, country="TR"),
    ).ok
    with pytest.raises(EligibilityError):
        engine.verify(bad)


def test_residency_has_to_be_for_the_country_the_carrier_is_licensed_in(engine, firm) -> None:
    result = engine.check(
        address=ADDRESS,
        attestations=[
            firm.state(Claim.SANCTIONS_CLEAR),
            firm.state(Claim.RESIDENCY, country="DE"),
        ],
        requirement=need(engine, limit=800.0, residency=True, country="TR"),
    )
    assert not result.ok
    assert Claim.RESIDENCY in result.missing


# ---------------------------------------------------------------------------
# Statements go stale, and that is the point
# ---------------------------------------------------------------------------


def test_an_expired_statement_does_not_count(engine, firm) -> None:
    stale = firm.state(Claim.SANCTIONS_CLEAR, issued_at=time.time() - 400 * 86400)
    result = engine.check(
        address=ADDRESS, attestations=[stale],
        requirement=need(engine, limit=800.0),
    )
    assert not result.ok
    assert "expired" in " ".join(result.reasons)


def test_a_screening_older_than_a_month_is_refused_even_if_unexpired(engine, firm) -> None:
    """A sanctions list changes daily. A year old clearance is not a clearance."""
    old = firm.state(
        Claim.SANCTIONS_CLEAR,
        issued_at=time.time() - (SANCTIONS_VALIDITY_DAYS + 5) * 86400,
        days=365,
    )
    result = engine.check(
        address=ADDRESS, attestations=[old], requirement=need(engine, limit=800.0),
    )
    assert not result.ok
    assert "too old" in " ".join(result.reasons)


def test_a_withdrawn_statement_stops_counting(engine, firm) -> None:
    statement = firm.state(Claim.SANCTIONS_CLEAR)
    requirement = need(engine, limit=800.0)
    assert engine.check(
        address=ADDRESS, attestations=[statement], requirement=requirement
    ).ok

    engine.revoke(statement.fingerprint)
    after = engine.check(
        address=ADDRESS, attestations=[statement], requirement=requirement
    )
    assert not after.ok
    assert "withdrawn" in " ".join(after.reasons)


def test_the_whole_thing_runs_again_before_the_payout(engine, firm) -> None:
    """Rialo re-evaluates compliance on every execution, and so does this: a
    person added to a list after binding is not paid by a protocol that stopped
    looking."""
    statement = firm.state(Claim.SANCTIONS_CLEAR)
    requirement = need(engine, limit=800.0)
    assert engine.check(
        address=ADDRESS, attestations=[statement], requirement=requirement
    ).ok

    engine.revoke(statement.fingerprint)
    assert not engine.recheck_at_settlement(
        address=ADDRESS, attestations=[statement], requirement=requirement
    ).ok


# ---------------------------------------------------------------------------
# What is not held
# ---------------------------------------------------------------------------


def test_a_statement_carries_no_identity_beyond_one_bit(firm) -> None:
    """The reason a breach of this service exposes nobody.

    The only payload a statement may carry is a country, and only for the claim
    that needs one. There is nowhere in it to put a name, a document number or
    a date of birth, so there is nowhere for one to end up in our storage.
    """
    statement = firm.state(Claim.IDENTITY_ENHANCED)
    fields = set(statement.to_dict())
    assert fields == {
        "claim", "verifier_id", "issued_at", "expires_at", "country",
        "live", "fingerprint",
    }
    assert Attestation.__slots__ == (
        "subject", "claim", "verifier_id", "issued_at", "expires_at",
        "country", "signature",
    )


def test_the_fingerprint_reveals_nothing_about_the_subject(firm) -> None:
    """It is how a verifier withdraws a statement without naming the person."""
    statement = firm.state(Claim.IDENTITY_BASIC)
    assert ADDRESS not in statement.fingerprint
    assert len(statement.fingerprint) == 32


def test_a_stronger_claim_satisfies_a_weaker_one(engine, firm) -> None:
    """Somebody verified to the enhanced standard is verified."""
    result = engine.check(
        address=ADDRESS,
        attestations=[
            firm.state(Claim.SANCTIONS_CLEAR),
            firm.state(Claim.IDENTITY_ENHANCED),
        ],
        requirement=need(engine, limit=IDENTITY_THRESHOLD + 1),
    )
    assert result.ok


def test_what_is_missing_is_named_rather_than_merely_refused(engine, firm) -> None:
    """So the interface can ask for exactly the thing that is absent."""
    result = engine.check(
        address=ADDRESS, attestations=[firm.state(Claim.SANCTIONS_CLEAR)],
        requirement=need(engine, limit=ENHANCED_THRESHOLD + 1),
    )
    assert not result.ok
    assert result.missing == (Claim.IDENTITY_ENHANCED,)
