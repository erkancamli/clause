"""A vehicle, against flood from extreme rainfall where it is kept.

What it is, and what it is not
------------------------------
This pays when the rain that falls in one day where the car is kept is extreme
for that place: heavier than it gets, on average, once in ten, twenty five or
fifty years. Cars are written off by flash floods in exactly those days, and a
payout on the day, without an assessor, is what an owner needs to get moving.

It is not motor insurance. It does not cover accidents, theft, hail, fire or
damage of any other kind, and it pays on the rain, not on the car: a car kept
in a garage on a hill is paid on the same day as one parked in a dip, and a
car flooded by a burst main on a dry day is not paid at all. That basis risk
is stated before anyone pays. Hail would be the natural companion; no hail
record that is free to use and reliable enough to settle on exists for
Türkiye yet, so it is not offered.

The index
---------
The largest daily precipitation during the term, from NASA POWER (the MERRA-2
reanalysis, PRECTOTCORR) at the provincial centre nearest the car, read also
from the national meteorological service and ERA5 by each validator. The
thresholds are that place's own 1 in 10, 1 in 25 and 1 in 50 year levels, so a
cover in Rize and one in Konya each pay on what is extreme where they are.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from .base import (DataSource, Direction, PayoutCurve, Peril, Shape,
                   curve_from_spec, insured_point)
from . import daily

MODEL = Path(__file__).resolve().parents[1] / "hazard" / "models" / "rain_TR.json"
MAX_DISTANCE_KM = daily.MAX_DISTANCE_KM
LEVELS = ((10, 0.25), (25, 0.60), (50, 1.00))


def model(code: str = "TR") -> dict[str, Any]:
    """One country's rainfall model, or an empty one where it was never built."""
    have = daily.models("rain").get(code.upper())
    if have is None:
        return {"places": [], "validation": {"passed": False, "failed": ["not built"]}}
    return have


def nearest(latitude: float, longitude: float) -> tuple[dict[str, Any] | None, float]:
    """The nearest fitted place in any country this cover is written in.

    Every country with a model of its own is searched, and only the ones whose
    model passed its own backtest, which is why the answer carries the country
    it came from: the licence, the law and the model card all follow it.
    """
    return daily.nearest("rain", round(latitude, 4), round(longitude, 4))


def level_mm(place: dict[str, Any], years: float) -> float:
    g = place["gumbel"]
    return g["mu"] - g["beta"] * math.log(-math.log(1.0 - 1.0 / years))


def annual_exceedance(place: dict[str, Any], mm: float) -> float:
    """Probability the largest day of a year is at least this much rain."""
    g = place["gumbel"]
    return 1.0 - math.exp(-math.exp(-(mm - g["mu"]) / g["beta"]))


class VehicleFlood(Peril):
    key = "vehicle_flood"
    name = "Vehicle, flood from extreme rainfall"
    index_name = "largest daily rainfall where the vehicle is kept"
    unit = "mm in a day"
    basis_risk = (
        "Pays on the rain, not on the car. A car kept high and dry is paid on the "
        "same day as one that floods, and damage from anything but extreme "
        "rainfall, including accidents, theft and hail, is not covered. The "
        "rainfall figures are area averages from a reanalysis, lower than a "
        "single rain gauge would show; the thresholds are set on the same figures."
    )
    basis_risk_level = "high"

    # Ten days, for the same reason as storm: the rainfall that floods a street
    # comes with the same forecast and the same ten day horizon, and a car can
    # be insured in the hour the warning is issued and moved the next morning.
    waiting_days = 10.0

    # Read from the models on disk, not written here: a country is added by
    # building and passing its model, and removed by failing it. The same rule
    # the earthquake models are sold under.
    @property
    def territory(self) -> frozenset[str]:  # type: ignore[override]
        return daily.passed("rain")

    def risk_country(self, subject: dict[str, Any]) -> str | None:
        said = subject.get("country")
        if said:
            return str(said)
        try:
            place, _ = nearest(float(subject["latitude"]), float(subject["longitude"]))
        except (KeyError, TypeError, ValueError):
            return None
        return place.get("country") if place else None

    def validate_subject(self, subject: dict[str, Any]) -> dict[str, Any]:
        try:
            latitude = float(subject["latitude"])
            longitude = float(subject["longitude"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("give where the vehicle is kept, as a latitude and longitude") from error
        place, km = nearest(latitude, longitude)
        if place is None or km > MAX_DISTANCE_KM:
            from ..countries import NAMES

            where = ", ".join(sorted(NAMES.get(c, c) for c in self.territory)) or "nowhere yet"
            raise ValueError(
                f"vehicle cover is written within 60 km of a place whose daily rainfall "
                f"record has been fitted and tested. That is {where}, and the "
                f"nearest such place to this one is further than that"
            )
        here = insured_point(latitude, longitude)
        out = {"latitude": here[0], "longitude": here[1],
               "station": place["name"], "country": place["country"],
               "distance_km": round(km, 1)}
        label = str(subject.get("place", "") or "")[:60]
        if label:
            out["place"] = label
        return out

    def _place(self, subject: dict[str, Any]) -> dict[str, Any]:
        place, _ = nearest(float(subject["latitude"]), float(subject["longitude"]))
        if place is None:
            raise ValueError("no rainfall model for this location")
        return place

    def curve_for(self, subject: dict[str, Any]) -> PayoutCurve:
        place = self._place(subject)
        return curve_from_spec([(round(level_mm(place, y), 1), share) for y, share in LEVELS],
                               shape=Shape.STEP, direction=Direction.ABOVE)

    def default_curve(self) -> PayoutCurve:
        return curve_from_spec([(60.0, 0.25), (75.0, 0.60), (90.0, 1.00)],
                               shape=Shape.STEP, direction=Direction.ABOVE)

    def exceedance(self, subject: dict[str, Any], term_days: float) -> Callable[[float], float]:
        if term_days <= 0:
            raise ValueError("term must be positive")
        place = self._place(subject)
        years = term_days / 365.25

        def probability(mm: float) -> float:
            p = annual_exceedance(place, mm)
            return 1.0 - (1.0 - p) ** years

        return probability

    def data_source(self, subject: dict[str, Any], *,
                    simulated: bool = False) -> DataSource:
        return DataSource(
            reference=(
                (f"api.rain.example/v1/daily-max?" if simulated
                 else "archive-api.open-meteo.com/v1/archive?index=rain&")
                + f"lat={subject['latitude']:g}&lon={subject['longitude']:g}"
            ),
            field="rain_24h_mm",
            unit=self.unit,
            publisher=(
                "a demonstration, measuring nothing" if simulated else
                "the ERA5 reanalysis, with ERA5-Land read against it. No "
                "national meteorological service is read here yet, so this is "
                "a model's estimate for the cell the address falls in and not "
                "a station at the address"),
            resolution="daily totals, final within a few days",
            settlement_deadline_days=14,
            on_missing_data=("If no daily total for the place is published within fourteen days "
                             "of the term ending, the policy expires and the premium is returned in full."),
        )

    def predicate(self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str, *,
                  simulated: bool = False) -> str:
        source = self.data_source(subject, simulated=simulated)
        return f'edge("{source.reference}").{source.field} >= {curve.attachment:g}'

    def describe_subject(self, subject: dict[str, Any]) -> str:
        where = subject.get("place") or f"{subject['latitude']:.3f}, {subject['longitude']:.3f}"
        return f"{where}, rainfall read at {subject.get('station', '')} ({subject.get('distance_km', 0):g} km)"

    def levels(self, subject: dict[str, Any]) -> list[dict[str, Any]]:
        place = self._place(subject)
        return [{"years": y, "mm": round(level_mm(place, y), 1), "share": share,
                 "annual_probability": round(1.0 / y, 4)} for y, share in LEVELS]
