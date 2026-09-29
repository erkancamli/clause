"""A home, against storm: extreme wind where it stands.

What it is, and what it is not
------------------------------
This pays when the wind on one day where the home stands is extreme for that
place: stronger than it gets, on average, once in twenty five, fifty or a
hundred years. Roofs, chimneys, cladding and glass go in exactly those days, and a
payout on the day, without an assessor, is what an owner needs to make the
house weathertight before the next front.

It is not buildings insurance. It pays on the wind, not on the roof: a house
behind a hill is paid on the same day as one on a ridge, and a roof that
blows off on a windy day short of the trigger is not paid at all. Hail,
lightning, snow load, flood and anything the wind did not do are not covered.
That basis risk is stated before anyone pays.

The index
---------
The largest daily maximum wind speed at ten metres during the term, from
NASA POWER (the MERRA-2 reanalysis, WS10M_MAX, in km/h) at the provincial
centre nearest the home, read also from the national meteorological service
and ERA5 by each validator. A reanalysis gives the strongest hour's mean over
a cell of about fifty kilometres, not a gust at a station: gusts run half as
much again above it, and more in a squall. The thresholds are that place's
own 1 in 25, 1 in 50 and 1 in 100 year levels in the same series, so a cover on
the Aegean coast and one in a sheltered valley each pay on what is extreme
where they are, and the series a policy is priced on is the series it
settles on.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from .base import DataSource, Direction, PayoutCurve, Peril, Shape, curve_from_spec
from . import daily

MODEL = Path(__file__).resolve().parents[1] / "hazard" / "models" / "wind_TR.json"
MAX_DISTANCE_KM = daily.MAX_DISTANCE_KM
# One step rarer than the car cover's 10, 25 and 50. A 1 in 10 year wind day
# is one most homes see within a decade and one that takes tiles rather than
# roofs; paying a quarter of the rebuild cost on it made the cover cost about
# twice what an Istanbul earthquake policy does, for a loss that is a fraction
# of it. The 1 in 100 level is an extrapolation of a thirty year fit, one
# step beyond the levels the build tests, and is stated as such.
LEVELS = ((25, 0.25), (50, 0.60), (100, 1.00))


def model(code: str = "TR") -> dict[str, Any]:
    """One country's wind model, or an empty one where it was never built."""
    have = daily.models("wind").get(code.upper())
    if have is None:
        return {"places": [], "validation": {"passed": False, "failed": ["not built"]}}
    return have


def nearest(latitude: float, longitude: float) -> tuple[dict[str, Any] | None, float]:
    """The nearest fitted place in any country this cover is written in.

    Every country with a model of its own is searched, and only the ones whose
    model passed its own backtest, which is why the answer carries the country
    it came from: the licence, the law and the model card all follow it.
    """
    return daily.nearest("wind", round(latitude, 4), round(longitude, 4))


def level_kmh(place: dict[str, Any], years: float) -> float:
    g = place["gumbel"]
    return g["mu"] - g["beta"] * math.log(-math.log(1.0 - 1.0 / years))


def annual_exceedance(place: dict[str, Any], kmh: float) -> float:
    """Probability the windiest day of a year is at least this fast."""
    g = place["gumbel"]
    return 1.0 - math.exp(-math.exp(-(kmh - g["mu"]) / g["beta"]))


class Storm(Peril):
    key = "storm"
    name = "Storm, on extreme wind at the address"
    index_name = "largest daily wind speed where the home stands"
    unit = "km/h"
    basis_risk = (
        "Pays on the wind, not on the roof. A house behind a hill is paid on the "
        "same day as one on a ridge, and damage from anything but extreme wind, "
        "including hail, lightning, snow load and flood, is not covered. The wind "
        "figures are the strongest hour's mean over a reanalysis cell, lower than "
        "the gust a station records; the thresholds are set on the same figures."
    )
    basis_risk_level = "high"

    # Ten days. A named storm is forecast on the news roughly a week before it
    # arrives, and the models that feed those forecasts run out to about ten
    # days; past that the atmosphere is not predictable at all. So ten days is
    # where cover stops being a bet on the weather and starts being a bet on
    # the news.
    waiting_days = 10.0

    # Read from the models on disk, not written here: a country is added by
    # building and passing its model, and removed by failing it. The same rule
    # the earthquake models are sold under.
    @property
    def territory(self) -> frozenset[str]:  # type: ignore[override]
        return daily.passed("wind")

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
            raise ValueError("give where the home stands, as a latitude and longitude") from error
        place, km = nearest(latitude, longitude)
        if place is None or km > MAX_DISTANCE_KM:
            from ..countries import NAMES

            where = ", ".join(sorted(NAMES.get(c, c) for c in self.territory)) or "nowhere yet"
            raise ValueError(
                f"storm cover is written within 60 km of a place whose daily wind "
                f"record has been fitted and tested. That is {where}, and the "
                f"nearest such place to this one is further than that"
            )
        out = {"latitude": round(latitude, 4), "longitude": round(longitude, 4),
               "station": place["name"], "country": place["country"],
               "distance_km": round(km, 1)}
        label = str(subject.get("place", "") or "")[:60]
        if label:
            out["place"] = label
        return out

    def _place(self, subject: dict[str, Any]) -> dict[str, Any]:
        place, _ = nearest(float(subject["latitude"]), float(subject["longitude"]))
        if place is None:
            raise ValueError("no wind model for this location")
        return place

    def curve_for(self, subject: dict[str, Any]) -> PayoutCurve:
        place = self._place(subject)
        return curve_from_spec([(round(level_kmh(place, y), 1), share) for y, share in LEVELS],
                               shape=Shape.STEP, direction=Direction.ABOVE)

    def default_curve(self) -> PayoutCurve:
        return curve_from_spec([(75.0, 0.25), (85.0, 0.60), (95.0, 1.00)],
                               shape=Shape.STEP, direction=Direction.ABOVE)

    def exceedance(self, subject: dict[str, Any], term_days: float) -> Callable[[float], float]:
        if term_days <= 0:
            raise ValueError("term must be positive")
        place = self._place(subject)
        years = term_days / 365.25

        def probability(kmh: float) -> float:
            p = annual_exceedance(place, kmh)
            return 1.0 - (1.0 - p) ** years

        return probability

    def data_source(self, subject: dict[str, Any], *,
                    simulated: bool = False) -> DataSource:
        return DataSource(
            reference=(
                (f"api.wind.example/v1/daily-max?" if simulated
                 else "archive-api.open-meteo.com/v1/archive?index=wind&")
                + f"lat={subject['latitude']:g}&lon={subject['longitude']:g}"
            ),
            field="wind_24h_kmh",
            unit=self.unit,
            publisher=(
                "a demonstration, measuring nothing" if simulated else
                "the ERA5 reanalysis, with ERA5-Land read against it. No "
                "national meteorological service is read here yet, so this is "
                "a model's estimate for the cell the address falls in and not "
                "a station at the address"),
            resolution="daily maxima, final within a few days",
            settlement_deadline_days=14,
            on_missing_data=("If no daily maximum for the place is published within fourteen days "
                             "of the term ending, the policy expires and the premium is returned in full."),
        )

    def predicate(self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str, *,
                  simulated: bool = False) -> str:
        source = self.data_source(subject, simulated=simulated)
        return f'edge("{source.reference}").{source.field} >= {curve.attachment:g}'

    def describe_subject(self, subject: dict[str, Any]) -> str:
        where = subject.get("place") or f"{subject['latitude']:.3f}, {subject['longitude']:.3f}"
        return f"{where}, wind read at {subject.get('station', '')} ({subject.get('distance_km', 0):g} km)"

    def levels(self, subject: dict[str, Any]) -> list[dict[str, Any]]:
        place = self._place(subject)
        return [{"years": y, "kmh": round(level_kmh(place, y), 1), "share": share,
                 "annual_probability": round(1.0 / y, 4)} for y, share in LEVELS]
