"""What a peril is, and how a payout is shaped.

A parametric policy never asks what you lost. It measures an agreed index, and
pays an agreed amount when that index crosses an agreed level. Three pieces
define one:

  the index        what is measured, from which source, at what resolution
  the structure    how much is paid at each level of the index
  the model        the probability of the index reaching each level

The first two are contractual and go onchain. The third is the insurer's own
view and is what the premium is derived from.

Basis risk is the gap between the index and the actual loss, and it is the
honest weakness of every parametric product. A policy can pay when nothing was
lost, and fail to pay when everything was. Each peril here states its own basis
risk in plain words, because a protocol that hides it is selling something it
has not described.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Sequence

from ..mathx import MathError


class Direction(str, Enum):
    """Which way the index has to move for the policy to respond."""

    ABOVE = "above"  # pays as the index rises: delay minutes, magnitude, heat
    BELOW = "below"  # pays as the index falls: rainfall in a drought cover


class Shape(str, Enum):
    """How payout relates to the index between breakpoints."""

    STEP = "step"    # the whole band is paid the moment the level is reached
    RAMP = "ramp"    # payout rises proportionally across the band


@dataclass(frozen=True, slots=True)
class Breakpoint:
    """One level of the index and the share of the limit paid at it."""

    level: float
    share: float  # fraction of the limit, 0 to 1

    def __post_init__(self) -> None:
        if not 0.0 <= self.share <= 1.0:
            raise ValueError(f"share must lie in [0, 1], got {self.share}")


@dataclass(frozen=True, slots=True)
class PayoutCurve:
    """The contractual payout, as a function of the index.

    Any monotone payout can be decomposed into layers, and the expected payout
    is then the integral of the layer widths against the probability of
    reaching them. That decomposition is how reinsurers price a layer, and it
    is exact for a step structure rather than an approximation:

        E[payout] = sum over bands of  (band width) x P(index reaches band)

    For a ramp the same identity holds in the limit, and is evaluated by
    integrating the exceedance probability across the band.
    """

    breakpoints: tuple[Breakpoint, ...]
    shape: Shape = Shape.STEP
    direction: Direction = Direction.ABOVE

    def __post_init__(self) -> None:
        if len(self.breakpoints) < 1:
            raise ValueError("a payout curve needs at least one breakpoint")

        levels = [point.level for point in self.breakpoints]
        shares = [point.share for point in self.breakpoints]

        ordered = levels == sorted(levels) if self.direction is Direction.ABOVE \
            else levels == sorted(levels, reverse=True)
        if not ordered:
            raise ValueError(
                "breakpoints must run in the direction the policy responds"
            )
        if shares != sorted(shares):
            raise ValueError("payout shares must not decrease across breakpoints")

    @property
    def attachment(self) -> float:
        """The index level at which the policy first pays anything."""
        return self.breakpoints[0].level

    @property
    def exhaustion(self) -> float:
        """The index level at which the full limit is paid."""
        return self.breakpoints[-1].level

    @property
    def maximum_share(self) -> float:
        return self.breakpoints[-1].share

    def payout_share(self, index_value: float) -> float:
        """The fraction of the limit due at an observed index value."""
        if self.direction is Direction.ABOVE:
            reached = [p for p in self.breakpoints if index_value >= p.level]
        else:
            reached = [p for p in self.breakpoints if index_value <= p.level]

        if not reached:
            return 0.0
        if self.shape is Shape.STEP:
            return reached[-1].share

        # Ramp: interpolate between the last reached point and the next one.
        last = reached[-1]
        remaining = [p for p in self.breakpoints if p not in reached]
        if not remaining:
            return last.share
        nxt = remaining[0]
        span = nxt.level - last.level
        if span == 0:
            return nxt.share
        progress = (index_value - last.level) / span
        progress = max(0.0, min(1.0, progress))
        return last.share + (nxt.share - last.share) * progress

    def payout(self, index_value: float, limit: float) -> float:
        """The amount due at an observed index value."""
        if limit < 0:
            raise ValueError(f"limit must not be negative, got {limit}")
        return limit * self.payout_share(index_value)

    def expected_share(self, exceedance: Callable[[float], float]) -> float:
        """Expected payout as a fraction of the limit.

        ``exceedance(level)`` gives the probability the index reaches that
        level in the policy's direction. Nothing else about the distribution is
        needed, which is what lets one curve price three unrelated perils.
        """
        if self.shape is Shape.STEP:
            total = 0.0
            previous_share = 0.0
            for point in self.breakpoints:
                width = point.share - previous_share
                if width <= 0:
                    continue
                probability = _checked_probability(exceedance(point.level))
                total += width * probability
                previous_share = point.share
            return total

        # Ramp: integrate the exceedance curve across each band. The band is
        # split finely enough that the residual error is far below the rounding
        # applied to a premium.
        steps_per_band = 64
        total = 0.0
        previous_share = 0.0
        previous_level = self.breakpoints[0].level

        for point in self.breakpoints:
            width = point.share - previous_share
            span = point.level - previous_level
            if width <= 0 or span == 0:
                previous_share, previous_level = point.share, point.level
                continue

            accumulated = 0.0
            for step in range(steps_per_band):
                fraction = (step + 0.5) / steps_per_band
                level = previous_level + span * fraction
                accumulated += _checked_probability(exceedance(level))
            total += width * accumulated / steps_per_band

            previous_share, previous_level = point.share, point.level

        # Below the first breakpoint nothing is paid, and at or beyond the last
        # the full share is due, which the loop above has already counted.
        return total

    def describe(self, unit: str) -> list[str]:
        """The structure in words, for the policy document and the interface."""
        lines: list[str] = []
        comparison = "at or above" if self.direction is Direction.ABOVE else "at or below"
        for index, point in enumerate(self.breakpoints):
            percentage = point.share * 100
            if self.shape is Shape.RAMP and index > 0:
                previous = self.breakpoints[index - 1]
                lines.append(
                    f"between {previous.level:g} and {point.level:g} {unit}, "
                    f"rising from {previous.share * 100:g}% to {percentage:g}% of the limit"
                )
            else:
                lines.append(
                    f"{comparison} {point.level:g} {unit}, pays {percentage:g}% of the limit"
                )
        return lines


def _checked_probability(value: float) -> float:
    if not 0.0 <= value <= 1.0:
        raise MathError(f"exceedance must lie in [0, 1], got {value}")
    return value


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DataSource:
    """Where the index is read from, and what happens when it is not there.

    The last two fields are the ones most parametric designs leave out. An
    endpoint that stops publishing leaves a policy armed forever, holding the
    buyer's premium against an event that can no longer be observed. Naming a
    settlement deadline and what happens at it is part of the product, not an
    operational detail.
    """

    reference: str            # the endpoint the chain reads, through Rialo Edge
    field: str                # the field on the response carrying the index
    unit: str
    publisher: str            # who is attesting the number
    resolution: str           # how often it updates, in words
    settlement_deadline_days: int   # how long after expiry the data may arrive
    on_missing_data: str      # what the policy does if it never does

    @property
    def key(self) -> str:
        """The dependency key a validator would index a reading under."""
        return f"edge:{self.reference}"


# ---------------------------------------------------------------------------
# Perils
# ---------------------------------------------------------------------------


class Peril(ABC):
    """One insurable index, its data contract and its probability model."""

    key: str
    name: str
    index_name: str
    unit: str
    basis_risk: str
    basis_risk_level: str  # low, moderate, high

    #: The countries this peril's model can actually price, as ISO codes, or
    #: None when the index is not tied to a territory. A licence in a country is
    #: necessary and not sufficient: a carrier licensed in Japan changes nothing
    #: about a hazard model that was only ever fitted to Anatolian faults, and a
    #: map that called Japan open on the strength of the licence alone would be
    #: promising cover the protocol cannot price.
    territory: frozenset[str] | None = None

    def risk_country(self, subject: dict[str, Any]) -> str | None:
        """Where the insured thing is, when that is what a licence must cover.

        For property the answer is the property: a flat in Istanbul needs paper
        licensed in Türkiye whoever owns it and wherever they live. For cover
        that follows a person, a flight, there is no such place and the buyer's
        own country governs, so this returns None.
        """
        return None

    @abstractmethod
    def data_source(self, subject: dict[str, Any]) -> DataSource:
        """Where the index for a particular insured subject is read."""

    def curve_for(self, subject: dict[str, Any]) -> PayoutCurve:
        """The standard structure for this particular subject. Most perils have
        one; earthquake has one per index (magnitude, or shaking at the address)."""
        return self.default_curve()

    def unit_for(self, subject: dict[str, Any]) -> str:
        return self.unit

    def title_for(self, subject: dict[str, Any]) -> str:
        """The name of the cover for this subject, as the buyer sees it."""
        return self.name

    @abstractmethod
    def default_curve(self) -> PayoutCurve:
        """The standard structure offered for this peril."""

    @abstractmethod
    def exceedance(
        self, subject: dict[str, Any], term_days: float
    ) -> Callable[[float], float]:
        """Probability the index reaches a given level within the term.

        This is the insurer's view of the risk, and everything about the price
        follows from it. It is separate from the contract on purpose: the
        structure is what the buyer is owed, the model is only what the insurer
        believes about it.
        """

    @abstractmethod
    def predicate(
        self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str
    ) -> str:
        """The onchain condition that settles this policy by itself."""

    @abstractmethod
    def validate_subject(self, subject: dict[str, Any]) -> dict[str, Any]:
        """Check and normalise what is being insured."""

    # -- shared helpers ---------------------------------------------------

    def trigger_probability(
        self, subject: dict[str, Any], curve: PayoutCurve, term_days: float
    ) -> float:
        """Probability the policy pays anything at all."""
        return self.exceedance(subject, term_days)(curve.attachment)

    def expected_share(
        self, subject: dict[str, Any], curve: PayoutCurve, term_days: float
    ) -> float:
        return curve.expected_share(self.exceedance(subject, term_days))

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "index": self.index_name,
            "unit": self.unit,
            "basis_risk": self.basis_risk,
            "basis_risk_level": self.basis_risk_level,
        }


def curve_from_spec(
    spec: Sequence[tuple[float, float]],
    *,
    shape: Shape = Shape.STEP,
    direction: Direction = Direction.ABOVE,
) -> PayoutCurve:
    """Build a curve from (level, share) pairs."""
    return PayoutCurve(
        breakpoints=tuple(Breakpoint(level, share) for level, share in spec),
        shape=shape,
        direction=direction,
    )
