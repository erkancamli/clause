"""One source's answer, and everything needed to check it later.

The fields are deliberately more than the number. A settlement that can only
be verified by asking us again is not verifiable at all; these are what let
somebody else go to the same source, send the same query, and see whether they
get the same answer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


def digest_of(body: bytes) -> str:
    """A short fingerprint of exactly the bytes a source sent.

    Short because it is printed on a page a person reads, and a full SHA-256 is
    sixty-four characters of noise to them; sixteen hex characters is still
    sixty-four bits, which nobody is going to collide by accident and nobody
    gains anything by colliding on purpose.
    """
    return hashlib.sha256(body).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Observation:
    """What one source said, once.

    ``measured_at`` is when the world did the thing. ``published_at`` is when
    the source first said so. ``retrieved_at`` is when we asked. They are three
    different times and confusing them is how a waiting period gets evaluated
    against the wrong clock.
    """

    source: str
    value: float
    unit: str
    measured_at: float
    retrieved_at: float
    url: str
    digest: str
    record_id: str = ""
    published_at: float = 0.0
    # What the source itself calls the quantity: USGS reports mww, mb, ms, and
    # they are not the same scale. A magnitude without its type is half a fact.
    scale: str = ""
    # The source's own revision marker, where it has one. AFAD carries
    # isEventUpdate and lastUpdateDate; USGS carries updated and status.
    revised_at: float = 0.0
    reviewed: bool = False
    # Where the source puts it. Needed because matching three agencies'
    # readings to one physical event cannot be done on time alone: on the
    # morning of 6 February 2023 there was a magnitude 7.5 at 10:24 and a
    # magnitude 6.0 at 10:26, and a window wide enough to absorb the agencies'
    # disagreement about the second is wide enough to swallow the second
    # earthquake.
    latitude: float = 0.0
    longitude: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {"source": self.source, "value": self.value, "unit": self.unit,
               "measured_at": self.measured_at, "retrieved_at": self.retrieved_at,
               "url": self.url, "digest": self.digest}
        for name in ("record_id", "published_at", "scale", "revised_at",
                     "latitude", "longitude", "note"):
            if getattr(self, name):
                out[name] = getattr(self, name)
        out["reviewed"] = self.reviewed
        return out

    def said(self) -> str:
        return f"{self.source} says {self.value:g} {self.unit}"


@dataclass(frozen=True, slots=True)
class Reading:
    """What the protocol takes as the reading, and everything it rests on.

    The value is one number because a ladder needs one number. Everything that
    made it one number travels with it: which sources were asked, what each
    said, how far apart they were, and whether that was far enough to stop.
    """

    value: float
    unit: str
    measured_at: float
    settles: bool
    why: str
    observations: tuple[Observation, ...] = field(default_factory=tuple)
    spread: float = 0.0
    primary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "unit": self.unit, "measured_at": self.measured_at,
                "settles": self.settles, "why": self.why, "spread": round(self.spread, 4),
                "primary": self.primary,
                "observations": [o.to_dict() for o in self.observations]}
