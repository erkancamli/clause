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
# Where a policy says it is
# ---------------------------------------------------------------------------
#
# Two decimal places, about 1.1 km of latitude. A policy's coordinate is
# public: it is in the book anyone can read, and it is in the oracle reference
# that makes a reading repeatable by somebody who does not work here, which is
# why it cannot be coarsened in the public view alone. So it is coarsened where
# the policy is written, and then the record, the reference, the predicate and
# the page all carry the same point.
#
# It was four places, about eleven metres, which for a home is the front door.
# Nothing is lost by moving to two: the data this protocol settles on is
# coarser than that everywhere. USGS ShakeMap is published on a grid of about
# a kilometre, ERA5 on about twenty-five and ERA5-Land on about ten, and a
# magnitude policy is a circle fifty or a hundred kilometres across. The
# measurement point moves by up to about 800 m and lands in the same cell of
# every source.
PLACE_PLACES = 2


def insured_point(latitude: float, longitude: float) -> tuple[float, float]:
    """The coordinate a policy is written on, as everything will read it."""
    return round(float(latitude), PLACE_PLACES), round(float(longitude), PLACE_PLACES)


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

    #: Days between buying the cover and the cover starting. The price is the
    #: probability of an event in an ordinary term, worked out for someone who
    #: does not know whether one is coming. A forecast breaks that: a storm is
    #: named on the news a week before it arrives, an earthquake is already
    #: shaking while a page is loading, and cover bought in those hours is
    #: bought by someone who does know. The premium they would pay is the
    #: premium of a person who does not, so the pool loses the difference on
    #: every such policy and the people who bought early pay for it. The wait
    #: is set past the point where the event is public knowledge, per peril,
    #: and is stated on the policy. It does not shorten the cover: the term
    #: runs its full length from the day it starts.
    waiting_days: float = 0.0

    def starts_in_days(self, subject: dict[str, Any], *, now: float | None = None) -> float:
        """How long after the sale this particular cover starts.

        The waiting period for most perils, and for a seasonal index the time
        until the season itself opens, which is not a fixed number of days.
        """
        return self.waiting_days

    def refuse_to_write(self, subject: dict[str, Any], *, now: float | None = None) -> str:
        """Why this cover must not be written right now, or "" if it may be.

        For most perils the waiting period above is the whole answer. A few
        cannot use it: flight cover names the flight it insures, so a wait
        would leave the insured flight outside the cover rather than inside
        it. Those perils refuse the sale instead, here.
        """
        return ""

    def risk_country(self, subject: dict[str, Any]) -> str | None:
        """Where the insured thing is, when that is what a licence must cover.

        For property the answer is the property: a flat in Istanbul needs paper
        licensed in Türkiye whoever owns it and wherever they live. For cover
        that follows a person, a flight, there is no such place and the buyer's
        own country governs, so this returns None.
        """
        return None

    @abstractmethod
    def data_source(self, subject: dict[str, Any], *,
                    simulated: bool = False) -> DataSource:
        """Where the index for a particular insured subject is read.

        ``simulated`` asks for the reference the demonstration book writes
        against: a domain reserved for examples, which can never resolve,
        because a figure this protocol produced itself must not be addressed
        as though an agency published it. The default is the measured one, so
        that a path which forgets to choose ends up asking the agency rather
        than quietly inventing the number.

        A peril whose feed has not been built yet returns the same reference
        either way, and says so where it builds it. That is not a measured
        source pretending to be one; it is a peril that cannot yet be sold
        against anything real.
        """

    def curve_for(self, subject: dict[str, Any]) -> PayoutCurve:
        """The standard structure for this particular subject. Most perils have
        one; earthquake has one per index (magnitude, or shaking at the address)."""
        return self.default_curve()

    def unit_for(self, subject: dict[str, Any]) -> str:
        return self.unit

    def structure_unit(self) -> str:
        """The unit the standard structure is written in, with no subject yet.

        The catalogue describes a peril before anybody has chosen a station or
        an address, so there is nothing to convert drought's shares of normal
        into. Naming them "mm" there was the same mistake in a quieter place.
        """
        return self.unit

    def reading_curve(self, subject: dict[str, Any], curve: PayoutCurve) -> PayoutCurve:
        """The structure in the units the index is actually read in.

        For every peril but one this is the curve itself. Drought's structure
        is written in shares of the station's normal season, because one
        structure then reads the same at every station, and it has to be
        converted to millimetres before it can be shown to anybody or settled
        on. That conversion was done in the settlement path and nowhere else,
        so the contract a farmer signed said "at or below 0.8 mm, pays 0% of
        the limit" where it meant 94 mm. It is here now, so that everything
        which describes a structure and the thing that settles it read the
        same number.
        """
        return curve

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
        self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str, *,
        simulated: bool = False,
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
            "waiting_days": self.waiting_days,
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
