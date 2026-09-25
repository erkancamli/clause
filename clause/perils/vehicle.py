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

from .base import DataSource, Direction, PayoutCurve, Peril, Shape, curve_from_spec
from .geo import distance_km

MODEL = Path(__file__).resolve().parents[1] / "hazard" / "models" / "rain_TR.json"
MAX_DISTANCE_KM = 60.0
LEVELS = ((10, 0.25), (25, 0.60), (50, 1.00))


@lru_cache(maxsize=1)
def model() -> dict[str, Any]:
    if not MODEL.exists():
        return {"places": [], "validation": {"passed": False}}
    return json.loads(MODEL.read_text(encoding="utf-8"))


def nearest(latitude: float, longitude: float) -> tuple[dict[str, Any] | None, float]:
    best, best_km = None, float("inf")
    for place in model()["places"]:
        km = distance_km((latitude, longitude), (place["latitude"], place["longitude"]))
        if km < best_km:
            best, best_km = place, km
    return best, best_km


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

    @property
    def territory(self) -> frozenset[str]:  # type: ignore[override]
        return frozenset({"TR"}) if model()["validation"].get("passed") else frozenset()

    def risk_country(self, subject: dict[str, Any]) -> str | None:
        return "TR"

    def validate_subject(self, subject: dict[str, Any]) -> dict[str, Any]:
        try:
            latitude = float(subject["latitude"])
            longitude = float(subject["longitude"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("give where the vehicle is kept, as a latitude and longitude") from error
        place, km = nearest(latitude, longitude)
        if place is None or km > MAX_DISTANCE_KM:
            raise ValueError("vehicle cover is written only within 60 km of a Türkiye "
                             "provincial centre, where the rainfall model is tested")
        out = {"latitude": round(latitude, 4), "longitude": round(longitude, 4),
               "station": place["name"], "distance_km": round(km, 1)}
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
        # No feed reads this peril yet, so both references are the one that
        # measures nothing. See oracle/feed.py for the ones that do.
        del simulated
        return DataSource(
            reference=(f"api.rain.example/v1/daily-max?lat={subject['latitude']:g}"
                       f"&lon={subject['longitude']:g}"),
            field="rain_24h_mm",
            unit=self.unit,
            publisher="the national meteorological service's nearest station first; NASA POWER (MERRA-2) and ERA5, quantile-mapped to the station, standing in; attested by validators",
            resolution="daily totals, final within a few days",
            settlement_deadline_days=14,
            on_missing_data=("If no daily total for the place is published within fourteen days "
                             "of the term ending, the policy expires and the premium is returned in full."),
        )

    def predicate(self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str) -> str:
        source = self.data_source(subject)
        return f'edge("{source.reference}").{source.field} >= {curve.attachment:g}'

    def describe_subject(self, subject: dict[str, Any]) -> str:
        where = subject.get("place") or f"{subject['latitude']:.3f}, {subject['longitude']:.3f}"
        return f"{where}, rainfall read at {subject.get('station', '')} ({subject.get('distance_km', 0):g} km)"

    def levels(self, subject: dict[str, Any]) -> list[dict[str, Any]]:
        place = self._place(subject)
        return [{"years": y, "mm": round(level_mm(place, y), 1), "share": share,
                 "annual_probability": round(1.0 / y, 4)} for y, share in LEVELS]
