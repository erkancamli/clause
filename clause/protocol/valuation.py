"""How much something is worth, from how big it is.

Cover is capped by the value at risk; that cap is what makes this insurance
rather than a wager. Until this module the buyer typed the value, so a 100 m²
garden and a 100 hectare farm could buy the same cover. Now the value comes
from what the buyer describes, and the protocol does the arithmetic:

    a home      floor area x rebuild cost per square metre, by country and
                building type, adjusted for the building's age
    a field     area x expected revenue per hectare, by crop
    a trip      what the trip cost, as stated (there is nothing to measure)
    a vehicle   its stated value, checked against what a car of that age can
                be worth, and capped at the market's depreciation curve

Age matters in two opposite directions and both are modelled. An old building
is worth less to rebuild like for like (the schedule's rebuild cost is for a
new one), but it is more likely to be damaged: Türkiye's compulsory scheme
charges more for what was built before the 2000 code, and everything built
before 2000 is the stock that fell in 2023. So an older home gets a lower
ceiling and a higher price, which is what age does everywhere in insurance. A
car simply loses value with age; a fifteen year old car does not carry a new
car's cover whatever the owner says it is worth.

The per unit figures are starting points and are published with every
quote, so the buyer sees how the ceiling was reached. They are indicative
figures in the protocol's unit of account, not a valuation of any property,
and an issuing insurer replaces them with its own schedule.
"""

from __future__ import annotations

import time

from dataclasses import dataclass
from typing import Any

# Rebuild cost per square metre, in the unit of account. Indicative.
# Türkiye from the Ministry's 2025 approximate unit building costs (Yapı
# Yaklaşık Birim Maliyetleri, Official Gazette 31 January 2025): an apartment
# block above 21.5 m (class IV-A) 21,500 TL, a lower residential building
# (III-B) 18,200 TL, a commercial building (IV-B) 27,500 TL, at about 41 lira
# to the unit of account.
REBUILD_PER_M2: dict[str, dict[str, float]] = {
    "TR": {"flat": 525.0, "house": 445.0, "shop": 670.0},
    "JP": {"flat": 2200.0, "house": 2400.0, "shop": 2000.0},
    "CL": {"flat": 900.0, "house": 1000.0, "shop": 850.0},
    "MX": {"flat": 650.0, "house": 700.0, "shop": 600.0},
    "NZ": {"flat": 2600.0, "house": 2900.0, "shop": 2400.0},
    "TW": {"flat": 1100.0, "house": 1200.0, "shop": 1000.0},
}
BUILDINGS = ("flat", "house", "shop")

# Expected revenue of one hectare in a normal season, in the unit of account.
# What a drought takes away is a season's income, so that is what is capped.
REVENUE_PER_HA: dict[str, float] = {
    "wheat": 900.0, "barley": 700.0, "maize": 2000.0, "sunflower": 1100.0,
    "cotton": 2800.0, "chickpea": 1200.0, "lentil": 1000.0, "sugar_beet": 3500.0,
    "other": 800.0,
}

AREA_M2 = (15.0, 3000.0)
THIS_YEAR = time.gmtime().tm_year
BUILT = (1900, THIS_YEAR)
MODEL_YEAR = (1990, THIS_YEAR)

# How a building's age moves its ceiling and its price. The ceiling factor is
# the share of new rebuild cost a like for like rebuild is worth; the hazard
# factor multiplies expected loss, after the DASK tariff's treatment of
# pre 2000 construction and the observed performance of the 1975 and 1998
# codes in 1999 and 2023.
def home_age_factors(built: int, country: str) -> tuple[float, float]:
    age = max(0, THIS_YEAR - built)
    ceiling = max(0.55, 1.0 - 0.01 * age)
    if country == "TR":
        hazard = 1.0 if built >= 2019 else 1.15 if built >= 2000 else 1.6 if built >= 1976 else 2.0
    else:
        hazard = 1.0 if age <= 20 else 1.25 if age <= 45 else 1.5
    return ceiling, hazard


# Straight line to a floor: a car keeps about 85% a year of its value for the
# first years and levels off at a fifth of new.
def vehicle_age_factor(model_year: int) -> float:
    age = max(0, THIS_YEAR - model_year)
    return max(0.2, 0.85 ** age)

# The most a car of a given age can plausibly be worth, so a stated value
# cannot buy new car cover for an old one.
VEHICLE_NEW_CAP = 250_000.0
AREA_HA = (0.01, 5000.0)
TRIP = (50.0, 20000.0)
VEHICLE = (1000.0, 250000.0)


class ValuationError(ValueError):
    """A description that does not give a value. The message is safe to show."""


@dataclass(frozen=True, slots=True)
class Valuation:
    value: float
    basis: str
    size: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"value": round(self.value, 2), "basis": self.basis, "size": dict(self.size)}


def _number(size: dict[str, Any], key: str, bounds: tuple[float, float], what: str) -> float:
    try:
        value = float(size[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValuationError(f"give {what}") from error
    if value != value or not bounds[0] <= value <= bounds[1]:
        raise ValuationError(f"{what} must be between {bounds[0]:g} and {bounds[1]:g}")
    return value


def value_of(size: dict[str, Any], *, country: str | None = None) -> Valuation:
    """The value at risk this description supports."""
    kind = str(size.get("kind", ""))
    if kind == "home":
        code = (country or str(size.get("country", ""))).upper()
        table = REBUILD_PER_M2.get(code)
        if table is None:
            raise ValuationError("there is no rebuild cost schedule for this country yet")
        building = str(size.get("building", "flat"))
        if building not in table:
            raise ValuationError("a home is a flat, a house or a shop")
        area = _number(size, "area_m2", AREA_M2, "the floor area in square metres")
        rate = table[building]
        built = int(_number(size, "built", BUILT, "the year it was built")) if "built" in size else None
        out = {"kind": "home", "building": building, "area_m2": area, "country": code}
        if built is None:
            return Valuation(area * rate, f"{area:g} m² x {rate:,.0f} per m² to rebuild", out)
        ceiling, hazard = home_age_factors(built, code)
        out["built"] = built
        out["hazard_factor"] = hazard
        return Valuation(area * rate * ceiling,
                         f"{area:g} m² x {rate:,.0f} per m² to rebuild, x {ceiling:.0%} for a building of {built}",
                         out)
    if kind == "field":
        crop = str(size.get("crop", "other"))
        if crop not in REVENUE_PER_HA:
            raise ValuationError("unknown crop")
        area = _number(size, "area_ha", AREA_HA, "the area in hectares")
        rate = REVENUE_PER_HA[crop]
        return Valuation(area * rate, f"{area:g} ha x {rate:,.0f} expected revenue per ha",
                         {"kind": "field", "crop": crop, "area_ha": area})
    if kind == "vehicle":
        # A car's value is its market value, which the buyer knows and a size
        # cannot tell; stated, and bounded.
        value = _number(size, "value", VEHICLE, "what the vehicle is worth")
        if "model_year" not in size:
            return Valuation(value, "the vehicle's market value, as stated",
                             {"kind": "vehicle", "value": value})
        year = int(_number(size, "model_year", MODEL_YEAR, "the model year"))
        cap = VEHICLE_NEW_CAP * vehicle_age_factor(year)
        return Valuation(min(value, cap),
                         f"the stated value of {value:,.0f}, capped at {cap:,.0f} for a {year} model",
                         {"kind": "vehicle", "value": value, "model_year": year})
    if kind == "trip":
        value = _number(size, "value", TRIP, "what the trip cost")
        return Valuation(value, "the cost of the trip, as stated", {"kind": "trip", "value": value})
    raise ValuationError("describe what is at risk: a home, a field or a trip")


# Which description each peril needs.
KIND_FOR = {"earthquake": "home", "drought": "field", "flight_delay": "trip",
            "vehicle_flood": "vehicle", "storm": "home"}


def schedule() -> dict[str, Any]:
    """Every figure the page needs to show a buyer the ceiling as they type."""
    return {
        "rebuild_per_m2": REBUILD_PER_M2, "revenue_per_ha": REVENUE_PER_HA,
        "buildings": list(BUILDINGS), "crops": list(REVENUE_PER_HA),
        "area_m2": AREA_M2, "area_ha": AREA_HA, "trip": TRIP, "vehicle": VEHICLE,
        "built": BUILT, "model_year": MODEL_YEAR, "vehicle_new_cap": VEHICLE_NEW_CAP,
        "home_age": {"ceiling_per_year": 0.01, "ceiling_floor": 0.55,
                     "hazard": {"TR": [[2019, 1.0], [2000, 1.15], [1976, 1.6], [0, 2.0]],
                                "*": [[2006, 1.0], [1981, 1.25], [0, 1.5]]}},
        "vehicle_age": {"per_year": 0.85, "floor": 0.2},
        "note": ("indicative figures in the protocol's unit of account; the issuing "
                 "insurer replaces them with its own schedule"),
    }
