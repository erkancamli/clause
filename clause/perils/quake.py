"""Earthquake, on magnitude within a radius.

The index is the largest magnitude recorded inside a circle around the insured
location during the policy term, read from a seismic catalogue. This is the
structure the market calls cat in a box, and it is how almost every parametric
earthquake cover in existence is written, because it settles on two numbers a
seismic network publishes within minutes rather than on a loss adjustment that
takes months.

The model
---------
Magnitudes follow the Gutenberg and Richter relation, which says the annual
count of events at or above a magnitude falls off as a straight line on a log
scale, log10 N(>= M) = a - bM, with b close to one almost everywhere. That
relation describes diffuse background seismicity well.

It describes a mapped fault badly. Large events on a fault recur more often
than an extrapolation from its small events predicts, because the fault
ruptures at a size set by its own geometry rather than at a size drawn from a
smooth distribution. This departure is well documented and the usual answer is
a characteristic earthquake model: truncated Gutenberg and Richter for the
background, plus a separate rate for the fault's own large event.

Both pieces are used here, and they are kept apart on purpose, because they
scale differently with the policy radius. Background seismicity is spread
through the region, so it scales with area. A fault rupture is a line in a
fixed place: either the fault runs inside the circle or it does not. That makes
the radius a real choice for the buyer rather than a dial, and the effect is
visible in the hazard table a quote carries.

Every figure below is illustrative and is the shape of the input, not a hazard
assessment. A live deployment fits them from the national catalogue.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from .base import DataSource, Direction, Peril, PayoutCurve, Shape, curve_from_spec
from .geo import (
    Site,
    characteristic_rate_at,
    dominant_magnitude,
    inside_covered_area,
    site_at,
)
from .places import PLACES, find_place
from ..hazard.model import HazardModel, model_for, models, priced_countries

# Rates are quoted at this magnitude and projected with the b value.
ANCHOR_MAGNITUDE = 4.0

# Background seismicity is truncated here: above this, a region's events belong
# to its mapped faults and are counted by the characteristic term instead.
BACKGROUND_MAXIMUM = 6.6

# Rates are quoted for a circle of this radius and scaled from it, which keeps
# the extrapolation small in both directions.
REFERENCE_RADIUS_KM = 50.0


@dataclass(frozen=True, slots=True)
class SeismicZone:
    """A region, its background seismicity, and the fault that dominates it."""

    code: str
    name: str
    b_value: float
    note: str

    def __post_init__(self) -> None:
        if not 0.6 <= self.b_value <= 1.4:
            raise ValueError(
                f"b value outside the range seen in nature: {self.b_value}"
            )


ZONES: dict[str, SeismicZone] = {
    "TR-MARMARA": SeismicZone(
        "TR-MARMARA", "Marmara and the North Anatolian Fault", 0.96,
        "A right lateral strike slip system running beneath the Sea of Marmara.",
    ),
    "TR-EAST": SeismicZone(
        "TR-EAST", "East Anatolian Fault", 0.98,
        "The left lateral system along the Anatolia and Arabia boundary.",
    ),
    "TR-AEGEAN": SeismicZone(
        "TR-AEGEAN", "Western Anatolia and the Aegean", 1.02,
        "Extensional grabens with frequent moderate events and no single "
        "dominant characteristic rupture.",
    ),
    "TR-CENTRAL": SeismicZone(
        "TR-CENTRAL", "Central Anatolia", 0.94,
        "A markedly quieter interior block.",
    ),
}


@dataclass(frozen=True, slots=True)
class Location:
    """Somewhere insurable, with its own local hazard.

    ``background_rate`` is the annual count of magnitude four and above from
    diffuse seismicity within the reference radius. ``characteristic_*``
    describe the mapped fault's own large event, and ``fault_distance_km`` is
    how far that fault runs from the site, which is what decides whether a
    given policy radius captures it at all.
    """

    code: str
    name: str
    zone: str
    latitude: float
    longitude: float
    background_rate: float
    characteristic_magnitude: float | None
    characteristic_return_years: float | None
    fault_distance_km: float | None

    def __post_init__(self) -> None:
        if self.background_rate <= 0:
            raise ValueError("background rate must be positive")
        has_fault = self.characteristic_magnitude is not None
        if has_fault and (
            self.characteristic_return_years is None
            or self.fault_distance_km is None
        ):
            raise ValueError(
                "a characteristic event needs a return period and a fault distance"
            )

    @property
    def characteristic_rate(self) -> float:
        if not self.characteristic_return_years:
            return 0.0
        return 1.0 / self.characteristic_return_years


LOCATIONS: dict[str, Location] = {
    # The Marmara segment runs close to the city on both sides of the Bosphorus.
    "IST-KADIKOY": Location(
        "IST-KADIKOY", "Istanbul, Kadikoy", "TR-MARMARA", 40.99, 29.03,
        background_rate=1.55,
        characteristic_magnitude=7.2,
        characteristic_return_years=88.0,
        fault_distance_km=18.0,
    ),
    "IST-BAKIRKOY": Location(
        "IST-BAKIRKOY", "Istanbul, Bakirkoy", "TR-MARMARA", 40.98, 28.87,
        background_rate=1.62,
        characteristic_magnitude=7.2,
        characteristic_return_years=88.0,
        fault_distance_km=14.0,
    ),
    # Aegean extension: frequent moderate events, no single dominant rupture.
    "IZM-KONAK": Location(
        "IZM-KONAK", "Izmir, Konak", "TR-AEGEAN", 38.42, 27.13,
        background_rate=2.40,
        characteristic_magnitude=6.9,
        characteristic_return_years=210.0,
        fault_distance_km=32.0,
    ),
    "ADY-MERKEZ": Location(
        "ADY-MERKEZ", "Adiyaman", "TR-EAST", 37.76, 38.28,
        background_rate=1.10,
        characteristic_magnitude=7.4,
        characteristic_return_years=140.0,
        fault_distance_km=26.0,
    ),
    # A quiet interior site, and the reason a protocol needs more than one.
    "ANK-CANKAYA": Location(
        "ANK-CANKAYA", "Ankara, Cankaya", "TR-CENTRAL", 39.90, 32.85,
        background_rate=0.18,
        characteristic_magnitude=None,
        characteristic_return_years=None,
        fault_distance_km=None,
    ),
}

# Radii a policy may be written on. A tighter circle is a truer proxy for
# shaking at the address and a looser one pays more often.
ALLOWED_RADII_KM = (25.0, 50.0, 100.0)
# What the policy measures: the largest magnitude inside a circle, or how hard
# the ground shook at the address itself.
INDICES = ("magnitude", "shaking")

# Half width of the magnitude band a characteristic rupture falls in.
_CHARACTERISTIC_HALF_WIDTH = 0.25


class Earthquake(Peril):
    key = "earthquake"
    name = "Earthquake, on magnitude within a radius"
    index_name = "largest magnitude recorded inside the policy radius"
    unit = "magnitude"
    basis_risk = (
        "High, and it runs both ways. Magnitude and distance are a proxy for "
        "how hard the ground moved at one address, and the proxy is loose: "
        "soil, depth and the direction a rupture travels can change shaking "
        "several fold between neighbours. A policy can pay after an event that "
        "broke nothing, and fail to pay after one that did. This cover is a "
        "liquidity instrument that settles in minutes, and it is not a "
        "substitute for indemnity insurance on the building."
    )
    basis_risk_level = "high"

    # Seven days. An earthquake gives no warning, so nothing can be bought on a
    # forecast; what can be bought is the aftershock sequence, which is public
    # the moment the mainshock is felt and is where the next weeks of shaking
    # actually sit. Seven days covers the part of that sequence a buyer can see
    # coming. It also covers the hour someone reaches for a phone mid-shake.
    waiting_days = 7.0

    # Two kinds of model. Türkiye is priced by the fault model in geo.py, which
    # knows its named faults. Everywhere else is priced by a gridded model built
    # from the catalogue (clause.hazard), and only where that model passed its
    # test on years it never saw. The territory is therefore read from the
    # models on disk, not written here: a country is added by building and
    # passing its model, and removed by failing it.
    @property
    def territory(self) -> frozenset[str]:  # type: ignore[override]
        return frozenset({"TR"}) | priced_countries()

    @staticmethod
    def in_turkey(latitude: float, longitude: float) -> bool:
        """On Turkish land or just off its coast, by the outline when there is one.

        The fault model's box also takes in Lesbos, Cyprus and northern Syria. A
        box was a fair first approximation of a country and is a poor answer to
        "whose law, whose licence", so the outline decides when it is present.
        """
        outline = models().get("TR")
        if outline is not None and outline.outline:
            return outline.contains(latitude, longitude)
        return inside_covered_area(latitude, longitude)

    def grid_model(self, subject: dict[str, Any]) -> HazardModel | None:
        """The catalogue model pricing this subject, or None where faults do."""
        latitude, longitude = float(subject["latitude"]), float(subject["longitude"])
        if self.in_turkey(latitude, longitude):
            return None
        return model_for(latitude, longitude)

    def risk_country(self, subject: dict[str, Any]) -> str | None:
        try:
            latitude, longitude = float(subject["latitude"]), float(subject["longitude"])
        except (KeyError, TypeError, ValueError):
            return "TR"   # a named Turkish place, before validation
        if self.in_turkey(latitude, longitude):
            return "TR"
        model = model_for(latitude, longitude)
        return model.code if model else None

    def validate_subject(self, subject: dict[str, Any]) -> dict[str, Any]:
        """A subject is a coordinate and a radius. A place name is a shortcut.

        Cover used to be offered at five named addresses, which is not cover.
        Any coordinate inside the covered area is now insurable, and the named
        places are a convenience for the interface rather than the model's
        basis.
        """
        index = str(subject.get("index", "magnitude"))
        if index not in INDICES:
            raise ValueError(f"index must be one of {INDICES}")
        radius = float(subject.get("radius_km", 50.0))
        if radius not in ALLOWED_RADII_KM:
            raise ValueError(f"radius must be one of {ALLOWED_RADII_KM}, got {radius}")

        if "latitude" in subject and "longitude" in subject:
            latitude = float(subject["latitude"])
            longitude = float(subject["longitude"])
            label = str(subject.get("place", "") or "")[:60]
        else:
            name = str(subject.get("location", "")).strip()
            place = find_place(name)
            if place is None:
                raise ValueError(
                    f"unknown place {name!r}; give a latitude and longitude, or "
                    f"a place from the offered list"
                )
            latitude, longitude, label = place.latitude, place.longitude, place.name

        if not self.in_turkey(latitude, longitude) and model_for(latitude, longitude) is None:
            priced = ", ".join(sorted(self.territory))
            raise ValueError(
                f"no tested earthquake model covers this location yet; cover is "
                f"written only where one does ({priced})"
            )

        out: dict[str, Any] = {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "radius_km": radius,
        }
        if label:
            out["place"] = label
        if index == "shaking":
            out["index"] = "shaking"
        # The year the building was built, when the buyer said. It moves the
        # trigger, not the hazard: an older building is damaged by less.
        if subject.get("built") not in (None, ""):
            built = int(float(subject["built"]))
            from ..protocol.valuation import THIS_YEAR
            if not 1900 <= built <= THIS_YEAR:
                raise ValueError(f"the year built must be between 1900 and {THIS_YEAR}")
            out["built"] = built
        return out

    def vulnerability(self, subject: dict[str, Any]) -> float:
        """How much less shaking it takes to damage this building than a new
        one, in intensity units. Zero for a building of the current code.

        From the hazard factor the valuation gives a building's age: a factor
        of 2 (Türkiye, before the 1975 code) is three quarters of an intensity
        unit, since damage ratios roughly double per unit of intensity."""
        built = subject.get("built")
        if built is None:
            return 0.0
        from ..protocol.valuation import home_age_factors
        country = "TR" if self.in_turkey(float(subject["latitude"]), float(subject["longitude"])) else ""
        _, hazard = home_age_factors(int(built), country)
        return round(min(0.75, max(0.0, (hazard - 1.0) * 0.75)), 2)

    def site(self, subject: dict[str, Any]) -> Site:
        return site_at(float(subject["latitude"]), float(subject["longitude"]))

    # -- hazard -----------------------------------------------------------

    def background_rate(self, subject: dict[str, Any], magnitude: float) -> float:
        """Annual rate of background events at or above a magnitude.

        Truncated Gutenberg and Richter, scaled by the area of the policy
        circle against the reference circle, because diffuse seismicity is
        spread through the region rather than tied to one line.
        """
        grid = self.grid_model(subject)
        if grid is not None:
            return grid.rate_within(float(subject["latitude"]), float(subject["longitude"]),
                                    float(subject["radius_km"]), magnitude)
        site = self.site(subject)
        b = site.b_value
        radius = float(subject["radius_km"])

        if magnitude >= BACKGROUND_MAXIMUM:
            return 0.0

        anchor = max(magnitude, ANCHOR_MAGNITUDE)
        top = pow(10.0, -b * (BACKGROUND_MAXIMUM - ANCHOR_MAGNITUDE))
        here = pow(10.0, -b * (anchor - ANCHOR_MAGNITUDE))
        truncated_share = (here - top) / (1.0 - top)

        area_ratio = (radius * radius) / (REFERENCE_RADIUS_KM * REFERENCE_RADIUS_KM)
        return site.background_rate * truncated_share * area_ratio

    def characteristic_rate(self, subject: dict[str, Any], magnitude: float) -> float:
        """Annual rate of a mapped system's own large event inside the circle.

        A fault is a line, so what matters is how much of that line the policy
        circle contains. Widening the radius buys a continuously larger share of
        the trace rather than flipping the fault from out to in, which is both
        closer to how a line source behaves and fairer to price.
        """
        if self.grid_model(subject) is not None:
            return 0.0   # the catalogue model has no separate fault term
        radius = float(subject["radius_km"])
        latitude = float(subject["latitude"])
        longitude = float(subject["longitude"])

        total, breakdown = characteristic_rate_at(latitude, longitude, radius)
        if total <= 0:
            return 0.0

        centre = dominant_magnitude(latitude, longitude, radius)
        if centre is None:
            return 0.0

        low = centre - _CHARACTERISTIC_HALF_WIDTH
        high = centre + _CHARACTERISTIC_HALF_WIDTH
        if magnitude <= low:
            share = 1.0
        elif magnitude >= high:
            share = 0.0
        else:
            share = (high - magnitude) / (high - low)
        return total * share

    def local_rate(self, subject: dict[str, Any], magnitude: float) -> float:
        """Total annual rate of qualifying events inside the policy radius."""
        return self.background_rate(subject, magnitude) + self.characteristic_rate(
            subject, magnitude
        )

    # -- peril interface --------------------------------------------------

    @staticmethod
    def shaking(subject: dict[str, Any]) -> bool:
        return subject.get("index") == "shaking"

    def curve_for(self, subject: dict[str, Any]) -> PayoutCurve:
        if self.shaking(subject):
            # Starts where buildings are damaged, as an indemnity policy's
            # deductible does: VI is felt by everyone and cracks plaster, and
            # paying on it made the cover several times dearer than any
            # insurer's. VII damages ordinary buildings, VIII severely, IX
            # destroys many. An older building's steps sit lower. Stepped, so
            # a reading a tenth below a level loses one step, not everything.
            d = self.vulnerability(subject)
            return curve_from_spec([(round(7.0 - d, 2), 0.35), (round(8.0 - d, 2), 0.75), (round(9.0 - d, 2), 1.00)],
                                   shape=Shape.STEP, direction=Direction.ABOVE)
        d = round(self.vulnerability(subject) * 0.4, 2)   # the magnitude step that moves intensity by d
        if d:
            return curve_from_spec([(round(5.5 - d, 2), 0.25), (round(6.5 - d, 2), 0.60), (round(7.0 - d, 2), 1.00)],
                                   shape=Shape.STEP, direction=Direction.ABOVE)
        return self.default_curve()

    def title_for(self, subject: dict[str, Any]) -> str:
        if self.shaking(subject):
            return "Earthquake, on shaking at the address"
        return self.name

    def unit_for(self, subject: dict[str, Any]) -> str:
        return "intensity (MMI)" if self.shaking(subject) else self.unit

    def data_source(self, subject: dict[str, Any]) -> DataSource:
        if self.shaking(subject):
            return DataSource(
                reference=(f"api.seismic.example/v1/shaking"
                           f"?lat={subject['latitude']:g}&lon={subject['longitude']:g}"),
                field="mmi",
                unit="intensity (MMI)",
                publisher="USGS ShakeMap and the national network's shaking map, attested by validators",
                resolution="first map within an hour of an event, revised as stations report",
                settlement_deadline_days=7,
                on_missing_data=(
                    "If no shaking map covering the address is published within seven "
                    "days of the term ending, the policy expires and the premium is "
                    "returned in full."
                ),
            )
        radius = subject["radius_km"]
        grid = self.grid_model(subject) if "latitude" in subject else None
        publisher = "national seismic network, attested by validators"
        if grid is not None and grid.sources:
            publisher = ", ".join(s["name"] for s in grid.sources) + ", attested by validators"
        return DataSource(
            reference=(
                f"api.seismic.example/v1/max-magnitude"
                f"?lat={subject['latitude']:g}&lon={subject['longitude']:g}"
                f"&radius_km={radius:g}"
            ),
            field="max_magnitude",
            unit=self.unit,
            publisher=publisher,
            resolution="revised within minutes of an event and final within days",
            settlement_deadline_days=7,
            on_missing_data=(
                "If the network publishes nothing for the radius within seven "
                "days of the term ending, the policy expires and the premium is "
                "returned in full."
            ),
        )

    def default_curve(self) -> PayoutCurve:
        """Tiered by magnitude, the standard cat in a box structure."""
        return curve_from_spec(
            [(5.5, 0.25), (6.5, 0.60), (7.0, 1.00)],
            shape=Shape.STEP,
            direction=Direction.ABOVE,
        )

    def exceedance(
        self, subject: dict[str, Any], term_days: float
    ) -> Callable[[float], float]:
        """Probability of at least one event at or above a magnitude in the term.

        Poisson occurrence, so the chance of the term passing without one is
        exp of minus the expected count.
        """
        if term_days <= 0:
            raise ValueError("term must be positive")
        if self.shaking(subject):
            from .shaking import exceedance as shaking_exceedance
            return shaking_exceedance(subject, term_days)
        years = term_days / 365.25

        def probability(magnitude: float) -> float:
            expected = self.local_rate(subject, magnitude) * years
            return 1.0 - math.exp(-expected)

        return probability

    def predicate(
        self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str
    ) -> str:
        source = self.data_source(subject)
        return f'edge("{source.reference}").{source.field} >= {curve.attachment:g}'

    def describe_subject(self, subject: dict[str, Any]) -> str:
        where = subject.get("place") or (
            f"{subject['latitude']:.3f}, {subject['longitude']:.3f}"
        )
        if self.shaking(subject):
            return f"{where}, shaking at the address"
        return f"{where}, within {subject['radius_km']:g} km"

    # -- disclosure -------------------------------------------------------

    def hazard_table(self, subject: dict[str, Any]) -> list[dict[str, Any]]:
        """Return periods by magnitude, split into background and fault.

        A buyer choosing between radii is choosing between hazard curves, and
        the split shows why: the fault term appears only once the circle
        reaches it, and it is what carries the large magnitudes.
        """
        rows: list[dict[str, Any]] = []
        for magnitude in (5.0, 5.5, 6.0, 6.5, 7.0, 7.5):
            background = self.background_rate(subject, magnitude)
            characteristic = self.characteristic_rate(subject, magnitude)
            total = background + characteristic
            rows.append(
                {
                    "magnitude": magnitude,
                    "background_rate": background,
                    "characteristic_rate": characteristic,
                    "annual_rate": total,
                    "return_period_years": math.inf if total <= 0 else 1.0 / total,
                }
            )
        return rows

    def radius_note(self, subject: dict[str, Any]) -> str:
        """What this radius does and does not capture, in words.

        The radius is the buyer's main lever on basis risk, so the effect of
        moving it is stated rather than left to be discovered in the price.
        """
        grid = self.grid_model(subject)
        if grid is not None:
            return self._grid_note(grid, subject)
        site = self.site(subject)
        radius = float(subject["radius_km"])
        latitude, longitude = site.latitude, site.longitude
        rate, _ = characteristic_rate_at(latitude, longitude, radius)

        if site.nearest is None:
            return (
                "No mapped system dominates this site: the nearest trace is "
                f"about {site.nearest_distance_km:.0f} km away. The hazard here "
                "is diffuse background seismicity, and a wider radius buys more "
                "of it in proportion to area."
            )

        if rate <= 0:
            return (
                f"The {site.nearest.name} runs about "
                f"{site.nearest_distance_km:.0f} km away, outside this "
                f"{radius:g} km circle, so its magnitude "
                f"{site.nearest.characteristic_magnitude:g} rupture would not "
                f"register on this index. A wider radius covers it, and the "
                f"price will say so."
            )

        wider, _ = characteristic_rate_at(latitude, longitude, min(100.0, radius * 2))
        extra = ""
        if wider > rate * 1.15:
            extra = (
                f" Doubling the radius would bring in about "
                f"{wider / rate:.1f} times as much of the trace."
            )
        gap = f" {site.nearest.gap_note}" if site.nearest.gap_note else ""
        return (
            f"This {radius:g} km circle contains part of the {site.nearest.name}, "
            f"whose characteristic magnitude is "
            f"{site.nearest.characteristic_magnitude:g}. A large event on the "
            f"stretch inside the circle is expected about once every "
            f"{1 / rate:.0f} years.{gap}{extra}"
        )

    def _grid_note(self, grid: HazardModel, subject: dict[str, Any]) -> str:
        """The radius note where a catalogue model prices, in its own terms."""
        latitude, longitude = float(subject["latitude"]), float(subject["longitude"])
        radius = float(subject["radius_km"])
        rate = grid.rate_within(latitude, longitude, radius, 5.5)
        per_century = rate * 100
        wider = grid.rate_within(latitude, longitude, min(100.0, radius * 2), 5.5)
        extra = ""
        if radius < 100 and rate > 0 and wider > rate * 1.15:
            extra = f" Doubling the radius would take in about {wider / rate:.1f} times as many."
        tested = grid.validation.get("tested_from")
        return (
            f"About {per_century:.0f} earthquakes of magnitude 5.5 or more a century "
            f"are expected with their epicentre inside this {radius:g} km circle, from "
            f"the {grid.name} catalogue model, which was tested on {tested} onward "
            f"before it was used to price anything.{extra}"
        )
