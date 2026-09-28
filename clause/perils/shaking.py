"""Shaking at the address, as an alternative to magnitude inside a circle.

Magnitude inside a radius is simple to state and wrong in both directions: a
magnitude 6 at the edge of a 100 km circle can pay a house that barely felt it,
and a magnitude 5.4 under the house pays nothing. What damages a building is
how hard the ground shook where it stands. Parametric earthquake products that
reached real buyers (Jumpstart in California, Bounce in New Zealand, Sompo's in
Japan) pay on that: the intensity at the insured address.

The index here is the modified Mercalli intensity (MMI) at the address, as
the seismic networks publish it in their shaking maps (USGS ShakeMap, AFAD,
JMA). VI is strong shaking and light damage; VII very strong, damage to poorly
built structures; VIII severe.

How it is priced
----------------
The same rate model that prices magnitude in a circle is turned into shaking at
a point. Around the address, rings out to 300 km; within each ring, magnitude
bands of a tenth. The rate of events in each ring and band is the difference of
the peril's own rates for nested circles and thresholds, so the Türkiye fault
model and the catalogue models elsewhere are used exactly as they are. Each
ring and band then shakes the address with a probability given by an
intensity prediction equation with its scatter:

    Allen, Wald and Worden (2012), global, hypocentral distance:
      MMI = 2.085 + 1.428 M - 1.402 ln( sqrt(R^2 + (1 + 0.078 exp(M - 5))^2) )
            - 0.209 ln(R / 50)   for R > 50 km
      with a standard deviation of about 0.7 intensity units.

Depth is taken as 10 km. The equation is global, and a global equation has no
site term: it cannot know the ground under the house.

Where a country publishes its own probabilistic hazard model, that model does
know, and it is the figure its own regulator prices against. Japan's J-SHIS and
the United States Geological Survey both publish a hazard curve at a point, and
``clause.hazard.published`` fetches them offline. Where one covers the address,
the difference between it and ours is read off as a site term in intensity
units and carried by every event. The events stay as they were; the ground under
the address becomes theirs.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from functools import lru_cache
from typing import Any, Callable

from ..mathx import normal_cdf

IPE_SIGMA = 0.7
DEPTH_KM = 10.0
# Ring edges, km. Finer near the address, where most of the shaking comes from.
RINGS = (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 65.0, 80.0, 100.0,
         125.0, 150.0, 200.0, 250.0, 300.0)
MAGNITUDES = tuple(round(5.0 + 0.1 * i, 1) for i in range(41))   # 5.0 .. 9.0
LEVELS = (5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0)


def mmi(magnitude: float, distance_km: float) -> float:
    """Median intensity at an epicentral distance, Allen Wald and Worden 2012."""
    r = math.sqrt(distance_km * distance_km + DEPTH_KM * DEPTH_KM)
    near = 1.0 + 0.078 * math.exp(magnitude - 5.0)
    value = 2.085 + 1.428 * magnitude - 1.402 * math.log(math.sqrt(r * r + near * near))
    if r > 50.0:
        value -= 0.209 * math.log(r / 50.0)
    return value


def p_at_least(level: float, magnitude: float, distance_km: float) -> float:
    """Probability the address shakes at or above a level, given one event."""
    return 1.0 - normal_cdf((level - mmi(magnitude, distance_km)) / IPE_SIGMA)


def _density(rate: Callable[[float, float], float]) -> list[tuple[float, float, float]]:
    """(magnitude, distance, annual rate) for every ring and band around a point.

    ``rate(radius, magnitude)`` is the annual rate of events at or above the
    magnitude inside the circle; ring and band rates are its differences.
    """
    table = [[rate(r, m) if r > 0 else 0.0 for m in MAGNITUDES] for r in RINGS]
    out = []
    for j in range(1, len(RINGS)):
        mid_r = 0.5 * (RINGS[j - 1] + RINGS[j])
        for i, m in enumerate(MAGNITUDES):
            upper = table[j][i + 1] if i + 1 < len(MAGNITUDES) else 0.0
            lower = table[j - 1][i + 1] if (i + 1 < len(MAGNITUDES) and j - 1 > 0) else 0.0
            here = (table[j][i] - upper) - ((table[j - 1][i] if j - 1 > 0 else 0.0) - lower)
            if here > 1e-12:
                out.append((m + 0.05, mid_r, here))
    return out


@lru_cache(maxsize=512)
def _site(latitude: float, longitude: float, part: str) -> tuple[tuple[float, float, float], ...]:
    from . import EARTHQUAKE

    def rate(radius: float, magnitude: float) -> float:
        subject = {"latitude": latitude, "longitude": longitude, "radius_km": radius}
        if part == "background":
            return EARTHQUAKE.background_rate(subject, magnitude)
        return EARTHQUAKE.local_rate(subject, magnitude)

    return tuple(_density(rate))


def density(subject: dict[str, Any], part: str = "all") -> tuple[tuple[float, float, float], ...]:
    return _site(round(float(subject["latitude"]), 4), round(float(subject["longitude"]), 4), part)


def raw_rate_at_least(subject: dict[str, Any], level: float, part: str = "all") -> float:
    """Annual rate of shaking at or above a level, from our rates and the IPE alone."""
    return sum(r * p_at_least(level, m, d) for m, d, r in density(subject, part))


# ---------------------------------------------------------------------------
# What the national model says about this address
# ---------------------------------------------------------------------------
#
# The equation above is global and has no site term: it knows the magnitude and
# the distance and nothing about the ground the house stands on, the basin under
# it, or the fault that a catalogue since 1973 has not yet seen rupture. Where a
# country publishes its own probabilistic hazard model, that model knows all
# three, and it is the figure its own regulator prices against.
#
# So where a published curve covers the address, the difference between it and
# ours is read off as one number: how many intensity units harder the ground
# there shakes than a global equation with no site term expects. That number is
# then carried by every event, which keeps the events themselves -- their
# magnitudes, their distances, the neighbours they shake at the same moment --
# exactly as they were. Only the ground under the address changes.
#
# The alternative, reading the published curve directly and discarding ours,
# would give the same annual rates and lose the events, and the capital model
# settles neighbours together by event. One number keeps both.

#: How far the site term may move an address, in intensity units. Beyond this
#: the two models disagree about more than the ground, and saying so is better
#: than papering over it with an unbounded correction.
SHIFT_LIMIT = 1.5

#: The intensities the fit is made on. A published curve runs from shaking
#: nobody insures against up to shaking off the end of the scale, and a least
#: squares fit over the whole of it is decided by the parts no policy attaches
#: to: New York's term, fitted over everything its curve carries, left a
#: sixteen fold disagreement in the band that is actually priced. This is the
#: band the product quotes, one level either side.
FIT_BAND = (5.0, 10.0)


@lru_cache(maxsize=512)
def _shift(latitude: float, longitude: float) -> tuple[Any, ...] | None:
    """The site term at an address, and how well one number fits their curve."""
    from ..hazard import published as pub

    near = pub.nearest(latitude, longitude)
    if near is None:
        return None
    subject = {"latitude": latitude, "longitude": longitude}
    # Their points, in the band that is priced, and only the ones our own model
    # can reach at all: a level so strong that our rate underflows to zero at
    # every shift is not evidence about the ground, and letting it into a least
    # squares fit in log rate throws the whole fit away.
    theirs = [(level, rate) for level, rate in near["curve"]
              if rate > 0 and FIT_BAND[0] <= level <= FIT_BAND[1]
              and raw_rate_at_least(subject, level - SHIFT_LIMIT) > 0]
    if len(theirs) < 2:
        return None

    def cost(shift: float) -> float:
        total = 0.0
        for level, rate in theirs:
            ours = raw_rate_at_least(subject, level - shift)
            if ours <= 0.0:
                return float("inf")
            total += (math.log(ours) - math.log(rate)) ** 2
        return total

    best, best_cost = 0.0, cost(0.0)
    for step, span in ((0.1, SHIFT_LIMIT), (0.01, 0.1)):
        low, high = best - span, best + span
        x = max(-SHIFT_LIMIT, low)
        while x <= min(SHIFT_LIMIT, high) + 1e-9:
            here = cost(x)
            if here < best_cost:
                best, best_cost = x, here
            x += step
    best = round(best, 3)
    clipped = abs(abs(best) - SHIFT_LIMIT) < 1e-9
    # One number cannot follow a curve of a different shape, and pretending it
    # did would be the sort of thing this whole exercise is against. The worst
    # disagreement left over is carried out with the term.
    worst = 1.0
    for level, rate in theirs:
        ours = raw_rate_at_least(subject, level - best)
        ratio = ours / rate if rate > 0 else 1.0
        worst = max(worst, ratio, 1.0 / ratio if ratio > 0 else 1.0)
    return (best, near["name"], near["distance_km"], near["publisher"],
            clipped, round(worst, 2))


def site_term(subject: dict[str, Any]) -> dict[str, Any] | None:
    """The published model's correction at this address, in a form worth reading."""
    found = _shift(round(float(subject["latitude"]), 4), round(float(subject["longitude"]), 4))
    if found is None:
        return None
    shift, name, km, publisher, clipped, worst = found
    return {"shift": shift, "place": name, "distance_km": km,
            "publisher": publisher, "at_the_limit": clipped, "worst_ratio": worst}


def shift_at(subject: dict[str, Any]) -> float:
    found = _shift(round(float(subject["latitude"]), 4), round(float(subject["longitude"]), 4))
    return found[0] if found is not None else 0.0


def rate_at_least(subject: dict[str, Any], level: float, part: str = "all") -> float:
    """Annual rate of shaking at or above a level at the address."""
    return raw_rate_at_least(subject, level - shift_at(subject), part)


def exceedance(subject: dict[str, Any], term_days: float) -> Callable[[float], float]:
    years = term_days / 365.25
    cache: dict[float, float] = {}

    def probability(level: float) -> float:
        key = round(level, 3)
        if key not in cache:
            cache[key] = 1.0 - math.exp(-rate_at_least(subject, level) * years)
        return cache[key]

    return probability


@lru_cache(maxsize=512)
def _sampler(latitude: float, longitude: float, part: str, magnitude_below: float | None,
             ) -> tuple[float, tuple[float, ...], tuple[tuple[float, float], ...]]:
    """The rate table of one address as a cumulative rate to draw against.

    Built once per address and kept: the capital model draws every trial from
    it, and rebuilding and walking the table twelve thousand times over was
    most of what an earthquake quote on shaking cost.
    """
    rows = [row for row in _site(latitude, longitude, part)
            if magnitude_below is None or row[0] < magnitude_below]
    total, cumulative = 0.0, []
    for _, _, r in rows:
        total += r
        cumulative.append(total)
    return total, tuple(cumulative), tuple((m, d) for m, d, _ in rows)


def draw(rng: Any, subject: dict[str, Any], part: str = "all",
         magnitude_below: float | None = None) -> list[float]:
    """Shaking at the address from events drawn in one year, one value per event.

    Used by the capital model for the part of the hazard that is local to the
    address; large shared events are shaken separately so neighbours settle
    together.
    """
    total, cumulative, events = _sampler(
        round(float(subject["latitude"]), 4), round(float(subject["longitude"]), 4),
        part, magnitude_below)
    if total <= 0:
        return []
    shift = shift_at(subject)
    count = _poisson(rng, total)
    out = []
    last = len(events) - 1
    for _ in range(count):
        # The first row whose cumulative rate reaches the target: the same row
        # a walk down the table found, at the cost of a binary search.
        i = min(bisect_left(cumulative, rng.random() * total), last)
        m, d = events[i]
        out.append(mmi(m, d) + shift + rng.gauss(0.0, IPE_SIGMA))
    return out


def _poisson(rng: Any, mean: float) -> int:
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1
