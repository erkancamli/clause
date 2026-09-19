"""Where a place is, and what runs underneath it.

The first version of this model held five named cities, each carrying a hand
written seismicity figure and a hand written distance to its fault. That is a
demonstration, not a product: an insurer that can only cover five addresses is
not covering anything, and the obvious question from anyone looking at it is why
their own town is not on the list.

So the named places are gone as the model's basis. What replaces them is the
geometry that was implicit in those five numbers all along.

A fault is a line, not a point
------------------------------
Turkey's seismicity is dominated by mapped strike slip systems, and a fault is a
line on a map. That has three consequences the earlier model could not express:

  Distance is continuous. Every coordinate in the country has a distance to the
  nearest trace, so every coordinate has a hazard, and nobody has to be on a
  list.

  A policy circle intersects a length of fault, not a yes or no. The earlier
  model asked whether the fault was inside the circle at all, which made a 49 km
  radius and a 51 km radius wildly different prices for no physical reason. Here
  the characteristic contribution scales with how much of the trace the circle
  actually contains, which is both smoother and closer to how a line source is
  treated in practice.

  Background seismicity decays away from the trace. Diffuse activity is not
  uniform across a country; it clusters around the systems that produce it. A
  point far from every mapped fault is quieter, and the model says so rather
  than being told so.

What is real and what is illustrative
-------------------------------------
The fault traces are simplified polylines following the published surface traces
of the North Anatolian, East Anatolian, West Anatolian graben and Central
Anatolian systems, at a resolution of a handful of vertices each. They are the
right shape and in the right place to a few kilometres, which is the accuracy
this model can use.

The rates attached to them are illustrative and calibrated so the model
reproduces the figures the earlier version carried for its five cities, which
were themselves chosen to land near published return periods. A deployment
replaces the rate parameters with a fit to the national catalogue and keeps
every line of the geometry.

Distances use an equirectangular projection about the midpoint of the two
coordinates. Across Turkey that is accurate to well under a percent, which is
far finer than the fault traces themselves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Sequence

EARTH_RADIUS_KM = 6371.0


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Kilometres between two points, given as (latitude, longitude)."""
    lat1, lon1 = a
    lat2, lon2 = b
    mid = math.radians((lat1 + lat2) * 0.5)
    x = math.radians(lon2 - lon1) * math.cos(mid)
    y = math.radians(lat2 - lat1)
    return EARTH_RADIUS_KM * math.hypot(x, y)


def _project(point: tuple[float, float], origin: tuple[float, float]) -> tuple[float, float]:
    """Local kilometres east and north of an origin."""
    lat, lon = point
    lat0, lon0 = origin
    east = math.radians(lon - lon0) * math.cos(math.radians(lat0)) * EARTH_RADIUS_KM
    north = math.radians(lat - lat0) * EARTH_RADIUS_KM
    return east, north


def distance_to_segment_km(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Shortest distance from a point to a line segment, in kilometres."""
    px, py = _project(point, point)          # the point is the origin: (0, 0)
    ax, ay = _project(start, point)
    bx, by = _project(end, point)

    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(ax, ay)

    # Where along the segment the nearest point falls, clamped to its ends.
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(ax + t * dx, ay + t * dy)


def _segment_length_inside_circle(
    start: tuple[float, float],
    end: tuple[float, float],
    centre: tuple[float, float],
    radius_km: float,
    steps: int = 24,
) -> float:
    """How much of a segment lies inside a circle, in kilometres.

    Sampled rather than solved: the trace is a simplification to a few
    kilometres already, so an exact intersection would be false precision, and
    sampling handles a segment that enters and leaves without special cases.
    """
    total = distance_km(start, end)
    if total == 0:
        return 0.0
    inside = 0
    for index in range(steps):
        fraction = (index + 0.5) / steps
        point = (
            start[0] + (end[0] - start[0]) * fraction,
            start[1] + (end[1] - start[1]) * fraction,
        )
        if distance_km(point, centre) <= radius_km:
            inside += 1
    return total * inside / steps


@dataclass(frozen=True, slots=True)
class FaultSystem:
    """A mapped system, its trace, and what it produces.

    ``characteristic_return_per_100km`` is the recurrence of the system's own
    large event along a hundred kilometres of trace. A policy circle containing
    thirty kilometres of trace carries three tenths of that rate, which is what
    makes the radius a continuous choice rather than a threshold.
    """

    code: str
    name: str
    zone: str
    b_value: float
    characteristic_magnitude: float
    characteristic_return_per_100km: float
    # Background seismicity around the trace: a floor away from it, an amplitude
    # at it, and the distance over which the amplitude decays.
    background_floor: float
    background_amplitude: float
    decay_km: float
    trace: tuple[tuple[float, float], ...]
    note: str
    # Stretches of the trace late in their cycle, as (first vertex, last vertex,
    # factor). A seismic gap is a published, physical idea rather than a fudge:
    # a segment that has not ruptured while its neighbours have is carrying
    # accumulated strain, and every hazard model for the Marmara says so.
    elevated: tuple[tuple[int, int, float], ...] = ()
    gap_note: str = ""

    def segment_factor(self, index: int) -> float:
        for start, end, factor in self.elevated:
            if start <= index < end:
                return factor
        return 1.0

    def distance_km(self, point: tuple[float, float]) -> float:
        return min(
            distance_to_segment_km(point, self.trace[i], self.trace[i + 1])
            for i in range(len(self.trace) - 1)
        )

    def length_inside(self, centre: tuple[float, float], radius_km: float) -> float:
        return sum(
            _segment_length_inside_circle(
                self.trace[i], self.trace[i + 1], centre, radius_km
            )
            for i in range(len(self.trace) - 1)
        )

    def weighted_length_inside(
        self, centre: tuple[float, float], radius_km: float
    ) -> float:
        """Trace length inside the circle, with late segments counted heavier."""
        return sum(
            _segment_length_inside_circle(
                self.trace[i], self.trace[i + 1], centre, radius_km
            ) * self.segment_factor(i)
            for i in range(len(self.trace) - 1)
        )


# Simplified surface traces. Vertices are (latitude, longitude).
FAULT_SYSTEMS: tuple[FaultSystem, ...] = (
    FaultSystem(
        code="NAF", name="North Anatolian Fault", zone="TR-NAF",
        b_value=0.96, characteristic_magnitude=7.3,
        characteristic_return_per_100km=250.0,
        background_floor=0.04, background_amplitude=2.50, decay_km=40.0,
        trace=(
            (40.62, 26.40), (40.68, 27.30), (40.72, 28.20), (40.78, 28.95),
            (40.74, 29.70), (40.72, 30.35), (40.78, 31.20), (40.82, 32.20),
            (40.72, 33.40), (40.60, 34.80), (40.45, 36.00), (40.30, 37.10),
            (40.05, 38.40), (39.88, 39.60), (39.78, 40.80), (39.70, 42.00),
            (39.66, 43.20),
        ),
        elevated=((1, 4, 3.0),),
        gap_note=(
            "The stretch beneath the Sea of Marmara has not ruptured while the "
            "segments on either side of it have, so it carries a materially "
            "higher rate here than the system's average."
        ),
        note=(
            "A right lateral strike slip system running the length of northern "
            "Anatolia and beneath the Sea of Marmara. It has ruptured westwards "
            "in sequence through the twentieth century."
        ),
    ),
    FaultSystem(
        code="EAF", name="East Anatolian Fault", zone="TR-EAST",
        b_value=0.98, characteristic_magnitude=7.5,
        characteristic_return_per_100km=290.0,
        background_floor=0.05, background_amplitude=1.35, decay_km=60.0,
        trace=(
            (36.20, 36.10), (36.75, 36.45), (37.25, 36.95), (37.70, 37.75),
            (38.15, 38.55), (38.50, 39.35), (38.85, 40.05), (39.25, 40.75),
            (39.55, 41.30),
        ),
        note=(
            "The left lateral system along the boundary between the Anatolian "
            "and Arabian plates, which ruptured in two large events in 2023."
        ),
    ),
    FaultSystem(
        code="BITLIS", name="Bitlis and Van thrust belt", zone="TR-EASTHIGH",
        b_value=0.97, characteristic_magnitude=7.1,
        characteristic_return_per_100km=520.0,
        background_floor=0.05, background_amplitude=1.15, decay_km=55.0,
        trace=(
            (37.90, 41.00), (38.20, 42.00), (38.50, 43.10), (38.90, 43.60),
            (39.40, 43.90),
        ),
        note=(
            "The contractional belt of eastern Anatolia, which produced the "
            "1976 Çaldıran and 2011 Van earthquakes."
        ),
    ),
    FaultSystem(
        code="AEG-GEDIZ", name="Gediz graben", zone="TR-AEGEAN",
        b_value=1.02, characteristic_magnitude=6.9,
        characteristic_return_per_100km=420.0,
        background_floor=0.12, background_amplitude=2.30, decay_km=48.0,
        trace=((38.44, 26.90), (38.50, 27.60), (38.58, 28.30), (38.66, 29.10)),
        note=(
            "An east west extensional graben in western Anatolia. The region "
            "produces frequent moderate events rather than one dominant rupture."
        ),
    ),
    FaultSystem(
        code="AEG-MENDERES", name="Büyük Menderes graben", zone="TR-AEGEAN",
        b_value=1.02, characteristic_magnitude=6.8,
        characteristic_return_per_100km=450.0,
        background_floor=0.12, background_amplitude=2.05, decay_km=48.0,
        trace=((37.75, 27.20), (37.82, 27.95), (37.88, 28.70), (37.95, 29.40)),
        note="A parallel graben to the south, with the same extensional style.",
    ),
    FaultSystem(
        code="AEG-SIMAV", name="Simav graben", zone="TR-AEGEAN",
        b_value=1.02, characteristic_magnitude=6.7,
        characteristic_return_per_100km=500.0,
        background_floor=0.10, background_amplitude=1.70, decay_km=45.0,
        trace=((39.05, 28.40), (39.12, 29.10), (39.20, 29.85)),
        note="The northern of the western Anatolian grabens.",
    ),
    FaultSystem(
        code="TUZ", name="Tuz Gölü fault", zone="TR-CENTRAL",
        b_value=0.94, characteristic_magnitude=6.5,
        characteristic_return_per_100km=1100.0,
        background_floor=0.02, background_amplitude=0.20, decay_km=38.0,
        trace=((38.20, 33.55), (38.80, 33.40), (39.40, 33.25)),
        note=(
            "A quieter normal fault in the central Anatolian interior, which is "
            "the calmest part of the country."
        ),
    ),
    FaultSystem(
        code="ECEMIS", name="Ecemiş fault", zone="TR-CENTRAL",
        b_value=0.94, characteristic_magnitude=6.6,
        characteristic_return_per_100km=950.0,
        background_floor=0.02, background_amplitude=0.26, decay_km=38.0,
        trace=((37.20, 35.05), (37.90, 35.25), (38.55, 35.50)),
        note="A left lateral fault bounding the eastern Central Anatolian block.",
    ),
    FaultSystem(
        code="HELLENIC", name="Hellenic subduction margin", zone="TR-AEGEAN",
        b_value=1.05, characteristic_magnitude=7.2,
        characteristic_return_per_100km=600.0,
        background_floor=0.10, background_amplitude=1.60, decay_km=70.0,
        trace=((36.20, 27.30), (36.10, 28.40), (36.20, 29.60), (36.40, 30.60)),
        note=(
            "The offshore margin south west of Anatolia, which governs hazard "
            "along the south western coast."
        ),
    ),
)

ZONE_NAMES = {
    "TR-NAF": "the North Anatolian Fault belt",
    "TR-EAST": "the East Anatolian Fault",
    "TR-AEGEAN": "western Anatolia and the Aegean",
    "TR-CENTRAL": "the Central Anatolian interior",
    "TR-EASTHIGH": "the Bitlis and Van thrust belt",
}

# A point further than this from every mapped trace has no system dominating it.
# It still has seismicity, drawn from whatever reaches it, but attributing it to
# a fault ninety kilometres away would overstate what is known about it.
INTERIOR_DISTANCE_KM = 90.0
INTERIOR_B_VALUE = 0.95
INTERIOR_BACKGROUND = 0.03


@dataclass(frozen=True, slots=True)
class Site:
    """Everything the hazard model needs about one coordinate."""

    latitude: float
    longitude: float
    zone: str
    zone_name: str
    b_value: float
    background_rate: float          # annual rate at or above the anchor magnitude
    nearest: FaultSystem | None
    nearest_distance_km: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude": round(self.latitude, 4),
            "longitude": round(self.longitude, 4),
            "zone": self.zone,
            "zone_name": self.zone_name,
            "background_rate": round(self.background_rate, 4),
            "nearest_fault": self.nearest.name if self.nearest else None,
            "nearest_fault_km": round(self.nearest_distance_km, 1),
            "characteristic_magnitude": (
                self.nearest.characteristic_magnitude if self.nearest else None
            ),
            "fault_note": self.nearest.note if self.nearest else None,
        }


# The geometry is pure and is asked the same questions thousands of times: every
# block of the simulated chain, every trial of a pricing run, every point of a
# hazard table. Caching it turns a measurable cost into none, and the inputs are
# rounded first so that coordinates a few metres apart share an answer rather
# than each paying for their own.
@lru_cache(maxsize=8192)
def _site_cached(latitude: float, longitude: float) -> Site:
    """The hazard surface, evaluated at one coordinate.

    Background seismicity is the sum of every system's contribution, each
    decaying with distance from its own trace, on a floor that represents
    activity belonging to no mapped system. Summing rather than taking the
    nearest matters where two systems converge, which around the Marmara and
    the Aegean is exactly where people live.
    """
    point = (latitude, longitude)
    contributions: list[tuple[float, FaultSystem]] = []
    total = 0.0
    for system in FAULT_SYSTEMS:
        distance = system.distance_km(point)
        contributions.append((distance, system))
        total += system.background_amplitude * math.exp(-distance / system.decay_km)

    # The system a site belongs to is the one contributing most of its
    # seismicity, which near converging systems is not always the nearest line.
    weighted = [
        (system.background_amplitude * math.exp(-distance / system.decay_km),
         distance, system)
        for distance, system in contributions
    ]
    _, distance, nearest = max(weighted, key=lambda item: item[0])
    if distance > INTERIOR_DISTANCE_KM:
        return Site(
            latitude=latitude, longitude=longitude,
            zone="TR-INTERIOR", zone_name="no dominant nearby fault",
            b_value=INTERIOR_B_VALUE,
            background_rate=INTERIOR_BACKGROUND + total,
            nearest=None, nearest_distance_km=distance,
        )

    return Site(
        latitude=latitude, longitude=longitude,
        zone=nearest.zone, zone_name=ZONE_NAMES.get(nearest.zone, nearest.zone),
        b_value=nearest.b_value,
        background_rate=nearest.background_floor + total,
        nearest=nearest, nearest_distance_km=distance,
    )


def site_at(latitude: float, longitude: float) -> Site:
    """The hazard surface at a coordinate, to about ten metres."""
    return _site_cached(round(float(latitude), 4), round(float(longitude), 4))


@lru_cache(maxsize=8192)
def _characteristic_cached(
    latitude: float, longitude: float, radius_km: float
) -> tuple[float, tuple[tuple[str, float], ...]]:
    """The annual rate of a system's own large event inside a policy circle.

    Scaled by the length of trace the circle contains, so widening the radius
    buys a continuously larger share of the fault rather than flipping a switch.
    Returned alongside the per system breakdown, because a buyer near two
    systems deserves to see both.
    """
    centre = (latitude, longitude)
    breakdown: dict[str, float] = {}
    total = 0.0
    for system in FAULT_SYSTEMS:
        length = system.weighted_length_inside(centre, radius_km)
        if length <= 0:
            continue
        rate = (length / 100.0) / system.characteristic_return_per_100km
        breakdown[system.code] = rate
        total += rate
    return total, tuple(sorted(breakdown.items()))


def characteristic_rate_at(
    latitude: float, longitude: float, radius_km: float
) -> tuple[float, dict[str, float]]:
    """The rate of a large event inside a circle, and which systems supply it."""
    total, pairs = _characteristic_cached(
        round(float(latitude), 4), round(float(longitude), 4), float(radius_km)
    )
    return total, dict(pairs)


@lru_cache(maxsize=8192)
def dominant_magnitude(latitude: float, longitude: float, radius_km: float) -> float | None:
    """The characteristic magnitude that matters most inside this circle."""
    centre = (latitude, longitude)
    best: tuple[float, float] | None = None
    for system in FAULT_SYSTEMS:
        length = system.weighted_length_inside(centre, radius_km)
        if length <= 0:
            continue
        rate = (length / 100.0) / system.characteristic_return_per_100km
        if best is None or rate > best[0]:
            best = (rate, system.characteristic_magnitude)
    return best[1] if best else None


# Turkey's bounding box, used only to refuse a coordinate this model has nothing
# to say about rather than quietly extrapolating into the sea.
BOUNDS = {"south": 35.7, "north": 42.2, "west": 25.6, "east": 45.0}


def inside_covered_area(latitude: float, longitude: float) -> bool:
    return (
        BOUNDS["south"] <= latitude <= BOUNDS["north"]
        and BOUNDS["west"] <= longitude <= BOUNDS["east"]
    )
