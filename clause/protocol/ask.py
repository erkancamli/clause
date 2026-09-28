"""Answering a question about the world from what a source published.

This protocol settles policies by pointing a condition at a primary source and
reading what it says. That is the whole claim, and until now the only way to
watch it happen was to buy a policy and wait for the weather.

So the same machinery answers a question nobody has any money on. A person
writes down what they want to know, the protocol reads the source, and the
answer comes back with everything needed to go and check it: which source,
which record, what it said, when the world did the thing, when the source
first said so, and when we asked. Three different times, and confusing them is
how a question gets answered against the wrong clock.

**This is not a settlement and it is not a wager.** No money is staked on
these answers and none is paid on them. A prediction market would be the
obvious thing to build on top and it is the one thing this will not become:
what separates insurance from a bet is that the buyer has something actually
at risk, and this protocol's own contract refuses cover where they do not. A
question with a stake on it has no such thing behind it. What is shared with a
prediction market is the useful half -- that the answer points at a primary
source rather than at an opinion -- and that half is here without the stake.

Every function in this module is given the source's records rather than
fetching them, so the answers are tested against fixed inputs and no test
needs the network to say whether a reading was read correctly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

#: How far off a question may be before it is not about today any more. A feed
#: that has gone stale answers about a world that has moved on, and answering
#: anyway is worse than saying nothing.
STALE_AFTER_SECONDS = 6 * 3600.0


class BadQuestion(ValueError):
    """A question the protocol cannot answer as asked."""


@dataclass(frozen=True, slots=True)
class Answer:
    """What the source said, and enough to go and check it.

    ``verdict`` is the answer to the question as asked. ``reading`` is the
    figure it was decided on, which is the part a reader should argue with; a
    verdict without the figure beside it is an opinion wearing a number's
    clothes.
    """

    question: str
    verdict: bool
    reading: float | None
    unit: str
    threshold: float
    source: str
    url: str
    measured_at: float = 0.0
    retrieved_at: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)
    #: Set when the source answered, but not about a recent enough world.
    stale: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "verdict": self.verdict,
            "reading": self.reading,
            "unit": self.unit,
            "threshold": self.threshold,
            "source": self.source,
            "url": self.url,
            "measured_at": self.measured_at,
            "retrieved_at": self.retrieved_at,
            "stale": self.stale,
            "detail": self.detail,
        }


def _finite(value: Any, what: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise BadQuestion(f"{what} must be a number") from error
    if not math.isfinite(number):
        raise BadQuestion(f"{what} must be a number")
    return number


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance, the same way the hazard model measures it."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def quake(
    items: Sequence[dict[str, Any]],
    *,
    latitude: float,
    longitude: float,
    radius_km: float,
    magnitude: float,
    place: str = "",
    window: str = "week",
    retrieved_at: float = 0.0,
    now: float = 0.0,
) -> Answer:
    """Whether the source recorded a large enough event close enough.

    The largest qualifying event is the one reported, not the nearest and not
    the first. A question asked about magnitude is answered with the biggest
    magnitude that met it, because that is the figure a reader would go and
    look up, and reporting a smaller one that also qualified invites them to
    conclude the protocol missed the real event.
    """
    radius_km = _finite(radius_km, "radius")
    magnitude = _finite(magnitude, "magnitude")
    if not 1.0 <= radius_km <= 1000.0:
        raise BadQuestion("the radius has to be between 1 and 1000 km")
    if not 0.0 <= magnitude <= 10.0:
        raise BadQuestion("the magnitude has to be between 0 and 10")

    if window not in ("day", "week"):
        raise BadQuestion("the source is read over the past day or the past week")
    where = place or f"{latitude:.3f}, {longitude:.3f}"
    # The window belongs in the question. Without it the answer is "no
    # earthquake near you", which reads as a fact about the place rather than
    # about the last few days of it, and the source only ever knew the latter.
    question = (
        f"Did an earthquake of at least M{magnitude:g} happen "
        f"within {radius_km:g} km of {where} in the past {window}?"
    )

    best: dict[str, Any] | None = None
    near = 0
    for item in items:
        try:
            lat, lon = float(item["latitude"]), float(item["longitude"])
            mag = float(item["magnitude"])
        except (KeyError, TypeError, ValueError):
            continue  # a record we cannot read is not a record of nothing
        away = _km(latitude, longitude, lat, lon)
        if away > radius_km:
            continue
        near += 1
        item = dict(item, distance_km=round(away, 1))
        if mag >= magnitude and (best is None or mag > float(best["magnitude"])):
            best = item

    if best is None:
        return Answer(
            question=question, verdict=False, reading=None, unit="Mw",
            threshold=magnitude, source="USGS", url="https://earthquake.usgs.gov/",
            retrieved_at=retrieved_at,
            detail={"events_in_radius": near, "radius_km": radius_km,
                    "place": where, "window": window},
            stale=_is_stale(retrieved_at, now),
        )
    return Answer(
        question=question, verdict=True, reading=float(best["magnitude"]), unit="Mw",
        threshold=magnitude, source="USGS",
        url=str(best.get("url") or "https://earthquake.usgs.gov/"),
        measured_at=float(best.get("at") or 0.0), retrieved_at=retrieved_at,
        detail={
            "events_in_radius": near, "radius_km": radius_km, "place": where,
            "window": window, "event": best.get("place", ""), "distance_km": best.get("distance_km"),
            "depth_km": best.get("depth_km"), "record_id": best.get("id", ""),
        },
        stale=_is_stale(retrieved_at, now),
    )


#: What the weather feed calls each thing this can be asked about, and the unit
#: the question is written in. Kept here rather than in the endpoint because it
#: is part of what the answer means, not part of how it is served.
WEATHER_FIELDS = {
    "wind": ("gust_kmh", "km/h"),
    "rain": ("rain_mm", "mm"),
}


def weather(
    items: Sequence[dict[str, Any]],
    *,
    place: str,
    measure: str,
    threshold: float,
    retrieved_at: float = 0.0,
    now: float = 0.0,
) -> Answer:
    """Whether today's figure for a place passed the line the question drew."""
    if measure not in WEATHER_FIELDS:
        raise BadQuestion("ask about wind or rain")
    threshold = _finite(threshold, "threshold")
    if threshold < 0:
        raise BadQuestion("the threshold cannot be below zero")
    field_name, unit = WEATHER_FIELDS[measure]

    row = next((i for i in items if str(i.get("place", "")).casefold() == place.casefold()), None)
    if row is None:
        raise BadQuestion("this source does not publish a figure for that place")

    question = (
        f"Did today's wind at {row['place']} reach {threshold:g} km/h?"
        if measure == "wind"
        else f"Did today's rain at {row['place']} reach {threshold:g} mm?"
    )
    value = row.get(field_name)
    if value is None:
        # The source answered and had nothing for this field. That is not a
        # reading of zero, and a question answered "no" on a missing figure is
        # the worst of both: wrong, and confidently.
        raise BadQuestion("this source published no such figure for that place today")
    reading = _finite(value, "the source's figure")
    return Answer(
        question=question, verdict=reading >= threshold, reading=reading, unit=unit,
        threshold=threshold, source="Open-Meteo", url="https://open-meteo.com/",
        retrieved_at=retrieved_at,
        detail={
            "place": row.get("place", ""), "measure": measure,
            "latitude": row.get("latitude"), "longitude": row.get("longitude"),
            "sky": row.get("sky", ""),
        },
        stale=_is_stale(retrieved_at, now),
    )


def delays(
    items: Sequence[dict[str, Any]],
    *,
    airport: str,
    count: float,
    retrieved_at: float = 0.0,
    now: float = 0.0,
) -> Answer:
    """Whether an airport has at least this many departures running late.

    Asked of the feed the way the feed is written. It reports airports with
    departures already 45 minutes late or more, and carries a handful of the
    flight numbers under each; it is not a timetable, so it cannot say whether
    one named flight left on time. A question shaped "is flight TK1 late"
    would refuse for nearly every flight ever asked about, and a feature that
    refuses is worse than one that was never offered: the reader concludes the
    protocol cannot read flights at all, when what it cannot do is answer that
    question from this source.
    """
    count = _finite(count, "the number of flights")
    if not 1 <= count <= 500:
        raise BadQuestion("ask about between 1 and 500 flights")
    wanted = "".join(airport.split()).upper()
    if not 3 <= len(wanted) <= 4 or not wanted.isalpha():
        raise BadQuestion("write the airport as its code, like IST")

    row = next((i for i in items
                if str(i.get("airport", "")).upper() == wanted), None)
    question = (
        f"Are at least {count:g} departures from {wanted} "
        f"running 45 minutes late or more?"
    )
    if row is None:
        # Nothing to report is a real answer here, and a different one from
        # "we could not ask": the feed covers every airport it saw, so an
        # airport it does not name had no departure late enough to be in it.
        return Answer(
            question=question, verdict=False, reading=0.0, unit="flights",
            threshold=count, source="AirLabs", url="",
            retrieved_at=retrieved_at,
            detail={"airport": wanted, "airports_reporting": len(items)},
            stale=_is_stale(retrieved_at, now),
        )
    late = _finite(row.get("count", 0), "the number this feed reports")
    return Answer(
        question=question, verdict=late >= count, reading=late, unit="flights",
        threshold=count, source="AirLabs", url="", retrieved_at=retrieved_at,
        detail={
            "airport": wanted, "airports_reporting": len(items),
            "worst_minutes": row.get("max_minutes"),
            "average_minutes": row.get("average_minutes"),
            "flights": [str(f.get("flight", "")) for f in (row.get("flights") or [])][:4],
        },
        stale=_is_stale(retrieved_at, now),
    )


def _is_stale(retrieved_at: float, now: float) -> bool:
    if not retrieved_at or not now:
        return False
    return (now - retrieved_at) > STALE_AFTER_SECONDS


def answerable() -> list[dict[str, Any]]:
    """What can be asked, for a page that has to draw the form.

    Written here rather than in the page, so a question shape the protocol
    stops being able to answer disappears from the form by itself. It listed a
    "flight" shape for one afternoon after the flight question became a
    question about an airport's departures, which would have drawn a chip that
    refused every question asked through it.
    """
    return [
        {"kind": "quake", "asks": "point", "unit": "Mw", "source": "USGS",
         "defaults": {"threshold": 4.0, "radius_km": 300.0}},
        {"kind": "wind", "asks": "place", "unit": "km/h", "source": "Open-Meteo",
         "defaults": {"threshold": 60.0}},
        {"kind": "rain", "asks": "place", "unit": "mm", "source": "Open-Meteo",
         "defaults": {"threshold": 20.0}},
        {"kind": "delays", "asks": "airport", "unit": "flights", "source": "AirLabs",
         "defaults": {"threshold": 3.0}},
    ]
