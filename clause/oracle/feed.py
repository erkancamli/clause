"""Going and asking, for the policies a person actually bought.

The rest of this package can read an agency's answer. This is the part that
decides which question to ask, asks it on a schedule, and writes what came
back onto the chain. Until it existed the chain produced its own readings from
a random number generator seeded in source, which is the right way to
demonstrate a protocol and the wrong way to settle a policy.

What separates the two is the reference. A policy the demonstration book wrote
is addressed to a domain reserved for examples, which can never resolve; a
policy a person bought is addressed to the agency's own service, with the
circle written into the query. So the chain can be walked and the references
sorted into the ones somebody has to go and ask about and the ones nobody
should: see :func:`is_measured`.

Three rules this layer holds to, each of them the reason for a piece of code
below rather than a sentiment:

**Never settle on one instrument.** The Paris Charles de Gaulle station showed
four and five degrees of a jump on two April evenings in 2026, each one
setting a site record, each one settling money on a prediction market, and a
climate nonprofit found it by chance. An earthquake is read from USGS, EMSC
and, inside Türkiye, AFAD, and where they disagree by more than the peril's
tolerance nothing is written at all.

**A running maximum only ever rises.** A cover reads the largest event in its
window. Asking again an hour later and finding a quiet hour does not undo the
earthquake, so a smaller answer is recorded as a visit and not as a reading.

**A failure to reach a source is not a reading of zero.** If nobody answers,
the poll says so and writes nothing. The policy's own missing-data branch,
which is on its face and was priced for, is what handles the silence.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from . import quake
from .agreement import read_from
from .events import largest
from .observation import Observation, Reading

#: The hosts a reference may name and still be worth asking. Anything else --
#: above all the ``.example`` domains the demonstration writes against -- is a
#: reference nobody should try to resolve, and trying would be the bug.
MEASURED_HOSTS = frozenset({"earthquake.usgs.gov"})

#: How far back a first poll looks when a reference has never been read. A
#: policy is registered when it is bought and polled within the minute, so this
#: is about restarts rather than about history.
FIRST_LOOK_DAYS = 2.0

#: The smallest magnitude worth asking for. Below the smallest attachment any
#: curve uses, a smaller event cannot move a policy and the query is only
#: larger for it.
FLOOR_MAGNITUDE = 4.0

#: Where AFAD is worth asking: it publishes the Turkish network and nothing
#: else, so outside this box it would answer with events it did not measure at
#: the place in question. Generous on every side, because the point is to
#: decide whether to ask, not where the border runs.
TURKIYE_BOX = (35.0, 43.0, 25.0, 45.5)   # south, north, west, east


def host_of(reference: str) -> str:
    """The host a reference names, without the path or the query."""
    return reference.split("?", 1)[0].split("/", 1)[0].strip().lower()


def is_measured(reference: str) -> bool:
    """Whether this reference names a source somebody should go and ask."""
    return host_of(reference) in MEASURED_HOSTS


def circle_of(reference: str) -> tuple[float, float, float] | None:
    """The circle a seismic reference was written against.

    Read back out of the reference rather than off the policy, because the
    reference is what the predicate was indexed under and what the contract
    prints: if the two ever disagreed, the one the buyer can read is the one
    that should decide.
    """
    try:
        latitude = float(reference.split("lat=")[1].split("&")[0])
        longitude = float(reference.split("lon=")[1].split("&")[0])
    except (IndexError, ValueError):
        return None
    try:
        radius = float(reference.split("radius_km=")[1].split("&")[0])
    except (IndexError, ValueError):
        # A shaking reference carries no radius: it is read at the address.
        radius = 0.0
    return latitude, longitude, radius


def field_of(reference: str) -> str:
    """Which quantity this reference reads out of the response."""
    return "mmi" if "index=mmi" in reference else "max_magnitude"


def _km(latitude: float, longitude: float, other: Observation) -> float:
    lat = math.radians((latitude + other.latitude) / 2.0)
    dx = (longitude - other.longitude) * 111.32 * math.cos(lat)
    dy = (latitude - other.latitude) * 110.57
    return math.hypot(dx, dy)


def _in_turkiye(latitude: float, longitude: float) -> bool:
    south, north, west, east = TURKIYE_BOX
    return south <= latitude <= north and west <= longitude <= east


@dataclass(frozen=True, slots=True)
class Attestation:
    """One visit to the sources, and what came of it.

    Returned whether or not anything was written, because a poll that wrote
    nothing is the interesting one: it is either a quiet window or two agencies
    that cannot be reconciled, and those are not the same fact.
    """

    reference: str
    index_field: str
    written: bool
    why: str
    value: float = 0.0
    reading: Reading | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "reference": self.reference, "field": self.index_field,
            "written": self.written, "why": self.why, "value": self.value,
        }
        if self.reading is not None:
            out["reading"] = self.reading.to_dict()
        return out


@dataclass
class Feed:
    """What the agencies say, for the references that name them.

    ``fetch`` is injected so the readers can be exercised against the agencies'
    own recorded responses without a network, which is how the tests for this
    package have been written from the start: a parser tested against invented
    JSON tests the invention.
    """

    fetch: Callable[[str], tuple[bytes, str]] = quake.fetch
    minimum: float = FLOOR_MAGNITUDE
    #: Sources that failed on the last visit, with what they said. Kept so an
    #: operator asking why a policy has not moved gets an answer that names the
    #: source and the error rather than a silence.
    trouble: dict[str, str] = field(default_factory=dict)

    # -- asking -----------------------------------------------------------

    def _ask(self, source: str, url: str,
             read: Callable[[bytes, str], list[Observation]]) -> list[Observation]:
        try:
            body, final = self.fetch(url)
        except Exception as error:                      # noqa: BLE001 - reported
            self.trouble[source] = f"{type(error).__name__}: {error}"
            return []
        try:
            seen = read(body, final)
        except Exception as error:                      # noqa: BLE001 - reported
            self.trouble[source] = f"unreadable: {type(error).__name__}: {error}"
            return []
        self.trouble.pop(source, None)
        return seen

    def earthquake(self, *, latitude: float, longitude: float, radius_km: float,
                   since: float, until: float, index_field: str = "max_magnitude",
                   ) -> Reading:
        """The largest event in the circle and the window, as the agencies have it.

        The primary is the one the rulebook names, not the one that is easiest
        to reach: inside Türkiye that is AFAD, the national network, and the
        contract on the buyer's policy says so. Where no national network is
        read yet, USGS is the primary and the rulebook says that too. A
        protocol whose code and whose contract name different primaries has
        not got a contract.

        The others are read to check it, never to average with it: the mean of
        two official magnitudes is a third number no agency published and
        nobody can be pointed at.
        """
        usgs_field = "mmi" if index_field == "mmi" else "magnitude"
        seen: list[Observation] = self._ask(
            "USGS",
            quake.usgs_query(latitude=latitude, longitude=longitude,
                             radius_km=max(radius_km, 1.0), since=since,
                             until=until, minimum=self.minimum),
            lambda body, url: quake.read_usgs(body, url, field=usgs_field),
        )

        if index_field != "mmi":
            # Shaking is estimated by USGS's own map; EMSC and AFAD publish
            # magnitudes and would be answering a different question.
            seen += self._ask(
                "EMSC",
                quake.emsc_query(latitude=latitude, longitude=longitude,
                                 radius_km=max(radius_km, 1.0), since=since,
                                 until=until, minimum=self.minimum),
                quake.read_emsc,
            )
            if _in_turkiye(latitude, longitude):
                afad = self._ask(
                    "AFAD",
                    quake.afad_query(since=since, until=until, minimum=self.minimum),
                    quake.read_afad,
                )
                # AFAD answers for the whole country, so the circle has to be
                # applied here; the others were asked for it.
                seen += [o for o in afad
                         if _km(latitude, longitude, o) <= max(radius_km, 1.0)]

        primary = self.primary_for(latitude, longitude, index_field)
        group = largest(seen)
        if not group:
            return Reading(0.0, "magnitude" if index_field != "mmi" else "intensity (MMI)",
                           0.0, False, self._silence(), (), 0.0, primary)
        return read_from(group, peril="earthquake", primary=primary)

    @staticmethod
    def primary_for(latitude: float, longitude: float, index_field: str) -> str:
        """Which source settles, as the policy's own rulebook names it.

        Shaking is the exception and is not a jurisdiction question: MMI at an
        address is USGS's own estimate, and no other source here publishes the
        same quantity.
        """
        if index_field == "mmi":
            return "USGS"
        return "AFAD" if _in_turkiye(latitude, longitude) else "USGS"

    def _silence(self) -> str:
        if self.trouble:
            named = ", ".join(f"{k} ({v})" for k, v in sorted(self.trouble.items()))
            return f"no reading: {named}"
        return "the sources answered and reported nothing in this window"

    # -- writing ----------------------------------------------------------

    def poll(self, chain: Any, *, now: float | None = None,
             references: Iterable[str] | None = None) -> list[Attestation]:
        """Ask about every measured reference on the chain, and write what holds.

        Nothing here decides whether a policy pays. It writes the reading, and
        the chain's own validator round, aggregator and ladder do what they
        already did for a reading the simulation produced. That is the point:
        the only thing this changes is where the number comes from.
        """
        now = time.time() if now is None else now
        out: list[Attestation] = []
        wanted: Sequence[str]
        if references is not None:
            wanted = list(references)
        else:
            with chain.lock:
                wanted = [r for r in chain.readings if is_measured(r)]

        for reference in wanted:
            reading = chain.readings.get(reference)
            if reading is None:
                continue
            circle = circle_of(reference)
            if circle is None:
                out.append(Attestation(reference, field_of(reference), False,
                                       "this reference names no circle to ask about"))
                continue
            latitude, longitude, radius = circle
            index_field = field_of(reference)
            # From the last time this reference was actually read, so a window
            # is never skipped and a restart does not lose one.
            since = float(getattr(reading, "measured_through", 0.0) or 0.0)
            if since <= 0.0:
                since = now - FIRST_LOOK_DAYS * 86400

            got = self.earthquake(
                latitude=latitude, longitude=longitude, radius_km=radius,
                since=since, until=now, index_field=index_field,
            )
            # The window closes only when somebody actually answered. A visit
            # that reached nobody must be retried over the same window, or a
            # source being down for an hour would silently erase that hour.
            if not self.trouble:
                reading.measured_through = now
            if not got.observations:
                out.append(Attestation(reference, index_field, False, got.why))
                continue
            if not got.settles:
                # The sources are further apart than this peril settles within.
                # Writing either of them would be choosing, and choosing is the
                # thing a parametric policy promises nobody does.
                out.append(Attestation(reference, index_field, False, got.why,
                                       reading=got))
                continue

            standing = float(reading.fields.get(index_field, 0.0) or 0.0)
            if got.value <= standing:
                out.append(Attestation(
                    reference, index_field, False,
                    f"nothing larger than the {standing:g} already standing",
                    value=got.value, reading=got))
                continue

            chain.attest(reference, index_field, round(got.value, 2), final=False)
            out.append(Attestation(reference, index_field, True, got.why,
                                   value=got.value, reading=got))
        return out
