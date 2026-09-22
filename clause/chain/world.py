"""A Rialo shaped chain, carrying the policies as reactive transactions.

This is what makes Clause a protocol rather than a spreadsheet. A policy is not
a record in a database that some service watches. It is a predicate registered
onchain at purchase, and the chain itself reads the outside world, evaluates it
and pays.

The block pipeline follows the one Rialo publishes for reactive transactions:

  1. buying a policy registers a predicate and the program to run when it holds
  2. validators attest readings from the outside world through Rialo Edge
  3. those readings touch the dependency keys the predicates were indexed under
  4. at the end of the block, only the predicates whose inputs moved are
     re-evaluated, deterministically
  5. the ones that became true are enqueued
  6. they run, and the payout settles against the pool

Step four is the part worth understanding. The chain does not re-run every
policy every block. It keeps an inverted index from signal to policy, and a new
rainfall reading wakes only the policies that read that station. The same index
is what lets the interface say which policies a given reading is about to move.

Two things here are not cosmetic. Settlement runs on validator attested data,
so no operator stands between the reading and the payout. And a policy whose
data never arrives is expired by a deadline that was written into it at
purchase, rather than left armed forever, which is the failure mode that makes
most parametric designs quietly worse than they look.
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .rex import Aggregation, Aggregator, Agreement, RexReport, RexUpdate, topic_for
from .. import predicate as pred
from ..perils import DROUGHT, EARTHQUAKE, FLIGHT_DELAY
from ..mathx import gamma_quantile
from ..perils.flight import CANCELLATION_MINUTES, ROUTES, _LOG_SIGMA as LOG_SIGMA
from ..perils.places import LEGACY_CODES, find_place
from ..perils.weather import STATIONS
from ..protocol import Policy, PolicyStatus, Pool

import logging

logger = logging.getLogger("clause.chain")

# Rialo targets fifty millisecond blocks.
BLOCK_TIME_SECONDS = 0.05

# How long a triggered policy waits, in the world's own hours, before it pays.
# Seismic networks revise a magnitude or a shaking map in the hours after an
# event, and flight data is corrected after landing; paying on the first figure
# and then learning it was wrong cannot be undone on a chain. Rainfall is read
# only once the season has closed, so it is already final.
CONFIRM_HOURS = {"earthquake": 24.0, "flight_delay": 6.0, "drought": 0.0, "vehicle_flood": 48.0, "storm": 48.0}

# Fields that are states rather than measurements. Validators cannot meaningfully
# disagree about whether a season has closed, so these are not perturbed.
_EXACT_FIELDS = frozenset({"window_closed", "cancelled", "final", "progress_days"})


def _signature(seed: str) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    digest = hashlib.blake2b(seed.encode(), digest_size=32).digest()
    value = int.from_bytes(digest, "big")
    out: list[str] = []
    while value and len(out) < 44:
        value, index = divmod(value, 58)
        out.append(alphabet[index])
    return "".join(reversed(out)).rjust(44, "1")


# ---------------------------------------------------------------------------
# The outside world, as validators see it
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EdgeReading:
    """One attested response from outside the chain.

    A response carries several fields, and a policy usually reads more than one
    of them. A drought cover needs the rainfall total and whether the season has
    actually closed, because a running total that happens to be low in June says
    nothing about the harvest.
    """

    reference: str
    fields: dict[str, Any]
    attested_at: float
    publisher: str
    index_field: str
    final: bool = False
    # A reference that has gone quiet. Set when a source stops publishing, and
    # what the expiry path exists to handle.
    silent: bool = False
    progress_days: float = 0.0
    # Rainfall sources lay their season out in advance; see _start_season.
    season_target: float = 0.0
    season_schedule: list[tuple[float, float]] = field(default_factory=list)
    season_index: int = 0
    # Flight sources carry the route they are reporting on.
    route: str = ""
    # How fast this source's world moves, as a share of the demonstration's
    # acceleration. 1.0 is the demonstration's own pace; a source created for
    # cover a person bought runs at the pace of the clock, so that a year is a
    # year (see Chain.register).
    pace: float = 1.0

    @property
    def key(self) -> str:
        return f"edge:{self.reference}"

    @property
    def value(self) -> Any:
        """The field the policy's index is read from."""
        return self.fields.get(self.index_field)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "fields": dict(self.fields),
            "index_field": self.index_field,
            "value": self.value,
            "attested_at": self.attested_at,
            "publisher": self.publisher,
            "final": self.final,
            "silent": self.silent,
        }


@dataclass(slots=True)
class ArmedPolicy:
    """A policy registered onchain, waiting on its index."""

    policy: Policy
    tree: pred.Node
    keys: frozenset[str]
    registered_block: int
    registered_at: float
    account: str
    condition_block: int | None = None
    # Set after a restart for a policy that had reached its index: the value
    # attested before the restart, which the rebuilt reading does not carry.
    resumed_index: float | None = None

    @property
    def policy_id(self) -> str:
        return self.policy.policy_id


@dataclass(slots=True)
class Settlement:
    """A settlement the chain performed by itself."""

    signature: str
    policy_id: str
    block_number: int
    condition_block: int
    at: float
    kind: str  # paid | lapsed | expired
    index_value: float | None
    amount: float
    summary: str

    @property
    def latency_blocks(self) -> int:
        return max(0, self.block_number - self.condition_block)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "policy_id": self.policy_id,
            "block_number": self.block_number,
            "condition_block": self.condition_block,
            "latency_blocks": self.latency_blocks,
            "at": self.at,
            "kind": self.kind,
            "index_value": self.index_value,
            "amount": round(self.amount, 2),
            "summary": self.summary,
        }


@dataclass(slots=True)
class ChainConfig:
    seed: int = 20260917
    speed: float = 1.0          # simulated seconds per real second
    start_height: int = 412_000
    retain_blocks: int = 20_000
    # How fast the simulated world moves relative to the chain clock. Terms are
    # written in real units, because a policy document that said the season
    # lasts four minutes would be describing something else. The clock outside
    # the chain is what runs fast, so a season, a flight and a settlement
    # deadline all arrive inside a demo. At this setting one block carries
    # about thirty three minutes, so a year of earthquake cover runs for about
    # thirteen minutes of watching and a growing season for six.
    world_acceleration: float = 40_000.0
    # How many validators perform the REX duty, matching Rialo's devnet.
    validators: int = 4
    # How much two validators' answers for the same reading may differ, as a
    # share of the value. Seismic networks routinely publish magnitudes a tenth
    # apart, which is under a percent at magnitude 7.
    measurement_noise: float = 0.004
    # How often a validator returns something badly wrong, from a stale cache or
    # a feed glitch. Rare, and the reason the dispersion guard exists.
    glitch_rate: float = 0.012
    # How often a validator fails to report at all in a round.
    miss_rate: float = 0.02


# The independent, official sources each validator reads for one reading. An
# earthquake is read from two international catalogues and the national
# network of the country it happened in; rainfall from the station's own
# service and a satellite estimate for the same point; a flight from the
# airline, the airport and an independent tracker. Only official publishers
# are listed: a source that could be bought or edited has no place here.
NATIONAL_SEISMIC = {
    "TR": "AFAD", "JP": "JMA", "CL": "CSN", "MX": "SSN", "NZ": "GeoNet", "TW": "CWA",
}


def sources_for(reading: "EdgeReading") -> tuple[str, ...]:
    if reading.index_field == "max_magnitude":
        country = "TR"
        try:
            query = reading.reference.split("?", 1)[1]
            parts = dict(p.split("=", 1) for p in query.split("&"))
            from ..perils import EARTHQUAKE
            country = EARTHQUAKE.risk_country(
                {"latitude": float(parts["lat"]), "longitude": float(parts["lon"])}) or "TR"
        except (IndexError, KeyError, ValueError):
            pass
        return ("USGS", "EMSC", NATIONAL_SEISMIC.get(country, "national network"))
    if reading.index_field == "mmi":
        try:
            query = reading.reference.split("?", 1)[1]
            parts = dict(p.split("=", 1) for p in query.split("&"))
            from ..perils import EARTHQUAKE
            country = EARTHQUAKE.risk_country(
                {"latitude": float(parts["lat"]), "longitude": float(parts["lon"])}) or "TR"
        except (IndexError, KeyError, ValueError):
            country = "TR"
        return ("USGS ShakeMap", NATIONAL_SEISMIC.get(country, "national network"),
                "nearest strong motion station")
    if reading.index_field in ("rain_24h_mm", "wind_24h_kmh"):
        # Observation first: the station is what a person can look up, and a
        # reanalysis under-reads the strong days; the reanalyses stand in.
        return ("national meteorological service station", "NASA POWER (MERRA-2)", "ERA5 reanalysis")
    if reading.index_field == "rainfall_mm":
        return ("national meteorological service", "CHIRPS satellite estimate", "ERA5 reanalysis")
    if reading.index_field == "arrival_delay_minutes":
        return ("airline", "arrival airport", "independent flight tracker")
    return (reading.publisher or "source",)


def terms_fingerprint(policy: Policy) -> str:
    """A hash of everything the policy promises, so a token names its terms."""
    import hashlib
    import json as _json

    terms = {
        "policy_id": policy.policy_id, "peril": policy.peril_key,
        "subject": policy.subject, "limit": round(policy.limit, 2),
        "premium": round(policy.premium, 2), "term_days": policy.term_days,
        "starts_at": round(policy.starts_at), "ends_at": round(policy.ends_at),
        "curve": [[b.level, b.share] for b in policy.curve.breakpoints],
        "predicate": policy.predicate, "holder": policy.holder,
    }
    body = _json.dumps(terms, sort_keys=True, separators=(",", ":"), default=str)
    return "0x" + hashlib.blake2b(body.encode(), digest_size=32).hexdigest()


def mint_token(policy: Policy, height: int, at: float) -> dict[str, Any]:
    return {
        "token_id": policy.policy_id,
        "owner": policy.holder,
        "standard": "non-transferable policy token (ERC-5192 style, locked)",
        "transferable": False,
        "minted_block": height,
        "minted_at": at,
        "terms_hash": terms_fingerprint(policy),
    }


class Chain:
    """The simulated Rialo chain the protocol runs on."""

    def __init__(self, pool: Pool, config: ChainConfig | None = None) -> None:
        self.config = config or ChainConfig()
        self.pool = pool
        self.rng = random.Random(self.config.seed)
        self.lock = threading.RLock()

        self.height = self.config.start_height
        self.genesis = time.time()
        self.timestamp = self.genesis

        # account -> armed policy, and the inverted index from signal to policy
        self.armed: dict[str, ArmedPolicy] = {}
        self.index: dict[str, set[str]] = defaultdict(set)

        self.readings: dict[str, EdgeReading] = {}
        self.settlements: list[Settlement] = []
        # Settlements dropped from the list above, counted so that what the
        # chain reports about itself is the whole of its history even when
        # the demonstration's own record is trimmed (see forget).
        self.forgotten: dict[str, float] = {}
        # Told about every settlement after it is recorded, for notices that
        # leave the protocol (a partner's webhook). A listener that fails is
        # logged; it can never undo a settlement.
        self.listeners: list[Any] = []
        # Told when a policy's token is minted or burned, with the policy.
        self.token_listeners: list[Any] = []

        # Every web call is performed by each validator separately, and what
        # lands on chain is the set of their answers. The aggregator is Clause's
        # own rule for reconciling them, stated in rex.py and in the policy.
        self.aggregator = Aggregator(validators=self.config.validators)
        self.validators = [f"validator-{i}" for i in range(self.config.validators)]
        self.aggregations: deque[Aggregation] = deque(maxlen=200)
        self.rex_round = 0
        self.refused_rounds = 0
        self.blocks: deque[dict[str, Any]] = deque(maxlen=self.config.retain_blocks)
        self.blocks_by_height: dict[int, dict[str, Any]] = {}

        self._pending_registrations: list[dict[str, Any]] = []
        self._newly_armed: set[str] = set()
        # Keys changed from outside the block producer, by an operator or a
        # demonstration. They join the next block's touched set, so a reading
        # written this way wakes exactly the predicates a natural one would.
        self._pending_touches: set[str] = set()
        # Run before any payout leaves: the compliance rules as they stand
        # now (a licence can lapse, a company be suspended, while a policy
        # runs). Returns a reason to refuse, or None. Set by the API.
        self.settlement_check: Callable[[Policy], str | None] | None = None
        self._queue: list[tuple[int, ArmedPolicy, float]] = []
        self._evaluations = 0
        self._nonce = 0
        self._running = False
        self._thread: threading.Thread | None = None

        self._install_sources()

    # -- the outside world ------------------------------------------------

    def _install_sources(self) -> None:
        """Seed every source the offered perils can read."""
        now = self.timestamp

        for code, station in STATIONS.items():
            reference = f"api.meteo.example/v1/station/{code}/cumulative"
            # Start each season partway through, so a demo does not wait for
            # rain to accumulate from nothing.
            fraction = self.rng.uniform(0.2, 0.45)
            reading = EdgeReading(
                reference=reference,
                fields={
                    "rainfall_mm": 0.0,
                    "window_closed": 0,
                    "window_days": station.window_days,
                },
                attested_at=now,
                publisher="national meteorological service",
                index_field="rainfall_mm",
                progress_days=station.window_days * fraction,
            )
            self._start_season(reading, station)
            self.readings[reference] = reading

        # Seismic sources for the places the seeded book uses. Any other
        # coordinate gets its source the moment a policy is registered against
        # it, which is what makes the country insurable rather than a list.
        for name in LEGACY_CODES.values():
            place = find_place(name)
            if place is None:
                continue
            for radius in (25.0, 50.0, 100.0):
                reference = (
                    f"api.seismic.example/v1/max-magnitude"
                    f"?lat={place.latitude:g}&lon={place.longitude:g}"
                    f"&radius_km={radius:g}"
                )
                self.readings[reference] = EdgeReading(
                    reference=reference,
                    fields={"max_magnitude": 0.0, "events": 0},
                    attested_at=now,
                    publisher="national seismic network",
                    index_field="max_magnitude",
                )

    def _start_season(self, reading: EdgeReading, station: Any) -> None:
        """Lay out a season's rain in advance.

        The season total is drawn once, from the same gamma the policy was
        priced on. Accumulating it day by day instead would look right and be
        wrong: hundreds of small independent draws average out, the total would
        land near the mean every year, and a drought cover written against that
        world could never pay. Drawing the total first and then scattering it
        across the season keeps the running reading realistic and the endpoint
        exactly the distribution the price assumed.
        """
        target = gamma_quantile(self.rng.random(), station.shape, station.scale)

        # Scatter the total over rainy days, with most days dry.
        rainy = max(6, int(station.window_days * 0.22))
        days = sorted(self.rng.uniform(0.0, station.window_days) for _ in range(rainy))
        weights = [self.rng.gammavariate(0.9, 1.0) for _ in range(rainy)]
        total_weight = sum(weights) or 1.0
        schedule = [
            (day, target * weight / total_weight)
            for day, weight in zip(days, weights)
        ]

        reading.season_target = target
        reading.season_schedule = schedule
        reading.season_index = 0
        reading.fields["rainfall_mm"] = 0.0

        # Fast forward whatever part of the season has already passed.
        elapsed = reading.progress_days
        accumulated = 0.0
        while (
            reading.season_index < len(schedule)
            and schedule[reading.season_index][0] <= elapsed
        ):
            accumulated += schedule[reading.season_index][1]
            reading.season_index += 1
        reading.fields["rainfall_mm"] = round(accumulated, 2)

    def ensure_source(
        self,
        reference: str,
        index_field: str,
        *,
        resolves_in_days: float = 1.0,
        route: str = "",
        pace: float = 1.0,
    ) -> EdgeReading:
        """Register a source a policy needs but the world does not yet carry.

        Flights are the case: a reference exists only once someone insures that
        flight on that date.
        """
        reading = self.readings.get(reference)
        if reading is not None:
            # A source shared between a demonstration policy and one a person
            # bought moves at the slower pace: the person's year is a year.
            if pace < reading.pace:
                reading.pace = pace
            return reading

        if index_field in ("rain_24h_mm", "wind_24h_kmh"):
            reading = EdgeReading(
                reference=reference,
                fields={index_field: 0.0, "events": 0},
                attested_at=self.timestamp,
                publisher="NASA POWER",
                index_field=index_field,
            )
            reading.pace = pace
            self.readings[reference] = reading
            return reading
        if index_field == "mmi":
            reading = EdgeReading(
                reference=reference,
                fields={"mmi": 0.0, "events": 0},
                attested_at=self.timestamp,
                publisher="USGS ShakeMap and the national network",
                index_field=index_field,
            )
            reading.pace = pace
            self.readings[reference] = reading
            return reading
        if index_field == "max_magnitude":
            # A coordinate nobody has insured before. The source exists from the
            # moment cover is written against it, exactly like any other.
            reading = EdgeReading(
                reference=reference,
                fields={"max_magnitude": 0.0, "events": 0},
                attested_at=self.timestamp,
                publisher="national seismic network",
                index_field=index_field,
            )
        else:
            reading = EdgeReading(
                reference=reference,
                fields={index_field: 0.0, "status": "scheduled"},
                attested_at=self.timestamp,
                publisher="flight status aggregator",
                index_field=index_field,
                progress_days=-resolves_in_days,
                route=route,
            )
        reading.pace = pace
        self.readings[reference] = reading
        return reading

    def silence(self, reference: str) -> bool:
        """Stop a source publishing, to exercise the expiry path."""
        with self.lock:
            reading = self.readings.get(reference)
            if reading is None:
                return False
            reading.silent = True
            return True

    # -- REX: the duty each validator performs for itself -----------------

    def _perform_rex_duty(
        self, reading: EdgeReading, field: str, truth: float, *, exact: bool
    ) -> RexReport:
        """Every validator reads the source and reports what it saw.

        Nothing here is an approximation of Rialo for convenience. What lands on
        chain really is one update per validator rather than one agreed figure,
        so the disagreement has to be modelled to be reconciled, and a chain that
        hid it would be hiding the only interesting failure mode.
        """
        self.rex_round += 1
        report = RexReport(
            topic=topic_for(reading.reference, field),
            reference=reading.reference,
            field=field,
            round=self.rex_round,
        )
        names = sources_for(reading)
        for validator in self.validators:
            if self.rng.random() < self.config.miss_rate:
                continue  # this validator did not answer this round
            if exact:
                report.add(RexUpdate(validator=validator, value=truth, round=self.rex_round))
                continue
            # Each validator reads every independent source and keeps their
            # median. One source serving a stale cache or a garbled response
            # moves nothing; it would take two of three failing the same way.
            seen: list[tuple[str, float | None]] = []
            for name in names:
                if self.rng.random() < self.config.miss_rate:
                    seen.append((name, None))       # this source did not answer
                elif self.rng.random() < self.config.glitch_rate:
                    seen.append((name, truth * self.rng.choice((0.4, 1.9, 10.0))))
                else:
                    seen.append((name, truth * (1.0 + self.rng.gauss(0.0, self.config.measurement_noise))))
            values = [v for _, v in seen if v is not None]
            if not values:
                continue
            report.add(RexUpdate(validator=validator, value=statistics.median(values),
                                 round=self.rex_round, sources=tuple(seen)))
        return report

    def _publish(
        self, reading: EdgeReading, field: str, value: Any, *, final: bool | None = None
    ) -> Aggregation:
        """Put a figure on chain, but only if the validators agree on it.

        A refused round does not touch the topic, so no predicate wakes and
        nothing settles. The next round tries again. A reading the network could
        not agree on is treated as a reading that has not arrived, which is
        already a case this protocol knows how to end: if it never arrives, the
        deadline expires the policy and returns the premium.
        """
        exact = not isinstance(value, (int, float)) or isinstance(value, bool)
        # Flags are not measurements. A window either closed or it did not, and
        # perturbing that would be modelling noise that does not exist.
        exact = exact or field in _EXACT_FIELDS or value == 0
        truth = float(value) if not exact else 0.0

        report = self._perform_rex_duty(reading, field, truth, exact=exact)
        if exact:
            # Still recorded as a round, so the lineage shows every reading was
            # carried the same way, but agreement is trivial.
            settled: Any = value
            outcome = self.aggregator.aggregate(
                RexReport(
                    topic=report.topic, reference=reading.reference,
                    field=field, round=report.round,
                    updates=[
                        RexUpdate(validator=u.validator, value=1.0, round=u.round)
                        for u in report.updates
                    ],
                )
            )
        else:
            outcome = self.aggregator.aggregate(report)
            settled = outcome.value

        self.aggregations.append(outcome)
        if not outcome.settles:
            self.refused_rounds += 1
            return outcome

        reading.fields[field] = settled
        reading.attested_at = self.timestamp
        if final is not None:
            reading.final = final
        self._pending_touches.add(reading.key)
        return outcome

    def attest(
        self, reference: str, field: str, value: Any, *, final: bool = True
    ) -> EdgeReading | None:
        """Write a reading from outside the block producer.

        Used by an operator or a demonstration. The reading goes through the
        same validator round and the same aggregator as one the simulated world
        produced, so nothing downstream is bypassed and an injected figure is
        subject to the same agreement rule as a natural one.
        """
        with self.lock:
            reading = self.readings.get(reference)
            if reading is None:
                return None
            reading.silent = False
            self._publish(reading, field, value, final=final)
            return reading

    # -- registration -----------------------------------------------------

    def register(self, policy: Policy) -> ArmedPolicy:
        """Put a policy onchain as a reactive transaction."""
        tree = pred.parse(policy.predicate)
        keys = frozenset(pred.dependency_keys(tree))

        # Cover a person bought, declaring an interest in it, keeps the term on
        # its document: the source made for it moves at the clock's pace, not
        # the demonstration's, and _expire_overdue reads it by the clock too.
        real = bool((policy.metadata or {}).get("interest"))
        pace = 1.0 / self.config.world_acceleration if real else 1.0

        with self.lock:
            self._nonce += 1
            account = _signature(f"policy:{policy.policy_id}:{self._nonce}")

            if policy.peril_key == FLIGHT_DELAY.key:
                resolves = max(0.25, policy.term_days * 0.7)
                flight = self.ensure_source(
                    policy.data_reference,
                    "arrival_delay_minutes",
                    resolves_in_days=resolves,
                    route=str(policy.subject.get("route", "")), pace=pace,
                )
                if real and flight.progress_days < 0:
                    # Counted from when the cover started, so a restart does
                    # not put the flight back on the ground.
                    elapsed = max(0.0, (time.time() - policy.starts_at) / 86400.0)
                    flight.progress_days = max(flight.progress_days, -resolves + elapsed)
            elif policy.peril_key == "vehicle_flood":
                self.ensure_source(policy.data_reference, "rain_24h_mm", pace=pace)
            elif policy.peril_key == "storm":
                self.ensure_source(policy.data_reference, "wind_24h_kmh", pace=pace)
            elif policy.peril_key == EARTHQUAKE.key:
                # Any coordinate in the country can be insured, so the source
                # for it comes into being here rather than from a fixed list.
                self.ensure_source(policy.data_reference,
                                   "mmi" if EARTHQUAKE.shaking(policy.subject) else "max_magnitude",
                                   pace=pace)

            # The policy is minted to its holder as a token that cannot move:
            # it names the address it belongs to and the terms it carries, and
            # a transfer is refused. Minted once; registering again after a
            # restart finds it already there.
            if "token" not in policy.metadata:
                policy.metadata["token"] = mint_token(policy, self.height, self.timestamp)
                self._token_event("minted", policy)
            # A running maximum left by an earlier policy on this source must
            # not pay this one for an event before its term.
            self._reset_if_idle(policy.data_reference)
            armed = ArmedPolicy(
                policy=policy,
                tree=tree,
                keys=keys,
                registered_block=self.height,
                registered_at=self.timestamp,
                account=account,
            )
            self.armed[account] = armed
            self._newly_armed.add(account)
            for key in keys:
                self.index[key].add(account)

            self._pending_registrations.append(
                {
                    "account": account,
                    "policy_id": policy.policy_id,
                    "peril": policy.peril_key,
                    "predicate": policy.predicate,
                    "limit": policy.limit,
                    "premium": policy.premium,
                    "registered_block": self.height,
                    "registered_at": self.timestamp,
                    "keys": sorted(keys),
                }
            )
            return armed

    # -- snapshot ---------------------------------------------------------

    def snapshot(self) -> pred.Snapshot:
        edge = {
            reference: dict(reading.fields)
            for reference, reading in self.readings.items()
        }
        return {
            "edge": edge,
            "oracle": {},
            "state": {},
            "event": {},
            "workflow": {},
            "time": {"block": self.height, "timestamp": self.timestamp},
        }

    # -- block production -------------------------------------------------

    def produce_block(self) -> dict[str, Any]:
        with self.lock:
            self.height += 1
            self.timestamp += BLOCK_TIME_SECONDS
            height = self.height

            registrations = list(self._pending_registrations)
            self._pending_registrations = []

            touched = self._advance_world()
            touched.update(self._pending_touches)
            pending_before = self._pending_touches
            self._pending_touches = set()
            ordinary = self.rng.randint(0, 9)

            try:
                settlements = self._run_queue(height)
                candidates = self._candidates(touched)
                fired = self._evaluate(candidates, height)
                settlements.extend(self._run_queue(height))

                expired = self._expire_overdue(height)
                settlements.extend(expired)
            except Exception:
                # Whatever moved this block is evaluated next block instead
                # of being lost with the exception.
                self._pending_touches |= touched | pending_before
                raise

            block = {
                "height": height,
                "timestamp": self.timestamp,
                "hash": _signature(f"block:{height}"),
                "transaction_count": ordinary + len(settlements) + len(registrations),
                "registrations": registrations,
                "settlements": [item.to_dict() for item in settlements],
                "touched_keys": sorted(touched),
                "evaluated_policies": len(candidates),
                "armed_total": len(self.armed),
                "fired": fired,
            }
            self.blocks.append(block)
            self.blocks_by_height[height] = block
            if len(self.blocks_by_height) > self.config.retain_blocks:
                self.blocks_by_height.pop(height - self.config.retain_blocks, None)
            return block

    def _advance_world(self) -> set[str]:
        """Move every source forward and report which keys changed."""
        touched: set[str] = {"time:block", "time:timestamp"}
        base_elapsed = (
            BLOCK_TIME_SECONDS * self.config.world_acceleration / 86400.0
        )

        for reference, reading in self.readings.items():
            if reading.silent or reading.final:
                continue

            index_field = reading.index_field
            elapsed_days = base_elapsed * reading.pace
            if index_field == "rainfall_mm":
                if self._advance_rainfall(reading, elapsed_days):
                    touched.add(reading.key)
            elif index_field == "max_magnitude":
                if self._advance_seismic(reading, elapsed_days):
                    touched.add(reading.key)
            elif index_field == "rain_24h_mm":
                if self._advance_rain_extreme(reading, elapsed_days):
                    touched.add(reading.key)
            elif index_field == "wind_24h_kmh":
                if self._advance_wind_extreme(reading, elapsed_days):
                    touched.add(reading.key)
            elif index_field == "mmi":
                if self._advance_shaking(reading, elapsed_days):
                    touched.add(reading.key)
            elif index_field == "arrival_delay_minutes":
                if self._advance_flight(reading, elapsed_days):
                    touched.add(reading.key)

        return touched

    def _advance_rainfall(self, reading: EdgeReading, elapsed_days: float) -> bool:
        """Accumulate rainfall through the season, then close the window.

        Nothing settles until the window closes. A running total that happens
        to be low in June says nothing about the harvest, and a policy that
        paid on it would be paying for weather that had not happened yet.
        """
        code = reading.reference.split("/station/")[1].split("/")[0]
        station = STATIONS.get(code)
        if station is None:
            return False

        reading.progress_days += elapsed_days

        # Release whatever rain the season had scheduled for the days just passed.
        added = 0.0
        while (
            reading.season_index < len(reading.season_schedule)
            and reading.season_schedule[reading.season_index][0] <= reading.progress_days
        ):
            added += reading.season_schedule[reading.season_index][1]
            reading.season_index += 1

        if reading.progress_days >= station.window_days:
            # Close on exactly the total that was drawn, so the settled index
            # is the distribution the policy was priced against. This is the
            # reading a policy settles on, so it goes through the validators.
            outcome = self._publish(
                reading, "rainfall_mm", round(reading.season_target, 2), final=True
            )
            if not outcome.settles:
                # The network could not agree this round. The window stays open
                # and the next round tries again; nothing settles on a figure
                # the validators did not converge on.
                reading.final = False
                return False
            closed = self._publish(reading, "window_closed", 1)
            if not closed.settles:
                # The total is agreed but the closing is not yet: the reading
                # stays live so the next block tries the closing again, and
                # the policies on it wait rather than lapse.
                reading.final = False
                return False
            return True

        if added <= 0:
            return False

        running = round(float(reading.fields["rainfall_mm"]) + added, 2)
        return self._publish(reading, "rainfall_mm", running).settles

    def _advance_seismic(self, reading: EdgeReading, elapsed_days: float) -> bool:
        """Draw seismicity in the circle this reference covers.

        The circle is read back out of the reference the policy was written
        against, so the world the chain produces is the world the policy was
        priced on rather than a second one that happens to look similar.
        """
        try:
            radius = float(reading.reference.split("radius_km=")[1].split("&")[0])
            latitude = float(reading.reference.split("lat=")[1].split("&")[0])
            longitude = float(reading.reference.split("lon=")[1].split("&")[0])
        except (IndexError, ValueError):
            return False

        subject = {
            "latitude": latitude, "longitude": longitude, "radius_km": radius,
        }
        years = elapsed_days / 365.25

        # The whole hazard, as the peril model states it, over this slice of time.
        rate_any = EARTHQUAKE.local_rate(subject, 4.0) * years
        if self.rng.random() >= 1.0 - math.exp(-rate_any):
            return False

        # An event happened. Draw its magnitude from the same hazard curve by
        # inverting the exceedance the peril model publishes.
        magnitude = self._draw_magnitude(subject)
        reading.fields["events"] = int(reading.fields.get("events", 0)) + 1
        if magnitude <= float(reading.fields["max_magnitude"]):
            reading.attested_at = self.timestamp
            return True

        return self._publish(reading, "max_magnitude", round(magnitude, 2)).settles

    def _advance_rain_extreme(self, reading: EdgeReading, elapsed_days: float) -> bool:
        """Heavy rain days at one place, from the Gumbel fit the policy was priced on."""
        from ..perils.vehicle import annual_exceedance, nearest

        try:
            latitude = float(reading.reference.split("lat=")[1].split("&")[0])
            longitude = float(reading.reference.split("lon=")[1].split("&")[0])
        except (IndexError, ValueError):
            return False
        place, _ = nearest(latitude, longitude)
        if place is None:
            return False
        # Days of 20 mm or more, as a rate a year; the day's total is drawn from
        # the tail above that, so the largest day over a year follows the fit.
        floor = 20.0
        rate = -math.log(max(1e-12, 1.0 - annual_exceedance(place, floor)))
        if self.rng.random() >= 1.0 - math.exp(-rate * elapsed_days / 365.25):
            return False
        uniform = self.rng.random()
        low, high = floor, 400.0
        for _ in range(40):
            middle = 0.5 * (low + high)
            share = -math.log(max(1e-12, 1.0 - annual_exceedance(place, middle))) / rate
            if share > uniform:
                low = middle
            else:
                high = middle
        value = 0.5 * (low + high)
        reading.fields["events"] = int(reading.fields.get("events", 0)) + 1
        if value <= float(reading.fields.get("rain_24h_mm", 0.0)):
            reading.attested_at = self.timestamp
            return True
        return self._publish(reading, "rain_24h_mm", round(value, 1)).settles

    def _advance_wind_extreme(self, reading: EdgeReading, elapsed_days: float) -> bool:
        """Windy days at one place, from the Gumbel fit the policy was priced on."""
        from ..perils.storm import annual_exceedance, nearest

        try:
            latitude = float(reading.reference.split("lat=")[1].split("&")[0])
            longitude = float(reading.reference.split("lon=")[1].split("&")[0])
        except (IndexError, ValueError):
            return False
        place, _ = nearest(latitude, longitude)
        if place is None:
            return False
        # Days of 40 km/h or more, as a rate a year; the day's figure is drawn
        # from the tail above that, so the windiest day over a year follows
        # the fit.
        floor = 40.0
        rate = -math.log(max(1e-12, 1.0 - annual_exceedance(place, floor)))
        if self.rng.random() >= 1.0 - math.exp(-rate * elapsed_days / 365.25):
            return False
        uniform = self.rng.random()
        low, high = floor, 300.0
        for _ in range(40):
            middle = 0.5 * (low + high)
            share = -math.log(max(1e-12, 1.0 - annual_exceedance(place, middle))) / rate
            if share > uniform:
                low = middle
            else:
                high = middle
        value = 0.5 * (low + high)
        reading.fields["events"] = int(reading.fields.get("events", 0)) + 1
        if value <= float(reading.fields.get("wind_24h_kmh", 0.0)):
            reading.attested_at = self.timestamp
            return True
        return self._publish(reading, "wind_24h_kmh", round(value, 1)).settles

    def _advance_shaking(self, reading: EdgeReading, elapsed_days: float) -> bool:
        """Shaking at one address, drawn from the same curve the policy was priced on."""
        from ..perils import shaking as sh

        try:
            latitude = float(reading.reference.split("lat=")[1].split("&")[0])
            longitude = float(reading.reference.split("lon=")[1].split("&")[0])
        except (IndexError, ValueError):
            return False
        subject = {"latitude": latitude, "longitude": longitude}
        years = elapsed_days / 365.25
        base = sh.rate_at_least(subject, 4.0)
        if base <= 0 or self.rng.random() >= 1.0 - math.exp(-base * years):
            return False
        uniform = self.rng.random()
        low, high = 4.0, 11.0
        for _ in range(40):
            middle = 0.5 * (low + high)
            if sh.rate_at_least(subject, middle) / base > uniform:
                low = middle
            else:
                high = middle
        value = 0.5 * (low + high)
        reading.fields["events"] = int(reading.fields.get("events", 0)) + 1
        if value <= float(reading.fields.get("mmi", 0.0)):
            reading.attested_at = self.timestamp
            return True
        return self._publish(reading, "mmi", round(value, 2)).settles

    def _draw_magnitude(self, subject: dict[str, Any]) -> float:
        """A magnitude consistent with the peril's own rate curve."""
        base = EARTHQUAKE.local_rate(subject, 4.0)
        if base <= 0:
            return 0.0
        uniform = self.rng.random()
        low, high = 4.0, 8.0
        for _ in range(60):
            middle = 0.5 * (low + high)
            share = EARTHQUAKE.local_rate(subject, middle) / base
            if share > uniform:
                low = middle
            else:
                high = middle
        return 0.5 * (low + high)

    def _advance_flight(self, reading: EdgeReading, elapsed_days: float) -> bool:
        """Resolve a flight when it lands, then mark the reading final.

        A flight status endpoint publishes nothing useful until the aircraft
        has arrived or been cancelled, and then it publishes once.
        """
        reading.progress_days += elapsed_days
        if reading.progress_days < 0:
            return False

        # Resolve against the same route statistics the policy was priced on,
        # so the chain and the price describe one world rather than two.
        stats = ROUTES.get(reading.route)
        cancellation = stats.cancellation_rate if stats else 0.013
        late = stats.late_rate if stats else 0.243
        median = stats.median_late_minutes if stats else 41.0

        roll = self.rng.random()
        if roll < cancellation:
            delay = CANCELLATION_MINUTES
            reading.fields["status"] = "cancelled"
        elif roll < cancellation + late:
            delay = round(math.exp(self.rng.gauss(math.log(median), LOG_SIGMA)), 1)
            reading.fields["status"] = "landed"
        else:
            delay = round(max(0.0, self.rng.gauss(7.0, 5.0)), 1)
            reading.fields["status"] = "landed"

        outcome = self._publish(reading, "arrival_delay_minutes", delay, final=True)
        if not outcome.settles:
            # The flight has still landed; the chain simply has no agreed figure
            # for it yet. Roll the clock back so the next block reports again.
            reading.progress_days -= elapsed_days
            reading.final = False
            return False
        return True

    # -- evaluation -------------------------------------------------------

    def _candidates(self, touched: Iterable[str]) -> list[ArmedPolicy]:
        accounts: set[str] = set(self._newly_armed)
        self._newly_armed = set()
        for key in touched:
            accounts.update(self.index.get(key, ()))
        return [self.armed[a] for a in accounts if a in self.armed]

    def _evaluate(self, candidates: list[ArmedPolicy], height: int) -> int:
        snapshot = self.snapshot()
        fired = 0

        for armed in sorted(candidates, key=lambda a: a.account):
            self._evaluations += 1
            try:
                result = pred.evaluate(armed.tree, snapshot)
            except pred.EvaluationError:
                # The reading this policy needs is not on the chain. It stays
                # armed, and the deadline is what eventually resolves it.
                continue

            if not result:
                continue

            armed.condition_block = height
            final = height + self.confirm_blocks(armed.policy)
            index_now = self._observed_index(armed)
            self._queue.append((final, armed, index_now))
            # Recorded on the policy, so a restart during the window resumes it
            # rather than forgetting that the index was reached.
            armed.policy.metadata["provisional"] = {
                "since_block": height, "final_block": final, "index": index_now,
                "at": self.timestamp,
            }
            self._disarm(armed.account)
            fired += 1

        return fired

    def _observed_index(self, armed: ArmedPolicy) -> float:
        reading = self.readings.get(armed.policy.data_reference)
        return float(reading.value) if reading else 0.0

    def _token_event(self, event: str, policy: Policy) -> None:
        for listener in list(self.token_listeners):
            try:
                listener(event, policy)
            except Exception:
                import logging
                logging.getLogger("clause.chain").exception("token listener failed")

    def _settled(self, settlement: Settlement) -> None:
        self.settlements.append(settlement)
        for listener in list(self.listeners):
            try:
                listener(settlement)
            except Exception:
                import logging
                logging.getLogger("clause.chain").exception("settlement listener failed")

    def withdraw(self, policy: Policy) -> bool:
        """Take a cancelled policy off chain, so nothing settles it later.

        Its token is burned in the same step: a cancelled policy is cover that
        never was, and a token for it has no business staying in a wallet.
        The burn is written on the token rather than deleting it, so the
        wallet's history still says what was minted and when it went.
        """
        with self.lock:
            token = (policy.metadata or {}).get("token")
            if token and not token.get("burned_at"):
                token.update({"burned_block": self.height, "burned_at": self.timestamp,
                              "burned_from": token.get("owner"), "owner": None,
                              "burned_because": "cancelled"})
                self._token_event("burned", policy)
            for account, armed in list(self.armed.items()):
                if armed.policy.policy_id == policy.policy_id:
                    self._disarm(account)
                    return True
            self._queue = [item for item in self._queue if item[1].policy.policy_id != policy.policy_id]
        return False

    RUNNING_MAX = ("max_magnitude", "mmi", "rain_24h_mm", "wind_24h_kmh")

    def _reset_if_idle(self, reference: str) -> None:
        """A source whose index is a running maximum starts again from zero
        once nothing is armed on it, so the next policy is judged on what
        happens during its own term and not on what happened before it."""
        reading = self.readings.get(reference)
        if reading is None or reading.index_field not in self.RUNNING_MAX:
            return
        if self.index.get(reading.key):
            return
        if any(item[1].policy.data_reference == reference for item in self._queue):
            return
        if float(reading.fields.get(reading.index_field, 0.0) or 0.0) > 0:
            reading.fields[reading.index_field] = 0.0
            reading.attested_at = self.timestamp

    def _disarm(self, account: str) -> None:
        armed = self.armed.pop(account, None)
        if armed is None:
            return
        for key in armed.keys:
            bucket = self.index.get(key)
            if bucket:
                bucket.discard(account)
                if not bucket:
                    self.index.pop(key, None)

    def confirm_blocks(self, policy: Policy) -> int:
        """Blocks to wait for corrections before paying: the window in hours
        at the pace the policy's source moves. For cover a person bought the
        source moves at the clock, so the window is real time, capped at two
        hours so that a settlement is still something one can watch."""
        hours = CONFIRM_HOURS.get(policy.peril_key, 0.0)
        if hours <= 0:
            return 0
        reading = self.readings.get(policy.data_reference)
        pace = reading.pace if reading is not None else 1.0
        if pace < 1.0:
            hours = min(hours, 2.0)
        per_block = BLOCK_TIME_SECONDS * self.config.world_acceleration * pace / 3600.0
        return max(1, min(math.ceil(hours / per_block), int(2 * 3600 / BLOCK_TIME_SECONDS)))

    def resume_provisional(self, policy: Policy) -> None:
        """After a restart: a policy that had reached its index is settled on
        the index it reached, since the world's readings were rebuilt."""
        info = (policy.metadata or {}).get("provisional") or {}
        armed = self.register(policy)
        with self.lock:
            self._disarm(armed.account)
            armed.condition_block = int(info.get("since_block", self.height))
            # The reading the trigger was seen on is not rebuilt after a
            # restart, so the stored index settles it; see _run_queue.
            armed.resumed_index = float(info.get("index", 0.0))
            self._queue.append((self.height + 1, armed, float(info.get("index", 0.0))))

    def _rearm(self, armed: ArmedPolicy) -> None:
        self.armed[armed.account] = armed
        for key in armed.keys:
            self.index[key].add(armed.account)

    def _run_queue(self, height: int) -> list[Settlement]:
        ready = [item for item in self._queue if item[0] <= height]
        if not ready:
            return []
        self._queue = [item for item in self._queue if item[0] > height]

        done: list[Settlement] = []
        paid_refs: set[str] = set()
        from ..protocol.policy import settle_index
        for condition_block, armed, index_value in ready:
            policy = armed.policy
            # The final figure, after the window, is the one that pays. If the
            # reading has since been attested on chain use it; a correction that
            # took it below the trigger sends the policy back to waiting rather
            # than paying on a number the sources withdrew.
            reading = self.readings.get(policy.data_reference)
            resumed = getattr(armed, "resumed_index", None)
            if resumed is not None:
                # After a restart the reading was rebuilt from nothing; the
                # index attested before it is the one that pays.
                index_value = resumed
                armed.resumed_index = None
            elif reading is not None and reading.value is not None:
                index_value = float(reading.value)
            if settle_index(policy, index_value) <= 0:
                policy.metadata.pop("provisional", None)
                policy.metadata["withdrawn_trigger"] = {"block": height, "index": index_value}
                self._rearm(armed)
                continue
            policy.metadata.pop("provisional", None)
            signature = _signature(f"settle:{policy.policy_id}:{height}")
            refused = None
            if self.settlement_check is not None:
                try:
                    refused = self.settlement_check(policy)
                except Exception as error:  # a broken check must not pay or lose
                    refused = f"the compliance check could not run: {error}"
            try:
                if refused:
                    # Unwound on the terms of a source that never published:
                    # the premium comes back, the payout does not go out.
                    amount = self.pool.expire(policy, now=self.timestamp,
                                              note=f"not paid: {refused}; premium returned")
                    summary = f"settlement refused by the compliance rules ({refused}); premium of {amount:,.0f} returned"
                    kind = "expired"
                else:
                    amount = self.pool.pay(
                        policy, index_value, now=self.timestamp
                    )
                    summary = (
                        f"{policy.peril_key.replace('_', ' ')} index of {index_value:g} "
                        f"attested, {amount:,.0f} paid with no claim filed"
                    )
                    kind = "paid"
            except Exception as error:  # the pool refused; record it plainly
                amount = 0.0
                summary = f"settlement failed: {error}"
                kind = "failed"
                # Not lost: the policy stays armed and is tried again on the
                # next block that touches its source, or expires in time.
                policy.metadata["provisional"] = {"index": index_value, "since_block": condition_block}
                self._queue.append((height + 60, armed, index_value))

            if kind == "paid":
                paid_refs.add(policy.data_reference)
            settlement = Settlement(
                signature=signature,
                policy_id=policy.policy_id,
                block_number=height,
                condition_block=armed.condition_block if armed.condition_block is not None else condition_block,
                at=self.timestamp,
                kind=kind,
                index_value=index_value,
                amount=amount,
                summary=summary,
            )
            self._settled(settlement)
            done.append(settlement)
        for reference in paid_refs:
            self._reset_if_idle(reference)
        return done

    def _expire_overdue(self, height: int) -> list[Settlement]:
        """Close policies whose term and grace period have both passed.

        A policy whose source went quiet is refunded. One whose term simply
        ended without a trigger lapses.
        """
        done: list[Settlement] = []
        for account, armed in list(self.armed.items()):
            policy = armed.policy
            if (policy.metadata or {}).get("interest"):
                # Bought by a person, who declared an interest in it: its term
                # runs in the time on the document, however fast the rest of
                # the demonstration's world is turning. A year of cover that
                # ended in thirteen minutes would be a lie to its holder. The
                # clock, not the chain's timestamp, which stands still while
                # the service is down and moves at the block rate.
                world_now = time.time()
            else:
                world_now = self.genesis + (
                    (self.timestamp - self.genesis) * self.config.world_acceleration
                )
            if world_now < policy.deadline_at:
                continue

            reading = self.readings.get(policy.data_reference)
            went_quiet = reading is None or reading.silent

            signature = _signature(f"close:{policy.policy_id}:{height}")
            try:
                if went_quiet:
                    amount = self.pool.expire(policy, now=self.timestamp)
                    kind = "expired"
                    summary = (
                        "the source published nothing before the deadline, so the "
                        f"premium of {amount:,.0f} was returned"
                    )
                else:
                    self.pool.lapse(policy, now=self.timestamp)
                    amount = 0.0
                    kind = "lapsed"
                    summary = "the term ended without the index reaching the trigger"
            except Exception as error:
                # The pool could not close it (a refund it cannot fund, a
                # policy already closed). Recorded, disarmed, and the block
                # goes on: one policy must not stop the chain.
                logger.warning("could not close %s at its deadline: %s", policy.policy_id, error)
                amount, kind = 0.0, "failed"
                summary = f"could not be closed at its deadline: {error}"

            self._disarm(account)
            settlement = Settlement(
                signature=signature,
                policy_id=policy.policy_id,
                block_number=height,
                condition_block=height,
                at=self.timestamp,
                kind=kind,
                index_value=None if went_quiet else self._observed_index(armed),
                amount=amount,
                summary=summary,
            )
            self._settled(settlement)
            done.append(settlement)
        return done

    # -- views ------------------------------------------------------------

    def pending(self) -> list[dict[str, Any]]:
        """Every policy the chain is currently holding open."""
        with self.lock:
            rows = []
            for armed in self.armed.values():
                reading = self.readings.get(armed.policy.data_reference)
                rows.append(
                    {
                        "account": armed.account,
                        "policy_id": armed.policy_id,
                        "peril": armed.policy.peril_key,
                        "predicate": armed.policy.predicate,
                        "readable": pred.describe(armed.tree),
                        "limit": armed.policy.limit,
                        "registered_block": armed.registered_block,
                        "registered_at": armed.registered_at,
                        "armed_seconds": max(0.0, self.timestamp - armed.registered_at),
                        "keys": sorted(armed.keys),
                        "current_index": reading.value if reading else None,
                        "source_silent": bool(reading and reading.silent),
                    }
                )
            rows.sort(key=lambda row: row["registered_at"])
            return rows

    def forget(self, policy_ids: set[str]) -> int:
        """Drop the settlements of policies that are no longer in the book.

        Only the record is dropped, never the arithmetic: what each dropped
        settlement contributed to the counts and to the mean latency is kept,
        so every figure the chain publishes is the same afterwards. Used for
        the demonstration's own policies, which arrive by the thousand and
        would otherwise be walked by everything, for ever.
        """
        if not policy_ids:
            return 0
        with self.lock:
            keep, gone = [], 0
            for s in self.settlements:
                if s.policy_id not in policy_ids:
                    keep.append(s)
                    continue
                gone += 1
                self.forgotten["settlements"] = self.forgotten.get("settlements", 0) + 1
                self.forgotten[s.kind] = self.forgotten.get(s.kind, 0) + 1
                if s.kind == "paid":
                    self.forgotten["latency_total"] = self.forgotten.get("latency_total", 0.0) + s.latency_blocks
                    self.forgotten["latency_count"] = self.forgotten.get("latency_count", 0) + 1
            if gone:
                self.settlements = keep
            for account, armed in list(self.armed.items()):
                if armed.policy.policy_id in policy_ids:
                    self.armed.pop(account, None)
                    for holders in self.index.values():
                        holders.discard(account)
            return gone

    def stats(self) -> dict[str, Any]:
        with self.lock:
            forgotten = self.forgotten
            latencies = [s.latency_blocks for s in self.settlements if s.kind == "paid"]
            latency_total = sum(latencies) + forgotten.get("latency_total", 0.0)
            latency_count = len(latencies) + int(forgotten.get("latency_count", 0))
            return {
                "height": self.height,
                "timestamp": self.timestamp,
                "armed": len(self.armed),
                "queued": len(self._queue),
                "evaluations": self._evaluations,
                "settlements": len(self.settlements) + int(forgotten.get("settlements", 0)),
                "paid": sum(1 for s in self.settlements if s.kind == "paid") + int(forgotten.get("paid", 0)),
                "expired": sum(1 for s in self.settlements if s.kind == "expired") + int(forgotten.get("expired", 0)),
                "lapsed": sum(1 for s in self.settlements if s.kind == "lapsed") + int(forgotten.get("lapsed", 0)),
                "sources": len(self.readings),
                "silent_sources": sum(1 for r in self.readings.values() if r.silent),
                "mean_latency_blocks": (latency_total / latency_count if latency_count else 0.0),
                # The REX layer: how the outside world actually gets in.
                "validators": self.config.validators,
                "quorum": self.aggregator.quorum,
                "rex_rounds": self.rex_round,
                "refused_rounds": self.refused_rounds,
                "aggregation_rule": self.aggregator.describe(),
            }

    def recent_aggregations(self, limit: int = 20) -> list[dict[str, Any]]:
        """The last rounds of validator reports, agreed and refused alike."""
        with self.lock:
            return [a.to_dict() for a in list(self.aggregations)[-limit:]][::-1]

    def lineage(self, policy_id: str) -> dict[str, Any] | None:
        """Why this policy did or did not pay, from the chain's own record.

        The question an insurer is normally asked to answer out of its own files.
        Here the answer is assembled from what the chain stored: the subscription
        that was registered, every round of validator reports on the topic it
        listens to, what the aggregator concluded about each, and the settlement
        transaction if one ran.

        A buyer can reconstruct all of this without this interface, through
        get_subscription, get_triggered_transactions and get_workflow_lineage.
        That is the point of showing it: not to be believed, but to be checked.
        """
        policy = self.pool.policies.get(policy_id)
        if policy is None:
            return None

        with self.lock:
            armed = next(
                (a for a in self.armed.values() if a.policy_id == policy_id), None
            )
            rounds = [
                a.to_dict() for a in self.aggregations
                if a.reference == policy.data_reference
            ]
            settlements = [
                s.to_dict() for s in self.settlements if s.policy_id == policy_id
            ]
            reading = self.readings.get(policy.data_reference)
            source = self.data_source_view(policy)

            provisional = next(
                ({"since_block": a.condition_block, "final_block": final, "index": idx}
                 for final, a, idx in self._queue if a.policy_id == policy_id), None)
            peril = policy.peril
            curve = (peril.curve_in_mm(policy.subject, policy.curve)
                     if policy.peril_key == "drought" else policy.curve)
            measured = reading.value if reading is not None else None
            outcome = {
                "measured": measured if isinstance(measured, (int, float)) else None,
                "unit": peril.unit_for(policy.subject),
                "direction": curve.direction.value,
                "steps": [{"level": b.level, "share": b.share} for b in curve.breakpoints],
                "trigger": curve.attachment,
                "sources_silent": bool(reading.silent) if reading is not None else True,
                "withdrawn": (policy.metadata or {}).get("withdrawn_trigger"),
            }
            return {
                "policy_id": policy_id,
                "status": policy.status.value,
                "provisional": provisional,
                "outcome": outcome,
                "subscription": {
                    "account": armed.account if armed else None,
                    "registered_block": armed.registered_block if armed else None,
                    "topic": topic_for(policy.data_reference, source["field"]),
                    "kind": "OneShot",
                    "predicate": policy.predicate,
                    "keys": sorted(armed.keys) if armed else [],
                },
                "source": source,
                "reading": reading.to_dict() if reading else None,
                "rex_rounds": rounds[-25:][::-1],
                "refused": sum(1 for r in rounds if not r["settles"]),
                "settlements": settlements,
                "rule": self.aggregator.describe(),
            }

    def data_source_view(self, policy: Policy) -> dict[str, Any]:
        """The source a policy reads, as its own peril describes it."""
        source = policy.peril.data_source(policy.subject)
        return {
            "reference": source.reference,
            "field": source.field,
            "publisher": source.publisher,
            "resolution": source.resolution,
            "settlement_deadline_days": source.settlement_deadline_days,
            "on_missing_data": source.on_missing_data,
        }

    def recent_blocks(self, limit: int = 80) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.blocks)[-limit:]

    def recent_settlements(self, limit: int = 40) -> list[dict[str, Any]]:
        with self.lock:
            return [item.to_dict() for item in self.settlements[-limit:]][::-1]

    def recent_decisions(self, limit: int = 12) -> list[dict[str, Any]]:
        """The policies the chain decided most recently, paid and not paid.

        The proof page used to open with an empty box asking for a policy id,
        which only somebody who already had one could answer. This is the same
        record it would have shown, for the policies it decided last, so the
        page can open with the work instead of a question.

        It publishes nothing the chain was keeping: a settlement is already a
        public transaction and the lineage of any policy already answers to its
        id. What this removes is the need to know the id first, which is a
        property of our interface, not of the record. The holder is the one
        thing left out, because no part of the argument needs it.

        Both halves are here. A policy that ran its term without the index ever
        reaching the line is the harder half of the promise and the one worth
        showing: an insurer that only publishes what it paid has published an
        advertisement.
        """
        with self.lock:
            seen: set[str] = set()
            out: list[dict[str, Any]] = []
            for item in reversed(self.settlements):
                if item.policy_id in seen:
                    continue
                policy = self.pool.policies.get(item.policy_id)
                if policy is None:
                    continue
                seen.add(item.policy_id)
                peril = policy.peril
                curve = (
                    peril.curve_in_mm(policy.subject, policy.curve)
                    if policy.peril_key == "drought"
                    else policy.curve
                )
                out.append({
                    "policy_id": item.policy_id,
                    "kind": item.kind,
                    "peril": policy.peril_key,
                    "peril_name": peril.title_for(policy.subject),
                    "subject_text": peril.describe_subject(policy.subject),
                    "predicate": policy.predicate,
                    "unit": peril.unit_for(policy.subject),
                    "direction": curve.direction.value,
                    "trigger": curve.attachment,
                    "measured": item.index_value,
                    "amount": round(item.amount, 2),
                    "limit": round(policy.limit, 2),
                    "block_number": item.block_number,
                    "condition_block": item.condition_block,
                    "latency_blocks": item.latency_blocks,
                    "at": item.at,
                    "summary": item.summary,
                })
                if len(out) >= limit:
                    break
            return out

    def edge_readings(self) -> list[dict[str, Any]]:
        with self.lock:
            return [reading.to_dict() for reading in self.readings.values()]

    # -- run loop ---------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="clause-chain", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        interval = BLOCK_TIME_SECONDS / max(self.config.speed, 0.01)
        next_tick = time.perf_counter()
        while self._running:
            try:
                self.produce_block()
            except Exception:  # a block must not kill the chain, but is never silent
                logger.exception("block %s failed", self.height)
            next_tick += interval
            delay = next_tick - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.perf_counter()
