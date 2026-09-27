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
from zoneinfo import ZoneInfo

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
#: How long before the flight leaves the cover has to be bought. A day is past
#: the point where a delay is the airline's own knowledge rather than a guess:
#: the aircraft that will fly the route is assigned, the crew is rostered, and
#: a schedule already slipping is visible on any flight tracker. Cover bought
#: inside that day is bought on information the price does not have.
BOOK_AHEAD_HOURS = 24

#: How a route nobody has published figures for is priced. Distance is the
#: only thing about an unknown flight that is known, and it is the thing that
#: matters: a longer sector has more places to lose time and fewer chances to
#: make it up, and its aircraft has usually flown that day already. The bands
#: are the published industry averages by sector length, rounded. Indicative,
#: like every other figure of this kind here, and replaced by the carrier's own
#: record the moment there is one.
DISTANCE_BANDS: tuple[tuple[float, float, float, float], ...] = (
    # up to km, cancellation rate, share arriving late, median late minutes
    (1_500.0, 0.016, 0.22, 33.0),
    (4_000.0, 0.013, 0.25, 40.0),
    (8_000.0, 0.010, 0.28, 50.0),
    (float("inf"), 0.008, 0.30, 58.0),
)

ROUTES: dict[str, RouteStatistics] = {
    "TK-IST-LHR": RouteStatistics("TK", "IST", "LHR", 0.012, 0.243, 41.0),
    "TK-IST-JFK": RouteStatistics("TK", "IST", "JFK", 0.009, 0.281, 52.0),
    "TK-IST-AMS": RouteStatistics("TK", "IST", "AMS", 0.014, 0.262, 44.0),
    "PC-SAW-ESB": RouteStatistics("PC", "SAW", "ESB", 0.018, 0.197, 33.0),
    "LH-FRA-IST": RouteStatistics("LH", "FRA", "IST", 0.011, 0.221, 38.0),
    "BA-LHR-IST": RouteStatistics("BA", "LHR", "IST", 0.016, 0.254, 46.0),
}


def airports_of(subject: dict[str, Any]) -> tuple[str, str]:
    """Where a flight leaves from and lands, whichever shape the record is in.

    Cover written before the airport catalogue existed named one of six routes
    instead of two codes. validate_subject reads that back into the two
    airports -- but it runs when a policy is written, and a policy already in
    the book was written before it. Restored from disk, those records still
    carry `route` and no `origin`, so every line that reached for
    subject["origin"] raised KeyError on them: the whole of /api/policies came
    back as a five hundred because one old flight policy was in the book.

    The migration belonged to the reading and not only to the door, which is
    what this is. Anything it cannot resolve comes back empty rather than
    raising, because a record that cannot be described is still a record, and
    failing to name a route must not take a page down.
    """
    origin = str(subject.get("origin", "") or "").upper().strip()
    destination = str(subject.get("destination", "") or "").upper().strip()
    if origin and destination:
        return origin, destination
    route = str(subject.get("route", "") or "").upper().strip()
    known = ROUTES.get(route)
    if known is not None:
        return known.origin, known.destination
    # A bare "IST-LHR", without the carrier the catalogue keys on.
    for stats in ROUTES.values():
        if stats.route == route:
            return stats.origin, stats.destination
    parts = route.split("-")
    if len(parts) == 2 and all(len(part) == 3 for part in parts):
        return parts[0], parts[1]
    return origin, destination


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

    # Flight cover names one flight, so the waiting period every other peril
    # uses would push the start of the cover past the flight it is meant to
    # insure. The same job is done by refusing the sale instead: the cover has
    # to be bought before the airline knows the aircraft is late, and an
    # airline knows that in the last hours, not two days out.
    waiting_days = 0.0


    def validate_subject(self, subject: dict[str, Any]) -> dict[str, Any]:
        from .airports import find

        # Where it leaves from and where it lands, as IATA codes. A policy
        # written before the catalogue existed names one of six routes instead;
        # it is read back into the two airports so that cover already sold
        # still describes and settles the same way.
        origin = str(subject.get("origin", "")).upper().strip()
        destination = str(subject.get("destination", "")).upper().strip()
        route = str(subject.get("route", "")).upper().strip()
        if not (origin and destination) and route in ROUTES:
            known = ROUTES[route]
            origin, destination = known.origin, known.destination
        if find(origin) is None:
            raise ValueError(
                f"{origin or 'the departure airport'} is not an airport code; "
                f"a code is three letters, like IST"
            )
        if find(destination) is None:
            raise ValueError(
                f"{destination or 'the arrival airport'} is not an airport code; "
                f"a code is three letters, like LHR"
            )
        if origin == destination:
            raise ValueError("a flight leaves from one airport and lands at another")
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
        # The scheduled departure in the airport's own clock, which is how a
        # ticket writes it. A subject from before this field was asked for
        # carries no time; midnight is the reading that can only refuse a sale
        # and never allow one it should have refused.
        clock = str(subject.get("departure_time", "")).strip()
        written = re.fullmatch(r"(\d{1,2}):(\d{2})", clock) if clock else None
        if clock and written is None:
            raise ValueError(
                "the departure time is written as HH:MM on a 24 hour clock, in "
                "the time at the airport it leaves from"
            )
        hour, minute = (int(written[1]), int(written[2])) if written else (0, 0)
        if hour > 23 or minute > 59:
            raise ValueError(
                "the departure time is written as HH:MM on a 24 hour clock, in "
                "the time at the airport it leaves from"
            )
        at = dt.time(hour, minute)
        return {
            "origin": origin,
            "destination": destination,
            "flight_number": flight_number,
            "departure_date": departure,
            "departure_time": at.strftime("%H:%M"),
        }

    def departs_at(self, subject: dict[str, Any]) -> float:
        """The scheduled departure as an instant.

        A flight leaves at a time written on a ticket in the clock of the
        airport it leaves from. Turning that into an instant is what makes the
        twenty-four hour rule a real twenty-four hours rather than a number of
        calendar days that means something different in every timezone.
        """
        from .airports import find

        airport = find(airports_of(subject)[0])
        zone = ZoneInfo(airport["tz"] if airport else "UTC")
        day = dt.date.fromisoformat(str(subject["departure_date"]))
        clock = dt.time.fromisoformat(str(subject.get("departure_time") or "00:00"))
        return dt.datetime.combine(day, clock, zone).timestamp()

    def refuse_to_write(self, subject: dict[str, Any], *, now: float | None = None) -> str:
        """Checked at the moment of writing, not only when the flight was
        typed: a price taken one evening can be paid for the next morning."""
        import time as _time
        try:
            leaves = self.departs_at(subject)
        except (KeyError, ValueError):
            return ""
        hours = (leaves - (now if now is not None else _time.time())) / 3600.0
        if hours >= BOOK_AHEAD_HOURS:
            return ""
        if hours <= 0:
            return "this flight has already left, so there is nothing left to insure"
        return (
            f"cover for a flight has to be bought {BOOK_AHEAD_HOURS} hours before "
            f"it leaves, and this one leaves in {hours:.0f} hours"
        )

    def statistics(self, subject: dict[str, Any]) -> RouteStatistics:
        """What this flight's route is expected to do.

        The published record where there is one. Where there is not — which is
        almost every flight, because published on-time performance exists for a
        handful of routes and people fly all of them — the sector's length
        stands in for it. The quote says which of the two it used, because a
        buyer should know whether the price is about their route or about
        routes of that length.
        """
        known = ROUTES.get(self.route_key(subject))
        if known is not None:
            return known
        carrier = str(subject.get("flight_number", ""))[:2].upper()
        origin, destination = airports_of(subject)
        km = self.sector_km(subject)
        for limit, cancelled, late, median in DISTANCE_BANDS:
            if km <= limit:
                return RouteStatistics(carrier, origin, destination, cancelled, late, median)
        raise ValueError("no band for this distance")  # unreachable: the last is infinite

    def route_key(self, subject: dict[str, Any]) -> str:
        carrier = str(subject.get("flight_number", ""))[:2].upper()
        origin, destination = airports_of(subject)
        return f"{carrier}-{origin}-{destination}"

    def published(self, subject: dict[str, Any]) -> bool:
        """Whether this route's own record was used, or the distance band."""
        return self.route_key(subject) in ROUTES

    def sector_km(self, subject: dict[str, Any]) -> float:
        from .airports import find, great_circle_km

        left, landed = airports_of(subject)
        origin, destination = find(left), find(landed)
        if origin is None or destination is None:
            return 2_000.0
        return great_circle_km(
            (origin["latitude"], origin["longitude"]),
            (destination["latitude"], destination["longitude"]),
        )

    def data_source(self, subject: dict[str, Any], *,
                    simulated: bool = False) -> DataSource:
        # No feed reads this peril yet, so both references are the one that
        # measures nothing. See oracle/feed.py for the ones that do.
        del simulated
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
        self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str, *,
        simulated: bool = False,
    ) -> str:
        source = self.data_source(subject, simulated=simulated)
        return (
            f'edge("{source.reference}").{source.field} >= {curve.attachment:g}'
        )

    def describe_subject(self, subject: dict[str, Any]) -> str:
        origin, destination = airports_of(subject)
        flight = subject.get("flight_number") or "?"
        when = subject.get("departure_date") or "?"
        return (
            f"{flight} on {origin or '?'} to {destination or '?'}, {when}"
            + (f" at {subject['departure_time']}" if subject.get("departure_time") else "")
        )

    def title_for(self, subject: dict[str, Any]) -> str:
        return self.name
