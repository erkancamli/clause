"""Event based simulation of the whole book.

Pricing one policy on its own needs only its own probability model. Deciding
how much capital stands behind a book needs something else, because losses
arrive together. One earthquake pays every policy inside its circle at once.
One dry season pays every farm around the station at once. A pool sized against
the sum of independent risks is sized against a world that does not exist.

So the portfolio is simulated the way catastrophe models are: draw events, not
losses. Each trial draws a state of the world, and every policy is settled
against the same draw. Correlation falls out of the shared events rather than
being asserted through a matrix.

Why the world is drawn separately from the book
-----------------------------------------------
The state of the world does not depend on who bought insurance, so it is drawn
once and kept. A policy is then settled against those fixed draws, and its
idiosyncratic randomness comes from a stream seeded by its own identifier. Two
consequences matter:

  A quote settles one policy against the cached draws instead of resimulating
  the book, which is the difference between an answer in milliseconds and one
  the buyer waits for.

  Adding a policy cannot disturb any other policy's draws, so the difference
  between the book with it and without it is the policy itself rather than
  simulation noise. Estimating a marginal capital charge is hopeless otherwise:
  the quantity being measured is far smaller than the error between two
  independent runs.

What is shared, and what is not
-------------------------------
Earthquake. The fault rupture is one event: if it happens, every policy whose
radius reaches that fault responds together, at the same magnitude. This is the
dominant source of tail correlation and it is modelled exactly. Background
seismicity is drawn per location, so policies at the same place share it and
policies in different cities do not. Two sites forty kilometres apart would in
truth share some background events, which this treats as independent. The
understatement is small because background events rarely reach the payout
thresholds, and it is stated here rather than left to be discovered.

Drought. Seasonal rainfall is drawn for every station through a Gaussian copula
with a single regional factor, so each station keeps exactly the gamma it was
fitted to while a dry year across the region shows up as a dry year almost
everywhere.

Flight. Near independent, with a carrier level disruption factor so a day of
closed airspace is not priced as thousands of unrelated coincidences.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ..mathx import gamma_quantile, normal_cdf
from ..perils import DROUGHT, EARTHQUAKE, FLIGHT_DELAY, PayoutCurve
from ..perils.flight import CANCELLATION_MINUTES, ROUTES, _LOG_SIGMA
from ..perils.geo import FAULT_SYSTEMS, distance_km
from ..perils.quake import ANCHOR_MAGNITUDE, BACKGROUND_MAXIMUM, LOCATIONS, ZONES
from ..perils.weather import STATIONS

# Points in the tabulated gamma inverse. Enough that interpolation error is
# invisible next to the model's own uncertainty, few enough to be free.
_QUANTILE_GRID = 512

# Correlation of seasonal rainfall between any two stations in the region,
# carried by a single common factor. Conservative: published station pair
# correlations over a season commonly sit above this.
REGIONAL_RAINFALL_CORRELATION = 0.45

# Share of flight delay variance coming from a carrier wide disruption rather
# than from the individual flight.
CARRIER_SHOCK_WEIGHT = 0.25

# Reference radius the per location background rate is quoted for.
REFERENCE_RADIUS_KM = 50.0

# Outside Türkiye, events at or above this magnitude are drawn once per country
# and shared by every policy; the smaller ones are drawn per place. The default
# cover first pays at 5.5, so everything that pays under it is shared.
GRID_SHARED_MAGNITUDE = 5.5


@dataclass(frozen=True, slots=True)
class Exposure:
    """One policy, as the capital model sees it."""

    policy_id: str
    peril_key: str
    subject: dict[str, Any]
    curve: PayoutCurve
    limit: float
    term_days: float

    def __post_init__(self) -> None:
        """Normalise the subject here, so nothing downstream has to wonder.

        An exposure is built in several places and settled in one. Validating on
        the way in means the settlement code can rely on a subject's shape
        rather than accepting whichever form its caller happened to hold, which
        is how a place name reached a function expecting a coordinate.
        """
        from ..perils import get_peril

        object.__setattr__(
            self, "subject", get_peril(self.peril_key).validate_subject(self.subject)
        )

    @property
    def term_years(self) -> float:
        return self.term_days / 365.25


# ---------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WorldDraws:
    """States of the world, drawn once and shared by every policy."""

    trials: int
    years: float
    seed: int
    # Where the large events happened, per trial: a list of (latitude,
    # longitude, magnitude) per system. A rupture is somewhere on a trace rather
    # than everywhere on it, so two policies three hundred kilometres apart on
    # the same fault are not settled by one event, and two in the same city are.
    ruptures: dict[str, list[list[tuple[float, float, float]]]]
    # The copula's uniforms, one per station per trial. Cheap to draw and cheap
    # to hold. Turning a uniform into millimetres means inverting a gamma, which
    # is not cheap, so it is done for the stations a book actually contains
    # rather than for all of them. The uniforms are the shared world; the
    # conversion is deterministic, so common random numbers are unaffected.
    rain_uniform: dict[str, list[float]]
    carrier_shock: dict[str, list[float]]
    _rainfall_cache: dict[str, list[float]] = field(default_factory=dict)
    # Outside Türkiye: shared events drawn from a country's gridded model the
    # first time a book holds cover there, bucketed by whole degree so a policy
    # only looks at events near it.
    _grid_events: dict[str, dict[tuple[int, int], list[tuple[int, float, float, float]]]] = field(
        default_factory=dict
    )

    def shared_normals(self, name: str) -> list[float]:
        """One standard normal per trial, drawn once per world and shared."""
        cached = self._grid_events.get(f"__normals:{name}")
        if cached is None:
            rng = random.Random(f"{self.seed}:normals:{name}")
            cached = [rng.gauss(0.0, 1.0) for _ in range(self.trials)]
            self._grid_events[f"__normals:{name}"] = cached  # type: ignore[assignment]
        return cached  # type: ignore[return-value]

    def grid_events(self, model: Any) -> dict[tuple[int, int], list[tuple[int, float, float, float]]]:
        """Every event of magnitude GRID_SHARED_MAGNITUDE or more in one country.

        One draw per country, seeded by the world and the country, so every
        policy there settles against the same earthquakes: two covers in Tokyo
        pay on the same event, and cover in Osaka pays on it only if it falls
        inside Osaka's circle too. The draw does not depend on what the book
        holds, so adding a policy never changes another policy's world.
        """
        cached = self._grid_events.get(model.code)
        if cached is not None:
            return cached
        import bisect

        rng = random.Random(f"{self.seed}:grid:{model.code}")
        cumulative: list[float] = []
        running = 0.0
        for rate in model.rates:
            running += rate
            cumulative.append(running)
        share = model.share_at_or_above(GRID_SHARED_MAGNITUDE)
        expected = running * share * self.years
        b, top = model.b_value, model.max_magnitude
        span = pow(10.0, -b * (top - GRID_SHARED_MAGNITUDE))
        buckets: dict[tuple[int, int], list[tuple[int, float, float, float]]] = {}
        if running <= 0 or expected <= 0:
            self._grid_events[model.code] = buckets
            return buckets
        half = model.step / 2.0
        for trial in range(self.trials):
            for _ in range(_poisson_draw(rng, expected)):
                cell = bisect.bisect_left(cumulative, rng.random() * running)
                cell = min(cell, len(cumulative) - 1)
                row, col = divmod(cell, model.cols)
                lat = model.south + row * model.step + (rng.random() * 2 - 1) * half
                lon = model.west + col * model.step + (rng.random() * 2 - 1) * half
                magnitude = GRID_SHARED_MAGNITUDE - math.log10(1.0 - rng.random() * (1.0 - span)) / b
                buckets.setdefault((math.floor(lat), math.floor(lon)), []).append(
                    (trial, lat, lon, magnitude)
                )
        self._grid_events[model.code] = buckets
        return buckets

    def rainfall(self, code: str) -> list[float]:
        """Season totals in millimetres for one station, computed on demand.

        Inverting a gamma is root finding, and doing it twenty thousand times
        per station would dominate the cost of a quote. Instead the inverse is
        tabulated once on a grid that is dense where the distribution moves
        fastest, and the trials are interpolated onto it. The error against a
        direct inversion is far below a millimetre of rain, which is well inside
        the precision the rest of the model claims.
        """
        cached = self._rainfall_cache.get(code)
        if cached is not None:
            return cached

        station = STATIONS[code]
        grid: list[float] = []
        # Dense in both tails, where a season's total actually decides a payout.
        for index in range(_QUANTILE_GRID + 1):
            fraction = index / _QUANTILE_GRID
            # A smooth stretch towards both ends, so the low tail that drought
            # cover settles on is resolved finely.
            grid.append(0.5 * (1.0 - math.cos(math.pi * fraction)))
        probabilities = [min(max(value, 1e-9), 1.0 - 1e-9) for value in grid]
        table = [
            gamma_quantile(p, station.shape, station.scale) for p in probabilities
        ]

        series: list[float] = []
        for uniform in self.rain_uniform[code]:
            # Invert the same stretch the grid was built with, so a probability
            # lands on the grid position that actually holds it.
            position = (
                math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * uniform))) / math.pi
            ) * _QUANTILE_GRID
            lower = int(position)
            if lower >= _QUANTILE_GRID:
                series.append(table[-1])
                continue
            weight = position - lower
            series.append(table[lower] + (table[lower + 1] - table[lower]) * weight)

        self._rainfall_cache[code] = series
        return series

    @classmethod
    def draw(cls, *, trials: int, years: float, seed: int) -> "WorldDraws":
        if trials <= 0:
            raise ValueError("trials must be positive")
        if years <= 0:
            raise ValueError("the horizon must be positive")

        rng = random.Random(seed)

        # Large events, placed along each system's trace. Sampling a position
        # rather than a yes or no is what makes correlation geographic: policies
        # near the same stretch settle together, and policies at opposite ends
        # of the same fault do not.
        ruptures: dict[str, list[list[tuple[float, float, float]]]] = {}
        for system in FAULT_SYSTEMS:
            # Cumulative weighted length along the trace, so a stretch late in
            # its cycle is proportionally more likely to be the one that goes.
            spans: list[tuple[float, float, int]] = []
            running = 0.0
            for index in range(len(system.trace) - 1):
                length = distance_km(system.trace[index], system.trace[index + 1])
                weight = length * system.segment_factor(index)
                spans.append((running, running + weight, index))
                running += weight
            if running <= 0:
                ruptures[system.code] = [[] for _ in range(trials)]
                continue

            rate = (running / 100.0) / system.characteristic_return_per_100km
            expected = rate * years
            series: list[list[tuple[float, float, float]]] = []
            for _ in range(trials):
                events: list[tuple[float, float, float]] = []
                for _ in range(_poisson_draw(rng, expected)):
                    target = rng.random() * running
                    for start, end, index in spans:
                        if start <= target < end:
                            fraction = (target - start) / (end - start)
                            a = system.trace[index]
                            b = system.trace[index + 1]
                            events.append((
                                a[0] + (b[0] - a[0]) * fraction,
                                a[1] + (b[1] - a[1]) * fraction,
                                system.characteristic_magnitude,
                            ))
                            break
                series.append(events)
            ruptures[system.code] = series

        # Seasonal rainfall for every station at once, through the copula. A dry
        # year is dry across a region, which is the correlation that makes a
        # book of drought cover expensive to stand behind.
        loading = math.sqrt(REGIONAL_RAINFALL_CORRELATION)
        residual = math.sqrt(1.0 - REGIONAL_RAINFALL_CORRELATION)
        rain_uniform: dict[str, list[float]] = {code: [] for code in STATIONS}
        for _ in range(trials):
            common = rng.gauss(0.0, 1.0)
            for code in STATIONS:
                normal = loading * common + residual * rng.gauss(0.0, 1.0)
                rain_uniform[code].append(
                    min(max(normal_cdf(normal), 1e-9), 1.0 - 1e-9)
                )

        # Carrier wide disruption.
        carriers = sorted({stats.carrier for stats in ROUTES.values()})
        carrier_shock = {
            carrier: [rng.gauss(0.0, 1.0) for _ in range(trials)]
            for carrier in carriers
        }

        return cls(
            trials=trials,
            years=years,
            seed=seed,
            ruptures=ruptures,
            rain_uniform=rain_uniform,
            carrier_shock=carrier_shock,
        )


# ---------------------------------------------------------------------------
# Settling one policy against the world
# ---------------------------------------------------------------------------


def settle(exposure: Exposure, draws: WorldDraws) -> list[float]:
    """The loss this policy takes in each trial.

    Idiosyncratic randomness comes from a stream seeded by the policy's own
    identifier, so it is the same whatever else the pool holds.
    """
    own = random.Random(f"{draws.seed}:{exposure.policy_id}")

    if exposure.peril_key == EARTHQUAKE.key:
        return _settle_earthquake(exposure, draws, own)
    if exposure.peril_key == DROUGHT.key:
        return _settle_drought(exposure, draws)
    if exposure.peril_key == FLIGHT_DELAY.key:
        return _settle_flight(exposure, draws, own)
    if exposure.peril_key == "vehicle_flood":
        return _settle_vehicle(exposure, draws)
    raise ValueError(f"no settlement rule for peril {exposure.peril_key!r}")


def _settle_earthquake(
    exposure: Exposure, draws: WorldDraws, own: random.Random
) -> list[float]:
    """The largest magnitude this circle saw, trial by trial.

    Two sources, and they correlate differently. Ruptures come from the shared
    world, placed on the traces, so a book concentrated on one stretch of fault
    settles together; that is the correlation the capital model exists to price.
    Background seismicity is local, so it is drawn per site rather than per
    policy: two covers on the same street see the same small events, and two in
    different provinces do not.
    """
    from ..perils.geo import site_at

    latitude = float(exposure.subject["latitude"])
    longitude = float(exposure.subject["longitude"])
    radius = float(exposure.subject["radius_km"])
    centre = (latitude, longitude)
    grid = EARTHQUAKE.grid_model(exposure.subject)
    if EARTHQUAKE.shaking(exposure.subject):
        return _settle_shaking(exposure, draws, grid, latitude, longitude)
    if grid is not None:
        return _settle_grid_earthquake(exposure, draws, grid, latitude, longitude, radius)
    site = site_at(latitude, longitude)

    # A circle smaller than the reference catches proportionally fewer of the
    # background events the site's rate is quoted for.
    keep = min(1.0, (radius * radius) / (REFERENCE_RADIUS_KM * REFERENCE_RADIUS_KM))

    # Seeded by the place, not the policy, so co-located cover shares its world.
    local = random.Random(f"{draws.seed}:bg:{latitude:.2f}:{longitude:.2f}")
    expected = site.background_rate * draws.years

    losses: list[float] = []
    for trial in range(draws.trials):
        largest = 0.0
        for _ in range(_poisson_draw(local, expected)):
            magnitude = _truncated_gr_magnitude(local, site.b_value)
            if (keep >= 1.0 or own.random() <= keep) and magnitude > largest:
                largest = magnitude

        for series in draws.ruptures.values():
            for event_lat, event_lon, magnitude in series[trial]:
                if magnitude > largest and distance_km(
                    (event_lat, event_lon), centre
                ) <= radius:
                    largest = magnitude

        losses.append(exposure.curve.payout(largest, exposure.limit))
    return losses


def _settle_grid_earthquake(
    exposure: Exposure, draws: WorldDraws, model: Any,
    latitude: float, longitude: float, radius: float,
) -> list[float]:
    """The same question, answered from a country's catalogue model.

    Events that can pay the default cover come from the shared country draw.
    Smaller ones, from the reference magnitude up to the shared threshold, are
    drawn per place, as the background is in Türkiye: they matter only to
    cover that pays below 5.5, and they are local anyway.
    """
    trials = draws.trials
    largest = [0.0] * trials

    small_rate = (
        model.rate_within(latitude, longitude, radius, model.reference)
        - model.rate_within(latitude, longitude, radius, GRID_SHARED_MAGNITUDE)
    )
    if small_rate > 0:
        local = random.Random(f"{draws.seed}:grid-bg:{latitude:.2f}:{longitude:.2f}:{radius:g}")
        b = model.b_value
        span = pow(10.0, -b * (GRID_SHARED_MAGNITUDE - model.reference))
        expected = small_rate * draws.years
        for trial in range(trials):
            for _ in range(_poisson_draw(local, expected)):
                magnitude = model.reference - math.log10(1.0 - local.random() * (1.0 - span)) / b
                if magnitude > largest[trial]:
                    largest[trial] = magnitude

    buckets = draws.grid_events(model)
    dlat = radius / 111.195
    dlon = radius / max(1e-6, 111.195 * math.cos(math.radians(latitude)))
    centre = (latitude, longitude)
    for ilat in range(math.floor(latitude - dlat), math.floor(latitude + dlat) + 1):
        for ilon in range(math.floor(longitude - dlon), math.floor(longitude + dlon) + 1):
            for trial, event_lat, event_lon, magnitude in buckets.get((ilat, ilon), ()):
                if magnitude > largest[trial] and distance_km((event_lat, event_lon), centre) <= radius:
                    largest[trial] = magnitude

    return [exposure.curve.payout(value, exposure.limit) for value in largest]


SHAKING_REACH_KM = 300.0


def _settle_shaking(
    exposure: Exposure, draws: WorldDraws, grid: Any, latitude: float, longitude: float,
) -> list[float]:
    """The strongest shaking at the address, trial by trial.

    Large events come from the shared world, the same ones every other policy
    in the country settles against, and are turned into shaking here with the
    intensity equation and its scatter: two houses on the same street feel the
    same earthquake a little differently, and a house 200 km away feels it
    much less. The small, local part of the hazard is drawn per address.
    """
    from ..perils import shaking as sh

    subject = {"latitude": latitude, "longitude": longitude}
    own = random.Random(f"{draws.seed}:shake:{exposure.policy_id}")
    local = random.Random(f"{draws.seed}:shake-bg:{latitude:.2f}:{longitude:.2f}")
    trials = draws.trials
    strongest = [0.0] * trials
    centre = (latitude, longitude)

    shared: list[tuple[int, float, float]] = []    # trial, distance, magnitude
    if grid is not None:
        buckets = draws.grid_events(grid)
        dlat = SHAKING_REACH_KM / 111.195
        dlon = SHAKING_REACH_KM / max(1e-6, 111.195 * math.cos(math.radians(latitude)))
        for ilat in range(math.floor(latitude - dlat), math.floor(latitude + dlat) + 1):
            for ilon in range(math.floor(longitude - dlon), math.floor(longitude + dlon) + 1):
                for trial, lat, lon, magnitude in buckets.get((ilat, ilon), ()):
                    d = distance_km((lat, lon), centre)
                    if d <= SHAKING_REACH_KM:
                        shared.append((trial, d, magnitude))
        local_part, below = "all", GRID_SHARED_MAGNITUDE
    else:
        for series in draws.ruptures.values():
            for trial in range(trials):
                for lat, lon, magnitude in series[trial]:
                    d = distance_km((lat, lon), centre)
                    if d <= SHAKING_REACH_KM:
                        shared.append((trial, d, magnitude))
        local_part, below = "background", None

    for trial, d, magnitude in shared:
        value = sh.mmi(magnitude, d) + own.gauss(0.0, sh.IPE_SIGMA)
        if value > strongest[trial]:
            strongest[trial] = value
    for trial in range(trials):
        for value in sh.draw(local, subject, local_part, magnitude_below=below):
            if value > strongest[trial]:
                strongest[trial] = value

    return [exposure.curve.payout(value, exposure.limit) for value in strongest]


# Extreme rainfall days are regional: one storm system floods several provinces
# in the same year. A shared factor per trial carries that, so a book of car
# covers across the Black Sea coast settles together the way it would.
RAIN_EXTREME_CORRELATION = 0.35


def _settle_vehicle(exposure: Exposure, draws: WorldDraws) -> list[float]:
    from ..perils.vehicle import nearest

    place, _ = nearest(float(exposure.subject["latitude"]), float(exposure.subject["longitude"]))
    if place is None:
        return [0.0] * draws.trials
    common = draws.shared_normals("rain-extreme")
    local = random.Random(f"{draws.seed}:rainx:{place['name']}")
    loading = math.sqrt(RAIN_EXTREME_CORRELATION)
    residual = math.sqrt(1.0 - RAIN_EXTREME_CORRELATION)
    mu, beta = place["gumbel"]["mu"], place["gumbel"]["beta"]
    years = exposure.term_years
    losses = []
    for trial in range(draws.trials):
        u = min(max(normal_cdf(loading * common[trial] + residual * local.gauss(0.0, 1.0)), 1e-12), 1 - 1e-12)
        # The largest day over the term: the annual maximum's distribution,
        # raised to the term's share of a year.
        u_term = u ** (1.0 / max(years, 1e-6))
        largest = mu - beta * math.log(-math.log(u_term))
        losses.append(exposure.curve.payout(largest, exposure.limit))
    return losses


def _settle_drought(exposure: Exposure, draws: WorldDraws) -> list[float]:
    code = exposure.subject["station"]
    curve = DROUGHT.curve_in_mm(exposure.subject, exposure.curve)
    series = draws.rainfall(code)
    return [curve.payout(series[trial], exposure.limit) for trial in range(draws.trials)]


def _settle_flight(
    exposure: Exposure, draws: WorldDraws, own: random.Random
) -> list[float]:
    stats = FLIGHT_DELAY.statistics(exposure.subject)
    shock = draws.carrier_shock.get(stats.carrier)
    common_weight = math.sqrt(CARRIER_SHOCK_WEIGHT)
    own_weight = math.sqrt(1.0 - CARRIER_SHOCK_WEIGHT)
    log_median = math.log(stats.median_late_minutes)

    losses: list[float] = []
    for trial in range(draws.trials):
        if own.random() < stats.cancellation_rate:
            delay = CANCELLATION_MINUTES
        elif own.random() >= stats.late_rate:
            delay = 0.0
        else:
            z = own_weight * own.gauss(0.0, 1.0)
            if shock is not None:
                z += common_weight * shock[trial]
            delay = math.exp(log_median + _LOG_SIGMA * z)
        losses.append(exposure.curve.payout(delay, exposure.limit))
    return losses


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SimulationResult:
    """Aggregate losses across trials."""

    losses: list[float]
    trials: int
    by_peril: dict[str, list[float]] = field(default_factory=dict)
    _ordered: list[float] | None = field(default=None, repr=False)

    def sorted_losses(self) -> list[float]:
        if self._ordered is None:
            self._ordered = sorted(self.losses)
        return self._ordered

    def mean(self) -> float:
        return sum(self.losses) / len(self.losses) if self.losses else 0.0

    def value_at_risk(self, level: float) -> float:
        """The loss exceeded with probability one minus the level."""
        ordered = self.sorted_losses()
        if not ordered:
            return 0.0
        index = min(len(ordered) - 1, max(0, math.ceil(level * len(ordered)) - 1))
        return ordered[index]

    def tail_value_at_risk(self, level: float) -> float:
        """The average loss in the tail beyond the value at risk.

        Preferred to the value at risk itself because it notices how bad the
        bad cases are rather than only where they start, which for a book with
        one dominant catastrophe is the whole question.
        """
        ordered = self.sorted_losses()
        if not ordered:
            return 0.0
        cutoff = min(len(ordered) - 1, max(0, math.ceil(level * len(ordered)) - 1))
        tail = ordered[cutoff:]
        return sum(tail) / len(tail) if tail else ordered[-1]

    def probability_of_loss_above(self, amount: float) -> float:
        if not self.losses:
            return 0.0
        return sum(1 for loss in self.losses if loss > amount) / len(self.losses)

    def exceedance_curve(self, points: int = 24) -> list[dict[str, float]]:
        """Loss against the chance of exceeding it, for the pool's risk view."""
        ordered = self.sorted_losses()
        if not ordered:
            return []
        rows: list[dict[str, float]] = []
        for step in range(points):
            probability = 0.5 ** (step * 10.0 / points)
            probability = max(1.0 / len(ordered), min(1.0, probability))
            index = max(0, min(len(ordered) - 1, int((1.0 - probability) * len(ordered))))
            rows.append(
                {
                    "exceedance_probability": probability,
                    "return_period_years": 1.0 / probability,
                    "loss": ordered[index],
                }
            )
        return rows


class PortfolioSimulator:
    """Settles a book against a shared set of world draws."""

    def __init__(
        self,
        exposures: Sequence[Exposure],
        *,
        draws: WorldDraws | None = None,
        trials: int = 20_000,
        seed: int = 20260917,
    ) -> None:
        self.exposures = list(exposures)
        horizon = max((e.term_years for e in self.exposures), default=1.0)
        self.draws = draws or WorldDraws.draw(trials=trials, years=horizon, seed=seed)

    def simulate(self) -> SimulationResult:
        trials = self.draws.trials
        total = [0.0] * trials
        by_peril: dict[str, list[float]] = {}

        for exposure in self.exposures:
            losses = settle(exposure, self.draws)
            bucket = by_peril.setdefault(exposure.peril_key, [0.0] * trials)
            for index, amount in enumerate(losses):
                total[index] += amount
                bucket[index] += amount

        return SimulationResult(losses=total, trials=trials, by_peril=by_peril)


# ---------------------------------------------------------------------------
# Draw helpers
# ---------------------------------------------------------------------------


def _poisson_draw(rng: random.Random, mean: float) -> int:
    """A Poisson count, by Knuth's method for small means.

    Every rate in this protocol is far below the point where the method loses
    its footing, and writing it out keeps the simulation dependency free.
    """
    if mean <= 0:
        return 0
    if mean > 30:
        return max(0, int(round(rng.gauss(mean, math.sqrt(mean)))))

    limit = math.exp(-mean)
    count = 0
    product = rng.random()
    while product > limit:
        count += 1
        product *= rng.random()
        if count > 1000:
            break
    return count


def _truncated_gr_magnitude(rng: random.Random, b: float) -> float:
    """A magnitude from the truncated Gutenberg and Richter distribution.

    Inverting the truncated exponential in magnitude, between the catalogue
    anchor and the point where background gives way to the mapped fault.
    """
    span = pow(10.0, -b * (BACKGROUND_MAXIMUM - ANCHOR_MAGNITUDE))
    uniform = rng.random()
    return ANCHOR_MAGNITUDE - math.log10(1.0 - uniform * (1.0 - span)) / b


def exposures_from(records: Iterable[Any]) -> list[Exposure]:
    """Build exposures from anything carrying the right attributes."""
    return [
        Exposure(
            policy_id=record.policy_id,
            peril_key=record.peril_key,
            subject=dict(record.subject),
            curve=record.curve,
            limit=float(record.limit),
            term_days=float(record.term_days),
        )
        for record in records
    ]
