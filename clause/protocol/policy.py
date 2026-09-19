"""A policy, from quote to settlement.

Every policy carries the three things that make it parametric: the index it
settles on, the structure that says what is paid at each level of that index,
and the onchain predicate that makes the chain do the paying. Nothing here
depends on a claims process, because there is not one.

The lifecycle has one state most parametric designs leave out. A policy whose
data source never reports cannot settle either way, and leaving it armed
forever means the pool quietly keeps a premium against an event nobody can
observe. That state is EXPIRED, it is reached by a deadline written into the
contract at purchase, and it returns the premium.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..perils import DataSource, PayoutCurve, Peril, get_peril


class PolicyStatus(str, Enum):
    ACTIVE = "active"        # armed, waiting on its index
    PAID = "paid"            # the index triggered and the payout settled
    LAPSED = "lapsed"        # the term ended with no trigger
    EXPIRED = "expired"      # the data never arrived, premium returned
    CANCELLED = "cancelled"  # withdrawn before cover began


TERMINAL = {PolicyStatus.PAID, PolicyStatus.LAPSED, PolicyStatus.EXPIRED,
            PolicyStatus.CANCELLED}


def _policy_id(*parts: Any) -> str:
    """A short, stable identifier from the policy's own terms."""
    digest = hashlib.blake2b(
        "|".join(str(part) for part in parts).encode(), digest_size=8
    ).hexdigest()
    return f"CLS-{digest[:12].upper()}"


@dataclass(slots=True)
class Policy:
    """One parametric cover."""

    policy_id: str
    peril_key: str
    subject: dict[str, Any]
    curve: PayoutCurve
    limit: float
    term_days: float
    premium: float
    expected_loss: float
    risk_load: float
    expense_load: float
    marginal_capital: float
    predicate: str
    data_reference: str
    settlement_deadline_days: int
    holder: str
    bought_at: float
    starts_at: float
    ends_at: float
    status: PolicyStatus = PolicyStatus.ACTIVE
    settled_at: float | None = None
    settled_index: float | None = None
    payout: float = 0.0
    settlement_note: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # -- derived ----------------------------------------------------------

    @property
    def peril(self) -> Peril:
        return get_peril(self.peril_key)

    @property
    def term_years(self) -> float:
        return self.term_days / 365.25

    @property
    def is_open(self) -> bool:
        return self.status is PolicyStatus.ACTIVE

    @property
    def deadline_at(self) -> float:
        """The moment after which missing data expires the policy."""
        return self.ends_at + self.settlement_deadline_days * 86400

    def exposure_remaining(self) -> float:
        """What the pool could still have to pay on this policy."""
        return self.limit if self.is_open else 0.0

    def describe(self) -> str:
        peril = self.peril
        return f"{peril.title_for(self.subject)}: {peril.describe_subject(self.subject)}"

    def to_dict(self) -> dict[str, Any]:
        peril = self.peril
        return {
            "policy_id": self.policy_id,
            "peril": self.peril_key,
            "peril_name": peril.title_for(self.subject),
            "subject": dict(self.subject),
            "subject_text": peril.describe_subject(self.subject),
            "structure": self.curve.describe(peril.unit_for(self.subject)),
            "unit": peril.unit_for(self.subject),
            "limit": round(self.limit, 2),
            "premium": round(self.premium, 2),
            "expected_loss": round(self.expected_loss, 2),
            "risk_load": round(self.risk_load, 2),
            "expense_load": round(self.expense_load, 2),
            "marginal_capital": round(self.marginal_capital, 2),
            "term_days": self.term_days,
            "predicate": self.predicate,
            "data_reference": self.data_reference,
            "settlement_deadline_days": self.settlement_deadline_days,
            "holder": self.holder,
            "status": self.status.value,
            "bought_at": self.bought_at,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "deadline_at": self.deadline_at,
            "settled_at": self.settled_at,
            "settled_index": self.settled_index,
            "payout": round(self.payout, 2),
            "settlement_note": self.settlement_note,
            "basis_risk": peril.basis_risk,
            "basis_risk_level": peril.basis_risk_level,
            "metadata": dict(self.metadata),
        }


def build_policy(
    *,
    peril_key: str,
    subject: dict[str, Any],
    limit: float,
    term_days: float,
    holder: str,
    premium: float,
    expected_loss: float,
    risk_load: float,
    expense_load: float,
    marginal_capital: float,
    curve: PayoutCurve | None = None,
    now: float | None = None,
    starts_in_days: float = 0.0,
) -> Policy:
    """Assemble a policy from a priced quote.

    The predicate and the data reference are fixed here, at purchase, and are
    what the chain will act on. Neither the pool nor the holder can change them
    afterwards, which is the whole basis on which the cover can settle itself.
    """
    peril = get_peril(peril_key)
    subject = peril.validate_subject(subject)
    curve = curve or peril.curve_for(subject)
    source: DataSource = peril.data_source(subject)

    now = now if now is not None else time.time()
    starts_at = now + starts_in_days * 86400
    ends_at = starts_at + term_days * 86400

    identifier = _policy_id(peril_key, sorted(subject.items()), limit, holder, now)

    return Policy(
        policy_id=identifier,
        peril_key=peril_key,
        subject=subject,
        curve=curve,
        limit=limit,
        term_days=term_days,
        premium=premium,
        expected_loss=expected_loss,
        risk_load=risk_load,
        expense_load=expense_load,
        marginal_capital=marginal_capital,
        predicate=peril.predicate(subject, curve, identifier),
        data_reference=source.reference,
        settlement_deadline_days=source.settlement_deadline_days,
        holder=holder,
        bought_at=now,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def settle_index(policy: Policy, index_value: float) -> float:
    """What a policy pays at an observed index value."""
    peril = policy.peril
    curve = (
        peril.curve_in_mm(policy.subject, policy.curve)
        if policy.peril_key == "drought"
        else policy.curve
    )
    return curve.payout(index_value, policy.limit)
