"""Deciding that three agencies are talking about the same earthquake.

This looked like a detail and is not. On the morning of 6 February 2023 there
was a magnitude 7.5 at 10:24:47 and a magnitude 6.0 at 10:26:48, two minutes
and a different fault apart. Any window wide enough to absorb the agencies'
disagreement about *when* the first one happened is wide enough to swallow the
second one, and a settlement that reads the wrong earthquake pays the wrong
person the wrong amount with perfect provenance.

Time alone cannot separate them, so location is used as well. The three
agencies put the Pazarcik epicentre at 37.226/37.014 (USGS), 37.277/37.040
(AFAD) and 37.170/37.080 (EMSC) -- as much as twelve kilometres apart, because
an epicentre is itself an estimate. So the rule is tight in time and generous
in space: agencies disagree about where by kilometres and about when by
seconds, and two separate earthquakes are almost never within a minute of each
other at the same place.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from .observation import Observation

#: Two readings are the same event within this many seconds of each other.
#: The agencies' origin times for one earthquake differ by well under a second;
#: the gap is for clock and rounding differences, not for disagreement.
SAME_SECONDS = 60.0
#: And within this many kilometres. Wide, because an epicentre is an estimate
#: and the three agencies located the same earthquake twelve kilometres apart.
SAME_KM = 60.0


def _km(a: Observation, b: Observation) -> float:
    """Great circle distance. Not the flat approximation: these are events
    anywhere on earth, and a flat one is wrong by a third at high latitude."""
    if not (a.latitude or a.longitude) or not (b.latitude or b.longitude):
        return 0.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    d = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(d)))


def same_event(a: Observation, b: Observation, *, seconds: float = SAME_SECONDS,
               km: float = SAME_KM) -> bool:
    return abs(a.measured_at - b.measured_at) <= seconds and _km(a, b) <= km


def events(observations: Iterable[Observation], *, seconds: float = SAME_SECONDS,
           km: float = SAME_KM) -> list[list[Observation]]:
    """Every reading grouped into the physical event it is about.

    Groups are returned with the largest value first, because what a cover
    reads is the largest event in its window, and within a group the readings
    are ordered by source name so a page prints them the same way twice.
    """
    left = sorted(observations, key=lambda o: o.measured_at)
    out: list[list[Observation]] = []
    for one in left:
        for group in out:
            if any(same_event(one, other, seconds=seconds, km=km) for other in group):
                group.append(one)
                break
        else:
            out.append([one])
    for group in out:
        group.sort(key=lambda o: o.source)
    return sorted(out, key=lambda g: -max(o.value for o in g))


def largest(observations: Iterable[Observation], *, seconds: float = SAME_SECONDS,
            km: float = SAME_KM) -> Sequence[Observation]:
    """The readings for the biggest event in the window, or nothing.

    "Biggest" is by the largest value any source gives it, not by the primary's
    value: if one agency calls an event 7.6 and another 7.5, it is the same
    event and it is the one that matters either way.
    """
    grouped = events(observations, seconds=seconds, km=km)
    return grouped[0] if grouped else ()
