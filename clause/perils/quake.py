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

from .base import (DataSource, Direction, Peril, PayoutCurve, Shape,
                   curve_from_spec, insured_point)
from .geo import (
    Site,
    characteristic_rate_at,
    dominant_magnitude,
    inside_covered_area,
    site_at,
)
from .places import PLACES, find_place
from ..hazard.model import (HazardModel, model_at, model_for, models,
                           priced_countries, published_countries)

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


#: The agency services the measured references are built against. They are
#: written into the policy, so they are part of the contract: a reader can run
#: the same query and reach the same number, which is the whole claim.
EVENT_SERVICE = "earthquake.usgs.gov/fdsnws/event/1/query"
SHAKEMAP_SERVICE = "earthquake.usgs.gov/fdsnws/event/1/query"


#: How far a mapped fault trace can be and still describe the ground at an
#: address. The traces are Türkiye's, so beyond this the nearest one is in
#: another country and its distance says nothing about the site being priced.
TRACES_REACH_KM = 500.0

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

    # Seventy-two hours, and it is the one wait here that does not outlast what
    # it is for. An earthquake gives no warning, so nothing can be bought on a
    # forecast; what can be bought is the aftershock sequence, which is public
    # from the moment the mainshock is felt. That sequence decays as roughly one
    # over time, so it stays elevated for weeks, and a wait long enough to
    # outlast it would be months of cover nobody would buy.
    #
    # What a wait can outlast is the rush. Buying is driven by attention and
    # attention is measured in days, so three of them take in nearly all of the
    # policies bought on a mainshock, and the hour somebody reaches for a phone
    # mid-shake. It is also close to how earthquake cover is sold here, where
    # DASK starts at midnight after the premium is paid; a week on a peril
    # nobody can forecast would be conspicuous, and would read as a trick to
    # anyone hit on the fifth day.
    #
    # So this does not price out the aftershock sequence. The pool carries the
    # rest of it on purpose, and the rest of it is not small.
    waiting_days = 3.0

    # Two kinds of model. Türkiye is priced by the fault model in geo.py, which
    # knows its named faults. Everywhere else is priced by a gridded model built
    # from the catalogue (clause.hazard), and only where that model passed its
    # test on years it never saw. The territory is therefore read from the
    # models on disk, not written here: a country is added by building and
    # passing its model, and removed by failing it.
    @property
    def territory(self) -> frozenset[str]:  # type: ignore[override]
        return frozenset({"TR"}) | priced_countries() | self.published_territory()

    @staticmethod
    def published_territory() -> frozenset[str]:
        """Countries opened by their own authority's published hazard, not ours.

        Our catalogue model for the United States does not pass its own test:
        around 296 American cities it expected 27.5 earthquakes of magnitude 5.5
        and 10 happened, so its level is not fit to price against. The USGS
        publishes the level for that country itself, and where one of its curves
        covers an address the level is theirs and our model is only supplying
        the events. That is a better basis than our own failed backtest, not a
        worse one, so it opens the country -- at those addresses. Whether a
        particular address is one of them is the point level question below.
        """
        have = models()
        return frozenset(code for code in published_countries() if code in have)

    def priced_at(self, latitude: float, longitude: float) -> HazardModel | None:
        """The model that may price this point, and what entitles it to.

        Either our own model passed for this country, or a national authority
        publishes the hazard at this address and our model supplies the events.
        """
        # Whether a published curve is near enough, and nothing more. Asking the
        # shaking layer for its site term here would be asking it to build a map
        # out of rates that this very function is being called to supply, so the
        # disagreement is checked by the caller below rather than here.
        from ..hazard.published import nearest

        passed = model_for(latitude, longitude)
        if passed is not None:
            return passed
        near = nearest(round(latitude, 4), round(longitude, 4))
        if near is None:
            return None
        here = model_at(latitude, longitude)
        if here is not None:
            return here
        # A published curve covers this address and no catalogue outline does.
        # That is Alaska and Hawaii: inside the United States, outside the box
        # the American catalogue was fitted on, and covered by two national
        # models of the USGS's own. The curve says which country published it,
        # and that is the country whose law and licences apply here. Honolulu
        # was refused with "no tested earthquake model covers this location",
        # which was true of our catalogue and not true of the ground.
        return models().get(str(near.get("country") or ""))

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
        model = self.priced_at(latitude, longitude)
        # Whose country it is and which grid prices it are two questions, and
        # they came apart the moment a published curve could cover ground the
        # catalogue was not fitted on. A grid asked about a point outside its
        # own box answers zero, which reads as "no earthquakes here" and is
        # really "this grid is not about here". Honolulu would have been priced
        # at no hazard at all rather than at the background floor.
        if model is not None and not model.in_box(latitude, longitude):
            return None
        return model

    def risk_country(self, subject: dict[str, Any]) -> str | None:
        try:
            latitude, longitude = float(subject["latitude"]), float(subject["longitude"])
        except (KeyError, TypeError, ValueError):
            return "TR"   # a named Turkish place, before validation
        if self.in_turkey(latitude, longitude):
            return "TR"
        model = self.priced_at(latitude, longitude)
        return model.country if model else None

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

        if not self.in_turkey(latitude, longitude):
            from ..perils import shaking as sh

            # The one check that has to come after the model is in hand: where a
            # national authority publishes the hazard at this address and our own
            # events cannot be brought within a factor of two of it, there is no
            # price worth quoting. It is measured, it is often large, and it is
            # nearly always our model that is light.
            if (self.priced_at(latitude, longitude) is not None
                    and sh.beyond_reconciling({"latitude": latitude, "longitude": longitude})):
                near = sh.site_term({"latitude": latitude, "longitude": longitude}) or {}
                # Both figures, not the residual alone. The residual is what
                # the map could not close, and it is the right thing to gate
                # on; it is not what the two models say. At Anchorage they are
                # 128 times apart and the residual is six. A reader asking why
                # their address was refused wants the two numbers, and can
                # check ours against the publisher's own map.
                theirs, ours = near.get("theirs_one_in"), near.get("ours_one_in")
                who = near.get("publisher") or "the national model"
                # Plain digits, no thousands separator. This sentence is
                # written here and translated by pattern, so the separator
                # would be an English one wherever it is read: "11,119" is
                # eleven thousand to one reader and eleven to another.
                if theirs and ours:
                    raise ValueError(
                        f"this address cannot be priced: {who} puts shaking of "
                        f"intensity VII here at about once in {theirs} years and our "
                        f"own events reach once in {ours}. Corrected as far as this "
                        f"model allows, a factor of {near.get('worst_ratio', 0):.0f} is "
                        f"left between them, and a premium from the smaller of the two "
                        f"is not cover"
                    )
                raise ValueError(
                    f"this address cannot be priced: {who} "
                    f"and our own earthquake model disagree by a factor of "
                    f"{near.get('worst_ratio', 0):.0f} about how often the ground here "
                    f"shakes, and a premium from the smaller of the two is not "
                    f"cover. Somewhere else nearby will price"
                )
        if not self.in_turkey(latitude, longitude) and self.priced_at(latitude, longitude) is None:
            priced = ", ".join(sorted(self.territory))
            here = model_at(latitude, longitude)
            # Only where that country really is open on its authority's hazard.
            # Greece's model failed too, and nobody publishes a curve we hold
            # for Greece, so telling a buyer in Athens that cover is written
            # there would be an invitation to nothing.
            if here is not None and not here.passed and here.country in self.published_territory():
                # The country is open, this address is not, and the difference
                # is worth stating rather than answering with a country list the
                # buyer can see their own country in.
                raise ValueError(
                    f"no tested earthquake model reaches this address. Cover in "
                    f"{here.name} is written where its own authority publishes the "
                    f"hazard, because our model for the country did not pass its "
                    f"backtest, and the nearest published figure is more than "
                    f"60 km away. A larger city nearby will have one"
                )
            raise ValueError(
                f"no tested earthquake model covers this location yet; cover is "
                f"written only where one does ({priced})"
            )

        here = insured_point(latitude, longitude)
        out: dict[str, Any] = {
            "latitude": here[0],
            "longitude": here[1],
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
        from ..protocol.valuation import BUILT, home_age_factors
        # A normalised subject always carries its coordinates; one that has not
        # been through normalise may not, and the country's own age table needs
        # them. Without them the generic table decides, which is what a subject
        # outside Türkiye gets anyway.
        lat, lon = subject.get("latitude"), subject.get("longitude")
        country = ("TR" if lat is not None and lon is not None
                   and self.in_turkey(float(lat), float(lon)) else "")
        # A subject with no year is the price bar before the buyer has said
        # anything about the building, so it has to be priced somehow. It used
        # to be priced as a building of the current code, which is the cheapest
        # band there is: in Türkiye 706.29 against 770.98 for the same cover on
        # a pre 1976 building, so the estimate shown first was one no honest
        # answer could improve on, and every honest answer made it dearer.
        #
        # An unknown year is the oldest year instead. The first figure is then
        # the dearest the building could be, and answering only ever brings it
        # down.
        built = subject.get("built")
        _, hazard = home_age_factors(int(built) if built is not None else BUILT[0], country)
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

    def data_source(self, subject: dict[str, Any], *,
                    simulated: bool = False) -> DataSource:
        """Where the index is read.

        Two references, and the difference between them is whether anyone
        goes and asks. The measured one names the agency's own service and the
        exact circle queried against it, so a reader can run the same query and
        get the same answer. The simulated one names a domain reserved for
        examples and can never resolve, which is the only honest address for a
        figure the demonstration produced itself.

        Measured is the default. A path that forgets to say which it wants
        should end up asking the agency, not quietly inventing the number.
        """
        if self.shaking(subject):
            return DataSource(
                reference=(
                    (f"api.seismic.example/v1/shaking?" if simulated
                     # index=mmi is what tells this reference apart from the
                     # magnitude one, which carries a radius instead: same
                     # service, different quantity read out of the response.
                     else f"{SHAKEMAP_SERVICE}?index=mmi&")
                    + f"lat={subject['latitude']:g}&lon={subject['longitude']:g}"
                ),
                field="mmi",
                unit="intensity (MMI)",
                publisher=(
                    "a demonstration, measuring nothing" if simulated else
                    "USGS ShakeMap, which estimates the shaking at the address"),
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
        if simulated:
            publisher = "a demonstration, measuring nothing"
        else:
            publisher = "USGS, with EMSC and, in Türkiye, AFAD read alongside it"
            if grid is not None and grid.sources:
                publisher = (publisher + "; priced on "
                             + ", ".join(s["name"] for s in grid.sources))
        return DataSource(
            reference=(
                (f"api.seismic.example/v1/max-magnitude?" if simulated
                 else f"{EVENT_SERVICE}?")
                + f"lat={subject['latitude']:g}&lon={subject['longitude']:g}"
                + f"&radius_km={radius:g}"
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
        self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str, *,
        simulated: bool = False,
    ) -> str:
        source = self.data_source(subject, simulated=simulated)
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
            # A distance that is not a fact about this site is not said. The
            # trace database is Türkiye's, and it answers a point in Hawaii
            # with 19,253 km, which is the distance to Anatolia rather than a
            # description of Oahu; the sentence then read "no mapped system
            # dominates this site: the nearest trace is about 19253 km away",
            # which contradicts itself in its own second clause. Ankara's
            # nearest trace is 96 km off and that is worth saying.
            if site.nearest_distance_km > TRACES_REACH_KM:
                return (
                    "No mapped fault system reaches this site. The hazard here "
                    "is diffuse background seismicity, and a wider radius buys "
                    "more of it in proportion to area."
                )
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
