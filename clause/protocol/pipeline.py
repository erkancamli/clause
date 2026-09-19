"""The policy pipeline: rules every movement of value passes before it runs.

Rialo's Latch puts a policy pipeline in front of a credential. Every request
passes the filters in order, the first to deny stops it, and a caller can ask
for a decision without acting, so an agent hears "that would be refused"
instead of a 403 after the fact. Clause already has two gates of its own: the
compliance engine answers whether this cover may lawfully be written here and
by whom, from the registry; the eligibility engine answers whether the buyer
has proved what the cover needs. Neither can say "not this address, whatever
it proves" or "nothing on this peril this week". This module can, and it is
the one place a decision the operator takes enters the path of money.

Two rules ship.

  denylist     an address on this protocol, a wallet on another chain, a
               country, or a payout destination. Refused at every stage: a
               purchase, a payout leaving, a cashout, a deposit, a wallet
               being linked. The screening a verifier attests to is one bit
               about one address on one day; this is the operator's own list,
               written when a regulator names an address, a partner reports a
               fraud, or a court orders it, and it holds until it is lifted.

  moratorium   a peril, in a country or inside a circle, until a date or
               until lifted. New business only: cover already in force pays.
               After a large earthquake an insurer stops writing on that fault
               until the sequence has settled, because a policy sold the day
               after a mainshock is priced on a hazard that is not the one it
               faces. The pricing engine cannot know an event happened this
               morning; the operator can, and this is where they say so.

Every entry carries a reason, who wrote it and when; a lifted entry stays in
the book with who lifted it and when. A decision is recorded whether it
allowed or refused, so a refusal can be read back later without a log file.

The same question is asked at ``POST /api/policy/check`` without acting. What
comes back is the decision the real stage would take, on the same rules, at
that moment; nothing is reserved and nothing is promised, because the rules
are re-evaluated on every execution, which is the property Rialo's compliance
model is built around.
"""

from __future__ import annotations

import math
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from .address import canonical, is_address

__all__ = [
    "Action", "Decision", "Entry", "Match", "PolicyError", "PolicyPipeline",
    "Rule", "STAGES", "normalise",
]

# Where a decision is taken. A purchase is any way cover comes to be written:
# by hand, by application, by a standing instruction, by a partner, by Rider.
STAGES = ("purchase", "settlement", "cashout", "funding", "link")

# How many decisions are kept for the operator to read back. In memory: a
# decision is a fact about a moment, and the entries that produced it are what
# is kept on disk.
DECISIONS_KEPT = 500


class PolicyError(ValueError):
    """An entry that cannot be written, or an action that cannot be described."""


class Rule(str, Enum):
    DENYLIST = "denylist"
    MORATORIUM = "moratorium"


class Match(str, Enum):
    """What a denylist entry names."""

    ADDRESS = "address"          # an account on this protocol
    WALLET = "wallet"            # a wallet on another chain
    COUNTRY = "country"          # a two letter code
    DESTINATION = "destination"  # a bank account, a mobile wallet or a wallet a payout goes to


def normalise(match: Match, value: str) -> str:
    """The form an entry and an action agree on, so a match is a comparison."""
    text = " ".join(str(value or "").split())
    if not text:
        raise PolicyError("give what the entry names")
    if match is Match.ADDRESS:
        if not is_address(text):
            raise PolicyError("that is not an address on this protocol")
        return canonical(text)
    if match is Match.COUNTRY:
        code = text.upper()
        if len(code) != 2 or not code.isalpha():
            raise PolicyError("a country is a two letter code")
        return code
    if match is Match.WALLET:
        # An Ethereum address is case insensitive; base58 addresses are not.
        return text.lower() if text.startswith("0x") else text
    # A destination: an IBAN with its spaces removed, a phone with its
    # punctuation removed, a wallet as it is written.
    if text.startswith("+"):
        return "+" + "".join(ch for ch in text[1:] if ch.isdigit())
    if text[:2].isalpha() and text[2:4].isdigit():
        return text.replace(" ", "").upper()
    return text.lower() if text.startswith("0x") else text


@dataclass
class Entry:
    """One line in the operator's book: what is refused, why, by whom."""

    entry_id: str
    rule: Rule
    reason: str
    added_by: str
    added_at: float
    # denylist
    match: Match | None = None
    value: str = ""
    # moratorium
    peril: str = ""
    country: str = ""
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None
    # both
    until: float | None = None       # None: until lifted
    lifted_at: float | None = None
    lifted_by: str = ""
    lift_note: str = ""

    def live(self, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if self.lifted_at is not None:
            return False
        return self.until is None or now < self.until

    def to_dict(self, *, private: bool = False) -> dict[str, Any]:
        """The entry as the operator sees it, or as the public may: a
        moratorium is public information (a buyer is told why nothing can be
        written here this week); a denylist entry never is."""
        out: dict[str, Any] = {
            "entry_id": self.entry_id, "rule": self.rule.value, "reason": self.reason,
            "added_at": self.added_at, "until": self.until,
            "live": self.live(), "lifted_at": self.lifted_at,
        }
        if self.rule is Rule.MORATORIUM:
            out.update({"peril": self.peril, "country": self.country or None,
                        "place": ({"latitude": self.latitude, "longitude": self.longitude,
                                   "radius_km": self.radius_km} if self.latitude is not None else None)})
        if private:
            out.update({"added_by": self.added_by, "lifted_by": self.lifted_by, "lift_note": self.lift_note})
            if self.rule is Rule.DENYLIST:
                out.update({"match": self.match.value if self.match else None, "value": self.value})
        return out


@dataclass(frozen=True, slots=True)
class Action:
    """What is about to happen, described just enough for the rules to read."""

    stage: str
    address: str = ""
    countries: tuple[str, ...] = ()
    peril: str = ""
    limit: float = 0.0
    amount: float = 0.0
    destination: str = ""
    wallet: str = ""
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise PolicyError(f"unknown stage {self.stage!r}; stages are {', '.join(STAGES)}")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"stage": self.stage}
        if self.address:
            out["address"] = self.address
        if self.countries:
            out["countries"] = list(self.countries)
        if self.peril:
            out["peril"] = self.peril
        if self.limit:
            out["limit"] = round(self.limit, 2)
        if self.amount:
            out["amount"] = round(self.amount, 2)
        if self.destination:
            out["destination"] = self.destination
        if self.wallet:
            out["wallet"] = self.wallet
        if self.latitude is not None and self.longitude is not None:
            out["place"] = {"latitude": self.latitude, "longitude": self.longitude}
        return out


@dataclass(frozen=True, slots=True)
class Decision:
    """What the pipeline said, and which rule said it."""

    allowed: bool
    stage: str
    reasons: tuple[str, ...]
    evaluated: tuple[str, ...]
    at: float
    rule: str = ""
    entry_id: str = ""
    action: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "decision": "allow" if self.allowed else "deny",
            "stage": self.stage,
            "reasons": list(self.reasons),
            "denied_by": ({"rule": self.rule, "entry_id": self.entry_id} if not self.allowed else None),
            "evaluated": list(self.evaluated),
            "at": self.at,
            "action": dict(self.action),
        }


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


class PolicyPipeline:
    """The rules, in the order they run; the book of entries; the decisions."""

    ORDER = (Rule.DENYLIST, Rule.MORATORIUM)

    def __init__(self, entries: Iterable[Entry] = ()) -> None:
        self.entries: dict[str, Entry] = {e.entry_id: e for e in entries}
        self.decisions: deque[Decision] = deque(maxlen=DECISIONS_KEPT)
        self.lock = threading.RLock()

    # -- writing the book -------------------------------------------------

    def deny(self, *, match: Match | str, value: str, reason: str, by: str,
             until: float | None = None, now: float | None = None) -> Entry:
        now = time.time() if now is None else now
        match = Match(match)
        text = " ".join(str(reason or "").split())
        if len(text) < 3:
            raise PolicyError("say why: a refusal nobody can be asked about is not a decision")
        if until is not None and until <= now:
            raise PolicyError("an entry that ends in the past would refuse nothing")
        entry = Entry(
            entry_id="RL-" + secrets.token_hex(4).upper(), rule=Rule.DENYLIST, reason=text[:300],
            added_by=(by or "operator")[:80], added_at=now, match=match,
            value=normalise(match, value), until=until,
        )
        with self.lock:
            for other in self.entries.values():
                if (other.rule is Rule.DENYLIST and other.match is match
                        and other.value == entry.value and other.live(now=now)):
                    raise PolicyError(f"already refused under {other.entry_id}")
            self.entries[entry.entry_id] = entry
        return entry

    def pause(self, *, peril: str, reason: str, by: str, country: str = "",
              latitude: float | None = None, longitude: float | None = None,
              radius_km: float | None = None, until: float | None = None,
              now: float | None = None) -> Entry:
        """No new cover on a peril, in a country or inside a circle, for a while."""
        now = time.time() if now is None else now
        peril = str(peril or "").strip()
        if not peril:
            raise PolicyError("name the peril, or * for every peril")
        text = " ".join(str(reason or "").split())
        if len(text) < 3:
            raise PolicyError("say why: a refusal nobody can be asked about is not a decision")
        if until is not None and until <= now:
            raise PolicyError("an entry that ends in the past would refuse nothing")
        code = str(country or "").strip().upper()
        if code and (len(code) != 2 or not code.isalpha()):
            raise PolicyError("a country is a two letter code")
        place = (latitude, longitude, radius_km)
        if any(v is not None for v in place):
            if any(v is None for v in place):
                raise PolicyError("a place is a latitude, a longitude and a radius in km")
            lat, lon, km = float(latitude), float(longitude), float(radius_km)  # type: ignore[arg-type]
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise PolicyError("that is not a coordinate")
            if not 0 < km <= 2000:
                raise PolicyError("a radius between 0 and 2000 km")
            latitude, longitude, radius_km = round(lat, 4), round(lon, 4), round(km, 1)
        entry = Entry(
            entry_id="RL-" + secrets.token_hex(4).upper(), rule=Rule.MORATORIUM, reason=text[:300],
            added_by=(by or "operator")[:80], added_at=now, peril=peril[:32], country=code,
            latitude=latitude, longitude=longitude, radius_km=radius_km, until=until,
        )
        with self.lock:
            self.entries[entry.entry_id] = entry
        return entry

    def lift(self, entry_id: str, *, by: str, note: str = "", now: float | None = None) -> Entry:
        now = time.time() if now is None else now
        with self.lock:
            entry = self.entries.get(entry_id)
            if entry is None:
                raise PolicyError("no such entry")
            if entry.lifted_at is not None:
                raise PolicyError(f"already lifted by {entry.lifted_by}")
            entry.lifted_at = now
            entry.lifted_by = (by or "operator")[:80]
            entry.lift_note = " ".join(str(note or "").split())[:300]
            return entry

    def live(self, *, now: float | None = None) -> list[Entry]:
        with self.lock:
            return [e for e in self.entries.values() if e.live(now=now)]

    # -- deciding ---------------------------------------------------------

    def check(self, action: Action, *, now: float | None = None) -> Decision:
        """Run the rules in order; the first to deny stops it. Recorded."""
        now = time.time() if now is None else now
        evaluated: list[str] = []
        with self.lock:
            live = [e for e in self.entries.values() if e.live(now=now)]
            for rule in self.ORDER:
                evaluated.append(rule.value)
                hit, reason = self._apply(rule, action, [e for e in live if e.rule is rule])
                if hit is not None:
                    decision = Decision(False, action.stage, (reason,), tuple(evaluated), now,
                                        rule=rule.value, entry_id=hit.entry_id, action=action.to_dict())
                    self.decisions.append(decision)
                    return decision
            decision = Decision(True, action.stage, ("no rule refuses this",), tuple(evaluated), now,
                                action=action.to_dict())
            self.decisions.append(decision)
            return decision

    def refusal(self, action: Action, *, now: float | None = None) -> str | None:
        """The reason, or None: for the places that only need a sentence."""
        decision = self.check(action, now=now)
        return None if decision.allowed else "; ".join(decision.reasons)

    def _apply(self, rule: Rule, action: Action, entries: list[Entry]) -> tuple[Entry | None, str]:
        if rule is Rule.DENYLIST:
            return self._denylist(action, entries)
        return self._moratorium(action, entries)

    @staticmethod
    def _denylist(action: Action, entries: list[Entry]) -> tuple[Entry | None, str]:
        address = canonical(action.address) if action.address and is_address(action.address) else action.address
        countries = tuple(c.upper() for c in action.countries if c)
        wallet = normalise(Match.WALLET, action.wallet) if action.wallet else ""
        destination = normalise(Match.DESTINATION, action.destination) if action.destination else ""
        for entry in entries:
            if entry.match is Match.ADDRESS and address and entry.value == address:
                return entry, "this address is refused by the operator's policy"
            if entry.match is Match.COUNTRY and entry.value in countries:
                return entry, f"nothing is written for, paid to or taken from {entry.value} under the operator's policy"
            if entry.match is Match.WALLET and (
                    (wallet and entry.value == wallet) or (destination and entry.value == destination)):
                return entry, "that wallet is refused by the operator's policy"
            if entry.match is Match.DESTINATION and (
                    (destination and entry.value == destination) or (wallet and entry.value == wallet)):
                return entry, "that destination is refused by the operator's policy"
        return None, ""

    @staticmethod
    def _moratorium(action: Action, entries: list[Entry]) -> tuple[Entry | None, str]:
        # New business only. Cover already in force is paid on its terms; a
        # moratorium is about what is written, not about what is owed.
        if action.stage != "purchase":
            return None, ""
        countries = tuple(c.upper() for c in action.countries if c)
        for entry in entries:
            if entry.peril not in ("*", action.peril):
                continue
            if entry.country and entry.country not in countries:
                continue
            if entry.latitude is not None:
                if action.latitude is None or action.longitude is None:
                    continue
                if _distance_km((entry.latitude, entry.longitude or 0.0),
                                (action.latitude, action.longitude)) > float(entry.radius_km or 0.0):
                    continue
            what = "cover" if entry.peril == "*" else f"{entry.peril.replace('_', ' ')} cover"
            where = (f" within {entry.radius_km:g} km of {entry.latitude:.2f}, {entry.longitude:.2f}"
                     if entry.latitude is not None else f" in {entry.country}" if entry.country else "")
            when = (f" until {time.strftime('%d %B %Y', time.gmtime(entry.until))}"
                    if entry.until else " until the operator lifts it")
            return entry, f"no new {what} is being written{where}{when}: {entry.reason}"
        return None, ""

    # -- describing -------------------------------------------------------

    def describe(self, *, now: float | None = None) -> dict[str, Any]:
        """What the pipeline is, for anyone: the rules in order, what each
        reads, how many entries are live, and every live moratorium in full.
        Never a denylist entry."""
        live = self.live(now=now)
        return {
            "rules": [
                {"rule": Rule.DENYLIST.value, "order": 1,
                 "reads": ["address", "countries", "wallet", "destination"],
                 "stages": list(STAGES),
                 "live": sum(1 for e in live if e.rule is Rule.DENYLIST),
                 "what": ("an address, a wallet on another chain, a country or a payout "
                          "destination the operator has refused; holds until lifted")},
                {"rule": Rule.MORATORIUM.value, "order": 2,
                 "reads": ["peril", "countries", "place"],
                 "stages": ["purchase"],
                 "live": sum(1 for e in live if e.rule is Rule.MORATORIUM),
                 "what": ("no new cover on a peril, in a country or inside a circle, until a "
                          "date or until lifted; cover already in force is unaffected")},
            ],
            "stages": list(STAGES),
            "moratoria": [e.to_dict() for e in live if e.rule is Rule.MORATORIUM],
            "first_to_deny_stops_it": True,
            "re_evaluated_on_every_execution": True,
        }

    def book(self, *, recent: int = 50) -> dict[str, Any]:
        """Everything, for the operator: every entry ever written, and the
        latest decisions."""
        with self.lock:
            entries = sorted(self.entries.values(), key=lambda e: e.added_at, reverse=True)
            decisions = list(self.decisions)[-recent:]
        return {
            "entries": [e.to_dict(private=True) for e in entries],
            "live": sum(1 for e in entries if e.live()),
            "decisions": [d.to_dict() for d in reversed(decisions)],
            "refused": sum(1 for d in self.decisions if not d.allowed),
        }
