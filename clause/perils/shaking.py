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
# The first version of this carried the difference as one number, a shift in
# intensity units, fitted by least squares. That works where the two curves have
# the same shape and fails where they do not. Japan publishes four points per
# place over a narrow range and the fit was good; the United States publishes
# twenty over a wide one, and across them our curve had the wrong slope, not
# only the wrong level. A single shift left a median factor of four in New York,
# which is a number nobody should be quoted.
#
# So the difference is carried as a mapping rather than a number: the intensity
# our model would have called x becomes the intensity at which the published
# curve has the same annual rate. That is a quantile map, it is built from the
# two curves and nothing else, and inside the band it is exact by construction.
# Our answer is their answer.
#
# It keeps what the shift kept. The events are still ours, with their
# magnitudes, their distances and the neighbours they shake at the same moment,
# because the map is applied to each event's intensity rather than to the curve
# wholesale. Reading the published curve directly and discarding ours would give
# the same annual rates and lose the events, and the capital model settles
# neighbours together by event.

#: How far the map may move one intensity, in intensity units. Beyond this the
#: two models disagree about more than the ground, and saying so is better than
#: papering over it with an unbounded correction.
#:
#: Two was measured rather than chosen. At one and a half the bound binds on
#: Japan and leaves the quote a third under what J-SHIS publishes, which is the
#: dangerous direction: too little premium rather than too much. At two it stops
#: binding, and nothing above two changes any answer. It was set at one and a
#: half while the conversion from a published velocity to an intensity was the
#: weakest step in the chain; that step is now the publisher's own relation at
#: the publisher's own mesh, checked where the two families of its figures
#: overlap, so following it further is warranted.
SHIFT_LIMIT = 2.0

#: How far the map may still be from the published curve and the address be
#: priced at all. A factor of two in return period, across the band a policy is
#: written at.
#:
#: The map is exact between the published points unless the bound above holds it
#: back, and where it does the gap is not a detail. Niigata is the case that set
#: this: our model gives intensity VII there once in eleven thousand years and
#: J-SHIS gives it once in seventy three, a factor of a hundred and fifty, in a
#: city that was destroyed by an earthquake in 1964. No correction to the level
#: rescues an event model that wrong, and a price seven times light is worse than
#: no price. About one place in nine is refused by this, in both countries.
MOST_DISAGREEMENT = 2.0

#: The intensities the map is built over, and the step it is tabulated at. The
#: band is the one the product quotes with a level either side; below it a
#: published curve describes shaking nobody insures against, and above it our
#: own rates underflow to nothing.
FIT_BAND = (5.0, 10.0)
GRID = tuple(round(3.0 + 0.05 * i, 2) for i in range(181))      # 3.00 .. 12.00


@lru_cache(maxsize=512)
def _raw_curve(latitude: float, longitude: float) -> tuple[float, ...]:
    """Our own exceedance rate at every intensity on the grid."""
    subject = {"latitude": latitude, "longitude": longitude}
    return tuple(raw_rate_at_least(subject, level) for level in GRID)


def _level_at(curve: tuple[float, ...], rate: float) -> float:
    """The intensity at which our own curve reaches an annual rate.

    Straight in log rate between the points of the grid, which is how the
    curve is read everywhere else. Beyond either end it returns the end: a
    rate our model never reaches is not evidence about the ground.
    """
    if rate <= 0:
        return GRID[-1]
    if rate >= curve[0]:
        return GRID[0]
    for i in range(1, len(GRID)):
        here = curve[i]
        if here <= 0 or here <= rate:
            before = curve[i - 1]
            if here <= 0 or before <= 0 or before <= here:
                return GRID[i]
            part = (math.log(before) - math.log(rate)) / (math.log(before) - math.log(here))
            return GRID[i - 1] + part * (GRID[i] - GRID[i - 1])
    return GRID[-1]


@lru_cache(maxsize=512)
def _mapping(latitude: float, longitude: float) -> tuple[Any, ...] | None:
    """The quantile map at an address, both ways, and what it is worth saying.

    ``ours`` is the intensity of ours that carries the published rate at each
    grid level, so a published level is priced by reading our own model there.
    ``theirs`` is the same relation the other way, for the events a draw makes.
    """
    from ..hazard import published as pub

    near = pub.nearest(latitude, longitude)
    if near is None:
        return None
    curve = tuple((level, rate) for level, rate in near["curve"] if rate > 0)
    if len(curve) < 2:
        return None
    mine = _raw_curve(latitude, longitude)

    # Inside the published points the map is theirs. Outside them it is a
    # constant offset, carried from the nearest end: a published curve read
    # below its weakest point is flat, and following that flatness would price
    # intensity VI and intensity VIII at the same frequency. Outside their
    # range the shape stays ours and only the level is corrected, which is what
    # the single shift did everywhere and is the right thing to do here.
    low, high = curve[0][0], curve[-1][0]
    ours: list[float] = []
    at_the_limit = False
    moved_at: dict[float, float] = {}
    for level in GRID:
        if level < low or level > high:
            ours.append(0.0)                      # filled in once the ends are known
            continue
        want = pub.rate_at(curve, level)
        moved = level - _level_at(mine, want)
        if abs(moved) > SHIFT_LIMIT:
            if FIT_BAND[0] <= level <= FIT_BAND[1]:
                at_the_limit = True
            moved = math.copysign(SHIFT_LIMIT, moved)
        moved_at[level] = moved
        ours.append(level - moved)
    if not moved_at:
        return None
    at_low = moved_at[min(moved_at)]
    at_high = moved_at[max(moved_at)]
    for i, level in enumerate(GRID):
        if level < low:
            ours[i] = level - at_low
        elif level > high:
            ours[i] = level - at_high
    # A map that ran backwards would put more hazard at a weaker shaking than a
    # stronger one. Clamping one level can do that, so the result is made to
    # rise: each level reads our curve at least as far along as the one below.
    for i in range(1, len(ours)):
        ours[i] = max(ours[i], ours[i - 1])

    # Exact inside the band, by construction, and the residual is measured
    # rather than assumed because the clamp above can still bind.
    worst = 1.0
    for level, rate in curve:
        if not FIT_BAND[0] <= level <= FIT_BAND[1]:
            continue
        got = _look(mine, _look_at(GRID, tuple(ours), level))
        if got > 0 and rate > 0:
            worst = max(worst, got / rate, rate / got)

    at_seven = round(7.0 - _look_at(GRID, tuple(ours), 7.0), 3)
    return (tuple(ours), near["name"], near["distance_km"], near["publisher"],
            at_the_limit, round(worst, 2), at_seven)


def _look_at(grid: tuple[float, ...], table: tuple[float, ...], x: float) -> float:
    """A table read straight between its points, and sloping one to one past
    either end.

    ``grid`` rises but need not be evenly spaced, which is why the place is
    found by searching rather than by arithmetic on the step: the map read
    forwards is indexed by the even grid of intensities, and read backwards it
    is indexed by its own answers, which are not evenly spaced at all. Dividing
    by a step that only the forward direction has put the inverse in the wrong
    cell, and the capital model then settled a Tokyo policy at a tenth where
    the price assumed a fifth.
    """
    if x <= grid[0]:
        return table[0] + (x - grid[0])
    if x >= grid[-1]:
        return table[-1] + (x - grid[-1])
    i = bisect_left(grid, x)
    if i == 0:
        return table[0]
    span = grid[i] - grid[i - 1]
    if span <= 0:
        return table[i]
    part = (x - grid[i - 1]) / span
    return table[i - 1] + part * (table[i] - table[i - 1])


def _look(curve: tuple[float, ...], level: float) -> float:
    """Our own rate at an intensity, off the same grid the map is built on."""
    if level <= GRID[0]:
        return curve[0]
    if level >= GRID[-1]:
        return curve[-1]
    i = min(int((level - GRID[0]) / 0.05) + 1, len(GRID) - 1)
    before, here = curve[i - 1], curve[i]
    if before <= 0 or here <= 0:
        return here
    part = (level - GRID[i - 1]) / (GRID[i] - GRID[i - 1])
    return math.exp(math.log(before) + part * (math.log(here) - math.log(before)))


def ours_at(subject: dict[str, Any], level: float) -> float:
    """Where to read our own model so it answers the published question."""
    found = _mapping(round(float(subject["latitude"]), 4), round(float(subject["longitude"]), 4))
    if found is None:
        return level
    return _look_at(GRID, found[0], level)


def theirs_at(subject: dict[str, Any], level: float) -> float:
    """The published intensity an event of ours at this intensity really is."""
    found = _mapping(round(float(subject["latitude"]), 4), round(float(subject["longitude"]), 4))
    if found is None:
        return level
    # The same map read the other way. Both sides rise, so one interpolation
    # against the other is the inverse.
    return _look_at(found[0], GRID, level)


def beyond_reconciling(subject: dict[str, Any]) -> bool:
    """Whether the published curve and ours are too far apart to price on.

    False where no published curve covers the address: then there is nothing to
    disagree with and our own model's own backtest is what entitles it.
    """
    found = _mapping(round(float(subject["latitude"]), 4), round(float(subject["longitude"]), 4))
    return found is not None and found[5] > MOST_DISAGREEMENT


def site_term(subject: dict[str, Any]) -> dict[str, Any] | None:
    """The published model's correction at this address, in a form worth reading."""
    found = _mapping(round(float(subject["latitude"]), 4), round(float(subject["longitude"]), 4))
    if found is None:
        return None
    _, name, km, publisher, clipped, worst, at_seven = found
    return {"shift": at_seven, "place": name, "distance_km": km,
            "publisher": publisher, "at_the_limit": clipped, "worst_ratio": worst}


def rate_at_least(subject: dict[str, Any], level: float, part: str = "all") -> float:
    """Annual rate of shaking at or above a level at the address."""
    return raw_rate_at_least(subject, ours_at(subject, level), part)


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
    count = _poisson(rng, total)
    out = []
    last = len(events) - 1
    for _ in range(count):
        # The first row whose cumulative rate reaches the target: the same row
        # a walk down the table found, at the cost of a binary search.
        i = min(bisect_left(cumulative, rng.random() * total), last)
        m, d = events[i]
        out.append(theirs_at(subject, mmi(m, d) + rng.gauss(0.0, IPE_SIGMA)))
    return out


def _poisson(rng: Any, mean: float) -> int:
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1
