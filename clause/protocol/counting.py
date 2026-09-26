"""How many, and nothing about who.

A funnel is usually built by following people: an identifier in a cookie, a
script on the page, a row per visit. None of that is possible here and none of
it is wanted. What this keeps instead is a tally: how many prices were asked
for today, how many contracts were read, how many policies were bought. Four
numbers a day, per peril.

That is a deliberate trade. A tally cannot answer "how many of the people who
asked for a price came back the next day", because it does not know that two
requests came from the same person, and there is nothing here that could be
made to know it. It can answer the question that actually decides whether a
change to the flow was worth making: of everybody who got as far as a price,
how many got as far as buying.

Three rules hold it to that.

Nothing identifying is ever passed in. The only arguments are what happened
and what kind of cover it was about, and the only thing written is a number
going up. There is no address here, no session, no IP, no user agent and no
time more precise than the day.

A day is a day in UTC, and days are kept whole. A tally that could be
rewritten backwards would be a worse record than none, so the only operation
is addition.

And the tally is not a person. Two requests from one buyer count twice and
one request from two buyers counts twice, which is the honest reading of the
number and the reason it is called a count and never a visitor.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from dataclasses import dataclass, field
from typing import Any

#: The stages a purchase passes through on the server, in order. Each is a
#: request the protocol actually receives, not a screen the page thinks it is
#: showing: what is counted is what happened.
STAGES = (
    "priced",      # a quote was asked for
    "offered",     # the companies that would write it were asked for
    "contracted",  # the contract was fetched, which happens at the last step
    "applied",     # cover was asked for, the premium held
    "bought",      # cover was written
    # Not a stage of its own: the same signed purchase arriving a second time,
    # because the first reply did not reach the buyer. It is counted because it
    # is the only visible measure of how often that happens, and one that keeps
    # climbing is a network or a proxy to look at rather than a buyer's mistake.
    "asked again",
)

#: How many days are kept. Enough to compare a month with the month before it.
KEEP_DAYS = 400


def day_of(when: float | None = None) -> str:
    """The UTC day, as yyyy-mm-dd. The finest time this module ever holds."""
    moment = time.time() if when is None else when
    return dt.datetime.fromtimestamp(moment, dt.timezone.utc).strftime("%Y-%m-%d")


@dataclass(slots=True)
class Day:
    """One day's tally. Keys are stage names, or "stage/peril"."""
    day: str
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"day": self.day, "counts": dict(self.counts)}


class Counting:
    """The tally, by day. Addition is the only thing it does."""

    def __init__(self) -> None:
        self.days: dict[str, Day] = {}
        self._lock = threading.Lock()

    def count(self, stage: str, peril: str = "", *, when: float | None = None) -> None:
        """One more of something. Never raises: a tally must not be able to
        fail a request that was otherwise fine."""
        if stage not in STAGES:
            return
        key = day_of(when)
        with self._lock:
            day = self.days.get(key)
            if day is None:
                day = self.days[key] = Day(day=key)
                self._forget_old()
            day.counts[stage] = day.counts.get(stage, 0) + 1
            if peril:
                pair = f"{stage}/{peril}"
                day.counts[pair] = day.counts.get(pair, 0) + 1

    def _forget_old(self) -> None:
        """Called under the lock, when a new day starts."""
        if len(self.days) <= KEEP_DAYS:
            return
        for old in sorted(self.days)[:-KEEP_DAYS]:
            self.days.pop(old, None)

    # -- reading ------------------------------------------------------------

    def since(self, days: int = 30) -> list[Day]:
        """The last so many days, oldest first, days with nothing left out."""
        with self._lock:
            keys = sorted(self.days)[-max(1, days):]
            return [self.days[k] for k in keys]

    def totals(self, days: int = 30) -> dict[str, int]:
        out: dict[str, int] = {}
        for day in self.since(days):
            for key, value in day.counts.items():
                out[key] = out.get(key, 0) + value
        return out

    def funnel(self, days: int = 30) -> dict[str, Any]:
        """The stages in order, and what share of the priced ones reached each.

        The share is of prices asked for, not of people: this module does not
        know what a person is. A figure above one is possible and means the
        same request was made more than once, which is a fact about requests.
        """
        totals = self.totals(days)
        priced = totals.get("priced", 0)
        rows = []
        for stage in STAGES:
            count = totals.get(stage, 0)
            rows.append({"stage": stage, "count": count,
                         "of_priced": round(count / priced, 4) if priced else None})
        return {"days": days, "stages": rows,
                "by_peril": {k: v for k, v in sorted(totals.items()) if "/" in k},
                "note": "counts of requests, not of people: nothing here identifies anybody"}
