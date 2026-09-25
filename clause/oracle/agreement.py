"""What to do when two official sources say different things.

They do. For the Pazarcik earthquake of 6 February 2023, USGS says magnitude
7.8 and AFAD, Turkiye's own agency, says 7.7. For Elbistan that same morning,
USGS and EMSC say 7.5 and AFAD says 7.6. These are the two largest earthquakes
in modern Turkish history, measured by three agencies who all do this for a
living, and they are 0.1 apart. A policy written at 7.6 pays on AFAD's reading
and does not pay on USGS's.

There is no version of this problem that goes away by picking a favourite
source and never looking at the others. A single source is a single point of
failure and a single thing to tamper with, which is what happened at Paris
Charles de Gaulle in April 2026 when one station's temperature readings jumped
four degrees on two evenings and settled money on a prediction market before
anyone noticed.

So the rule is: ask everyone who measures this, take the primary's number,
record what the others said, and if they are further apart than the peril can
tolerate, do not settle -- hold, and say why. Holding is not a refusal. It is
the honest state of a fact that is genuinely in dispute, and the alternative is
to pick a side silently and hope nobody checks.

The tolerance is per peril because the quantities are not alike. A tenth of a
magnitude is a third of the energy and it straddles a payment step, so
earthquake is tight. Rainfall from two grids twenty kilometres apart can differ
by a fifth on a convective day without either being wrong, so rain is loose.
A flight either landed at a time or it did not, so flight is tighter still.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .observation import Observation, Reading

#: How far apart two sources may be before the protocol stops rather than
#: choosing. In the unit the index is read in.
TOLERANCE: dict[str, float] = {
    "earthquake": 0.2,        # magnitude: 0.1 is routine between agencies, 0.3 is not
    "storm": 8.0,             # km/h of daily maximum wind
    "vehicle_flood": 12.0,    # mm of daily rainfall
    "drought": 0.05,          # share of the season's normal
    "flight_delay": 10.0,     # minutes
}
#: The peril's own unit, so a reading can say what it is without asking the peril.
UNIT: dict[str, str] = {
    "earthquake": "magnitude", "storm": "km/h", "vehicle_flood": "mm",
    "drought": "of normal", "flight_delay": "minutes",
}


@dataclass(frozen=True, slots=True)
class Agreement:
    """Whether the sources are close enough to settle on."""

    agreed: bool
    spread: float
    tolerance: float
    why: str

    def to_dict(self) -> dict[str, Any]:
        return {"agreed": self.agreed, "spread": round(self.spread, 4),
                "tolerance": self.tolerance, "why": self.why}


def agree(observations: Iterable[Observation], *, peril: str,
          tolerance: float | None = None) -> Agreement:
    """How far apart the sources are, and whether that is too far."""
    seen = list(observations)
    limit = TOLERANCE.get(peril, 0.0) if tolerance is None else tolerance
    if not seen:
        return Agreement(False, 0.0, limit, "no source answered")
    if len(seen) == 1:
        return Agreement(True, 0.0, limit,
                         f"only {seen[0].source} measures this here, so there is "
                         f"nothing to check it against")
    values = [o.value for o in seen]
    spread = max(values) - min(values)
    if spread <= limit:
        return Agreement(True, spread, limit,
                         f"{len(seen)} sources within {spread:g} of each other")
    apart = ", ".join(f"{o.source} {o.value:g}" for o in sorted(seen, key=lambda o: o.value))
    return Agreement(False, spread, limit,
                     f"the sources do not agree: {apart}. That is {spread:g} apart "
                     f"and this cover settles only within {limit:g}")


def read_from(observations: Iterable[Observation], *, peril: str,
              primary: str, tolerance: float | None = None) -> Reading:
    """The one number a ladder can be applied to, and what it rests on.

    The primary's value is the value. The others are not averaged into it --
    an average of two official measurements is a third number that no agency
    published and nobody can be pointed at. They are there to say whether the
    primary can be believed.
    """
    seen = tuple(observations)
    verdict = agree(seen, peril=peril, tolerance=tolerance)
    unit = UNIT.get(peril, seen[0].unit if seen else "")
    chosen = next((o for o in seen if o.source == primary), None)
    if chosen is None:
        chosen = next(iter(seen), None)
    if chosen is None:
        return Reading(0.0, unit, 0.0, False, "no source answered", (), 0.0, primary)
    return Reading(value=chosen.value, unit=chosen.unit or unit,
                   measured_at=chosen.measured_at,
                   settles=verdict.agreed, why=verdict.why,
                   observations=seen, spread=verdict.spread, primary=chosen.source)
