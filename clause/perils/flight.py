"""Flight delay and cancellation.

The index is the arrival delay in minutes against the scheduled time, with a
cancellation treated as the maximum. It is read once, after the flight has
resolved, from a flight status endpoint the validators attest.

Model. On time performance statistics give, for a route and carrier, the share
of flights arriving within fifteen minutes and the share cancelled. Conditional
on being late, delay length is heavy tailed and is conventionally fitted as
lognormal, which is what is used here. Two published numbers per route are
therefore enough to price any structure written on this index:

    p_cancel        share of departures cancelled
    p_late          share arriving more than fifteen minutes late
    median_delay    median delay among late arrivals

The lognormal is pinned by the median and a dispersion that widens with the
median, since routes with longer typical delays also have longer tails.
"""

from __future__ import annotations

import datetime as dt
import re

import math
from dataclasses import dataclass
from typing import Any, Callable

from ..mathx import normal_cdf
from .base import DataSource, Direction, Peril, PayoutCurve, Shape, curve_from_spec

# A cancellation is settled at this index value, above any survivable delay, so
# one curve covers both delay and cancellation without a second contract.
CANCELLATION_MINUTES = 1440.0

# Dispersion of the lognormal fitted to late arrivals. Calibrated so that the
# ratio between the ninetieth percentile and the median delay sits near three,
# which is what published arrival delay distributions show.
_LOG_SIGMA = 0.86


@dataclass(frozen=True, slots=True)
class RouteStatistics:
    """Published performance for one carrier on one route."""

    carrier: str
    origin: str
    destination: str
    cancellation_rate: float   # share of departures cancelled
    late_rate: float           # share arriving more than fifteen minutes late
    median_late_minutes: float  # median delay among those late arrivals

    def __post_init__(self) -> None:
        for name, value in (
            ("cancellation_rate", self.cancellation_rate),
            ("late_rate", self.late_rate),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1], got {value}")
        if self.median_late_minutes <= 0:
            raise ValueError("median delay must be positive")

    @property
    def route(self) -> str:
        return f"{self.origin}-{self.destination}"


# Published on time performance, rounded, for routes the demo offers. Real
# figures for a live deployment come from the carrier or the regulator; these
# are the shape of that input, not a claim about any particular airline today.
ROUTES: dict[str, RouteStatistics] = {
    "TK-IST-LHR": RouteStatistics("TK", "IST", "LHR", 0.012, 0.243, 41.0),
    "TK-IST-JFK": RouteStatistics("TK", "IST", "JFK", 0.009, 0.281, 52.0),
    "TK-IST-AMS": RouteStatistics("TK", "IST", "AMS", 0.014, 0.262, 44.0),
    "PC-SAW-ESB": RouteStatistics("PC", "SAW", "ESB", 0.018, 0.197, 33.0),
    "LH-FRA-IST": RouteStatistics("LH", "FRA", "IST", 0.011, 0.221, 38.0),
    "BA-LHR-IST": RouteStatistics("BA", "LHR", "IST", 0.016, 0.254, 46.0),
}


class FlightDelay(Peril):
    key = "flight_delay"
    name = "Flight delay and cancellation"
    index_name = "arrival delay against schedule"
    unit = "minutes"
    basis_risk = (
        "Low. The index is the delay itself, so the policy pays when the "
        "insured event happens. What it cannot know is what the delay cost "
        "you: a missed connection and a missed afternoon are the same number "
        "of minutes and the same payout."
    )
    basis_risk_level = "low"

    def validate_subject(self, subject: dict[str, Any]) -> dict[str, Any]:
        route = str(subject.get("route", "")).upper().strip()
        if route not in ROUTES:
            raise ValueError(
                f"unknown route {route!r}; offered routes are "
                f"{', '.join(sorted(ROUTES))}"
            )
        flight_number = str(subject.get("flight_number", "")).upper().strip().replace(" ", "")
        if not re.fullmatch(r"[A-Z0-9]{2}[0-9]{1,4}[A-Z]?", flight_number):
            raise ValueError("a flight number is an airline code and up to four digits, like TK1979")
        departure = str(subject.get("departure_date", "")).strip()
        try:
            when = dt.date.fromisoformat(departure)
        except ValueError as error:
            raise ValueError("the departure date is written as YYYY-MM-DD") from error
        today = dt.date.today()
        if when < today or when > today + dt.timedelta(days=365):
            raise ValueError("the departure date is between today and a year from now")
        return {
            "route": route,
            "flight_number": flight_number,
            "departure_date": departure,
        }

    def statistics(self, subject: dict[str, Any]) -> RouteStatistics:
        return ROUTES[subject["route"]]

    def data_source(self, subject: dict[str, Any]) -> DataSource:
        flight = subject["flight_number"]
        date = subject["departure_date"]
        return DataSource(
            reference=f"api.flightstatus.example/v1/{flight}/{date}",
            field="arrival_delay_minutes",
            unit=self.unit,
            publisher="flight status aggregator, attested by validators",
            resolution="final, published once the flight has landed or been cancelled",
            settlement_deadline_days=3,
            on_missing_data=(
                "If no final status is attested within three days of scheduled "
                "arrival, the policy expires and the premium is returned in full."
            ),
        )

    def default_curve(self) -> PayoutCurve:
        """The market standard tiered delay cover."""
        return curve_from_spec(
            [
                (120.0, 0.30),   # two hours
                (240.0, 0.70),   # four hours
                (CANCELLATION_MINUTES, 1.00),  # cancelled
            ],
            shape=Shape.STEP,
            direction=Direction.ABOVE,
        )

    def exceedance(
        self, subject: dict[str, Any], term_days: float
    ) -> Callable[[float], float]:
        """Probability the arrival delay reaches a given number of minutes.

        A single flight either happens or does not, so the term length does not
        enter: the exposure is one event, not a rate over time.
        """
        del term_days
        stats = self.statistics(subject)

        # Conditional on a late arrival, delay is lognormal with the observed
        # median. The median of a lognormal is exp(mu), so mu falls out directly.
        mu = math.log(stats.median_late_minutes)

        def probability(level: float) -> float:
            if level <= 0:
                return 1.0

            # A cancellation settles at the top of the index, so any level at
            # or below the cancellation mark is reached by every cancelled
            # flight, and levels above it by none.
            cancelled = stats.cancellation_rate if level <= CANCELLATION_MINUTES else 0.0
            if level >= CANCELLATION_MINUTES:
                return cancelled

            # Among flights that operate, the chance of being late at all, then
            # the chance the delay exceeds this level given it was late.
            operated = 1.0 - stats.cancellation_rate
            beyond_given_late = 1.0 - normal_cdf(math.log(level), mu, _LOG_SIGMA)
            return cancelled + operated * stats.late_rate * beyond_given_late

        return probability

    def predicate(
        self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str
    ) -> str:
        source = self.data_source(subject)
        return (
            f'edge("{source.reference}").{source.field} >= {curve.attachment:g}'
        )

    def describe_subject(self, subject: dict[str, Any]) -> str:
        stats = self.statistics(subject)
        return (
            f"{subject['flight_number']} on {stats.origin} to {stats.destination}, "
            f"{subject['departure_date']}"
        )
