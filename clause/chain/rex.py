"""REX: the web call, performed by every validator, and what to do when they disagree.

Rialo reads a Web2 API from inside the chain through REX. The published shape of
that mechanism is specific and worth stating exactly, because it decides how an
insurance contract can be written on top of it.

Each validator performs the duty itself and produces its own ``RexUpdate``,
tagged with its authority key. Every validator's update, not a single agreed
figure, is bundled into a ``RexReport`` for the round and written to an account,
which emits an event that subscriptions match on.

    RexResponse -> RexOutput -> RexUpdate.data -> RexReport.updates

So what lands on chain is a set of independent measurements. Reconciling them is
delegated to a separate aggregator program, and the default aggregator's rule is
not published: there is no documented quorum, no median rule, no dispute path and
no stated behaviour when validators disagree or time out.

That gap is ordinary for a young chain and fatal for an insurer, because the
disagreement case is not hypothetical. Two seismic networks routinely publish
magnitudes a tenth apart for the same event. A policy attaching at magnitude 5.5
settles differently depending on which of 5.49 and 5.51 the chain believes, and
"whichever validator answered first" is not an answer a buyer can be sold.

So Clause specifies its own aggregation, in the contract, in advance:

  Quorum.      A reading settles only when at least a stated share of validators
               reported. Below that, the index is treated as unpublished, which
               eventually returns the premium rather than paying an arbitrary
               number.

  Median.      The agreed value is the median of the reports, not the mean. One
               validator reading a corrupted feed moves a mean and does not move
               a median.

  Dispersion.  If the validators disagree by more than a stated tolerance, the
               reading is refused rather than aggregated. A contract that pays on
               a number the network could not agree on is not parametric cover,
               it is a lottery on which validator was fastest.

Every one of those three is a term of the policy and is shown to the buyer before
they pay. That is the honest way to build on an unspecified aggregator: state the
rule you are relying on, rather than inherit whatever a future default turns out
to be.
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

# Rialo's devnet runs four validators, equally staked, all operated by Rialo
# itself. The number here follows that so the demonstration matches the network
# a reviewer can actually query, not an imagined one.
DEVNET_VALIDATORS = 4

# A reading needs this share of the validator set before it counts. Three of
# four: enough that one silent or slow validator does not stall settlement, and
# not so low that a single reporter decides a payout.
QUORUM_SHARE = 0.75

# How far validators may disagree and still be aggregated, as a share of the
# median. Beyond this the reading is refused.
DISPERSION_TOLERANCE = 0.05

# Validator authority keys on Rialo are 96 byte BLS12-381 public keys. These are
# display stand ins of the right shape; nothing depends on their internals.
_KEY_BYTES = 48


class Agreement(str, Enum):
    """What the aggregator concluded about a round of reports."""

    AGREED = "agreed"            # quorum met, dispersion inside tolerance
    NO_QUORUM = "no_quorum"      # too few validators reported
    DISPUTED = "disputed"        # they reported, and did not agree


def authority_key(validator: str) -> str:
    """A validator's authority key, in the display form Rialo uses."""
    digest = hashlib.blake2b(validator.encode(), digest_size=_KEY_BYTES).hexdigest()
    return "0x" + digest


@dataclass(frozen=True, slots=True)
class RexUpdate:
    """One validator's own answer, carried on chain alongside every other's."""

    validator: str
    value: float
    round: int
    # What this validator read from each source, before taking their median.
    # Empty for a flag, which has nothing to reconcile.
    sources: tuple[tuple[str, float | None], ...] = ()

    @property
    def key(self) -> str:
        return authority_key(self.validator)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator": self.validator,
            "authority_key": self.key[:18] + "…",
            "value": self.value,
            "round": self.round,
            "sources": [{"source": name, "value": value} for name, value in self.sources],
        }


@dataclass(frozen=True, slots=True)
class Aggregation:
    """The aggregator's verdict, and enough of its working to check it."""

    topic: str
    reference: str
    field: str
    round: int
    agreement: Agreement
    value: float | None
    median: float | None
    spread: float | None        # max minus min, in the index's own unit
    dispersion: float | None    # spread as a share of the median
    reported: int
    expected: int
    updates: tuple[RexUpdate, ...]
    note: str

    @property
    def settles(self) -> bool:
        return self.agreement is Agreement.AGREED and self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "reference": self.reference,
            "field": self.field,
            "round": self.round,
            "agreement": self.agreement.value,
            "value": self.value,
            "median": self.median,
            "spread": self.spread,
            "dispersion": self.dispersion,
            "reported": self.reported,
            "expected": self.expected,
            "settles": self.settles,
            "note": self.note,
            "updates": [u.to_dict() for u in self.updates],
        }


@dataclass(slots=True)
class RexReport:
    """Every validator's update for one topic in one round, as stored on chain."""

    topic: str
    reference: str
    field: str
    round: int
    updates: list[RexUpdate] = field(default_factory=list)

    def add(self, update: RexUpdate) -> None:
        self.updates.append(update)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "reference": self.reference,
            "field": self.field,
            "round": self.round,
            "updates": [u.to_dict() for u in self.updates],
        }


class Aggregator:
    """Clause's own reconciliation rule, written down because Rialo's is not.

    The rule is deliberately dull. Dullness is the point: a buyer can be told in
    one sentence what has to happen for their policy to pay, and an auditor can
    recompute it from the reports stored on chain.
    """

    def __init__(
        self,
        *,
        validators: int = DEVNET_VALIDATORS,
        quorum_share: float = QUORUM_SHARE,
        dispersion_tolerance: float = DISPERSION_TOLERANCE,
    ) -> None:
        if not 0 < quorum_share <= 1:
            raise ValueError("quorum share must be a fraction above zero")
        if dispersion_tolerance < 0:
            raise ValueError("dispersion tolerance cannot be negative")
        self.validators = validators
        self.quorum_share = quorum_share
        self.dispersion_tolerance = dispersion_tolerance

    @property
    def quorum(self) -> int:
        """How many validators must report. Rounded up, and never below two."""
        needed = int(-(-self.validators * self.quorum_share // 1))
        return max(2, min(self.validators, needed))

    def describe(self) -> str:
        """The rule as a policy term, in the buyer's language."""
        return (
            f"At least {self.quorum} of {self.validators} validators must report "
            f"the reading, the settled figure is the median of what they report, "
            f"and if their answers differ by more than "
            f"{self.dispersion_tolerance * 100:g}% the reading is refused rather "
            f"than aggregated."
        )

    def aggregate(self, report: RexReport) -> Aggregation:
        """Reconcile one round of reports into a figure, or refuse to."""
        updates = tuple(report.updates)
        values = [u.value for u in updates]
        reported = len(values)

        def verdict(
            agreement: Agreement, value: float | None, note: str,
            median: float | None = None, spread: float | None = None,
            dispersion: float | None = None,
        ) -> Aggregation:
            return Aggregation(
                topic=report.topic, reference=report.reference,
                field=report.field, round=report.round,
                agreement=agreement, value=value, median=median, spread=spread,
                dispersion=dispersion, reported=reported, expected=self.validators,
                updates=updates, note=note,
            )

        if reported < self.quorum:
            return verdict(
                Agreement.NO_QUORUM, None,
                f"only {reported} of {self.validators} validators reported, "
                f"below the {self.quorum} this policy requires",
            )

        median = float(statistics.median(values))
        spread = max(values) - min(values)
        # A median at zero is a degenerate case for a ratio, so dispersion is
        # measured against the spread itself there rather than dividing by zero.
        dispersion = (spread / abs(median)) if median else (0.0 if spread == 0 else 1.0)

        if dispersion > self.dispersion_tolerance:
            return verdict(
                Agreement.DISPUTED, None,
                f"validators disagreed by {dispersion * 100:.1f}%, beyond the "
                f"{self.dispersion_tolerance * 100:g}% this policy tolerates",
                median=median, spread=spread, dispersion=dispersion,
            )

        return verdict(
            Agreement.AGREED, median,
            f"{reported} of {self.validators} validators reported within "
            f"{dispersion * 100:.2f}%, settled at the median",
            median=median, spread=spread, dispersion=dispersion,
        )


def topic_for(reference: str, field_name: str) -> str:
    """The topic a subscription listens on, derived from the source it reads.

    On Rialo a topic is an account address. Deriving it from the source reference
    and the field means two policies reading the same figure listen to the same
    topic, which is what makes one reading settle a whole book at once.
    """
    digest = hashlib.blake2b(
        f"{reference}#{field_name}".encode(), digest_size=16
    ).hexdigest()
    return "topic:" + digest


def shorten_topic(topic: str) -> str:
    body = topic.split(":", 1)[-1]
    return body[:8] + "…" + body[-4:] if len(body) > 14 else body
