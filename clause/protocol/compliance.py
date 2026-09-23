"""The gate: whether this cover may be written, by whom, and on what terms.

An earlier version of this module was a table of six countries. Everywhere else
was refused on the grounds that no rule had been established, which meant the
protocol's reach was a property of our documentation. That is backwards. The
question a buyer's country actually raises is not "have these authors read your
insurance code" but "is there a company licensed to issue you this policy", and
that question has an answer the software can look up: the carrier registry.

So this module has been turned inside out. It still enforces the tests that
separate insurance from a wager, because those are universal and no licence
cures them. What it no longer does is decide by itself where cover may be sold.
That is decided by who has registered, which is why the protocol now works in
any country in the world and refuses in precisely the ones where nobody has
put up a licence.

What is enforced, in order
--------------------------
  1. Insurable interest.   Is the thing insured inside the area the index
                           measures? A buyer in Ankara taking cover on an
                           Istanbul index is not insuring, they are betting on
                           someone else's earthquake. No jurisdiction anywhere
                           permits that as insurance, so this test runs first
                           and is never waived.

  2. Indemnity.            Is cover capped by what the buyer says is at risk?
                           Parametric breaks the exact link to loss by design;
                           the workable position, and the one every regulator
                           surveyed takes, is that approximation survives and
                           untethering does not. Enforced as a cap, because a
                           cap needs no adjuster.

  3. Placement.            Is a registered company licensed to issue this, in
                           this country, for this peril, to this kind of buyer,
                           settling in this asset? This is the licensing
                           question and the registry answers it.

  4. Settlement.           The asset is taken from the licence that matched,
                           not from a table. A Turkish retail policy settles in
                           lira because the carrier's licence permits lira and
                           not because this file says so, though it says so too,
                           in the notes, where a note belongs.

Disclosure is separate from refusal
-----------------------------------
The regulatory notes that used to be the gate are still here and are still
worth reading, but they are now shown rather than enforced. A buyer in Türkiye
sees why their policy comes through a licensed carrier and settles in lira,
with the statutes named. A buyer in a country nobody has researched sees no note
and is still covered, because the licence is the thing that makes it lawful and
a missing paragraph in our notes never made anyone safer.

Re-evaluated before the money leaves
------------------------------------
Rialo describes identity, privacy and compliance as a protocol level concern it
calls IPC, and the property it claims is the one this module is built around:
compliance is not assumed at setup, it is re-evaluated during each execution,
and a failure aborts the execution rather than being discovered afterwards. A
carrier whose licence lapsed, a buyer who has since been sanctioned, and a
country whose rule changed are all that case. So `recheck_at_settlement` runs
the whole thing again, against the registry as it stands at that moment.

Nothing here is legal advice, and the notes are a reading of public sources
rather than an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .carrier import Placement, Reach, Registry, Settlement

__all__ = [
    "Channel", "Settlement", "Interest", "Ruling", "ComplianceEngine",
    "NOTES", "note_for",
]


class Channel(str, Enum):
    """How cover reaches the buyer, which follows from who issued it."""

    REFUSED = "refused"
    # A licensed carrier issues the policy and the pool stands behind it as
    # capital. The ordinary case, and the structure Ensuro operates under a
    # Bermuda reinsurance licence.
    FRONTED = "fronted"
    # An index contract between informed parties. Not consumer insurance, not
    # offered to consumers, and not called insurance anywhere in the interface.
    INDEX_CONTRACT = "index_contract"
    # The operator's own licensed entity issues it. Same gate, no shortcut.
    DIRECT = "direct"


# ---------------------------------------------------------------------------
# Notes: read, not enforced
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Note:
    """What is worth telling a buyer about their own jurisdiction."""

    country: str
    name: str
    authority: str
    text: str


NOTES: dict[str, Note] = {
    "TR": Note(
        country="TR", name="Türkiye", authority="SEDDK, with the CBRT on settlement",
        text=(
            "Index cover is lawful here through a licensed insurer: the state "
            "supported drought product runs under Agricultural Insurance Law 5363 "
            "through the TARSİM pool and expressly does not assess individual "
            "loss. Writing cover without a licence is a criminal offence under "
            "Article 35 of Law 5684, and Article 1401(2) of the Commercial Code "
            "makes such a contract void and subject to the gambling provisions. "
            "Premium and claims settle in lira: the 2021 central bank regulation "
            "prohibits using crypto assets in payments, directly or indirectly."
        ),
    ),
    "DE": Note(
        country="DE", name="Germany", authority="BaFin",
        text=(
            "Distribution falls under the IDD and the carrier under Solvency II. "
            "Parametric is permissible where it answers an economic need rather "
            "than creating one, which is the insurable interest test under "
            "another name."
        ),
    ),
    "GB": Note(
        country="GB", name="United Kingdom", authority="FCA and PRA",
        text=(
            "Insurable interest is required and at least nominal loss must exist "
            "at claim time. A contract that is not insurance is likely caught as "
            "a contract for differences instead, so there is no unregulated gap "
            "to sit in."
        ),
    ),
    "IE": Note(
        country="IE", name="Ireland", authority="Central Bank of Ireland",
        text=(
            "A Solvency II carrier here may passport into the rest of the EEA on "
            "a freedom of services basis, which is why an insurance DAC is the "
            "usual European base for a parametric programme."
        ),
    ),
    "US": Note(
        country="US", name="the United States", authority="state insurance departments, and the CFTC on the derivative route",
        text=(
            "Licensing is state by state and the federal product test requires "
            "insurable interest maintained throughout, loss proven, and payment "
            "capped at that interest. Pure parametric does not meet it, so the "
            "products that work here are distributed by licensed carriers or "
            "structured as event linked derivatives under the CFTC."
        ),
    ),
    "AE": Note(
        country="AE", name="the United Arab Emirates", authority="DFSA and FSRA",
        text=(
            "The DIFC and ADGM regimes are where crypto native risk transfer is "
            "usually domiciled. Offered to professional counterparties as an "
            "index contract rather than to consumers as insurance."
        ),
    ),
    "BM": Note(
        country="BM", name="Bermuda", authority="BMA",
        text=(
            "Where this structure is licensed today. A reinsurer holding an "
            "insurance licence and a digital asset business licence may take "
            "risk with stablecoins as solvency capital, which is the layer this "
            "pool belongs at rather than the consumer facing one."
        ),
    ),
}


def note_for(country: str | None) -> Note | None:
    return NOTES.get((country or "").upper())


# ---------------------------------------------------------------------------
# What the buyer declares
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Interest:
    """What the buyer says is at risk. The difference between cover and a bet."""

    what: str               # "a house", "40 hectares of wheat", "one flight"
    country: str
    # Whether the thing at risk sits inside the area the index measures. A buyer
    # in Ankara cannot take cover on an Istanbul index and call it insurance.
    inside_trigger_area: bool
    value_at_risk: float    # what it is worth, in the settlement asset
    holder_is_professional: bool = False

    def __post_init__(self) -> None:
        if not self.what.strip():
            raise ValueError("state what is at risk")
        if self.value_at_risk <= 0:
            raise ValueError("the value at risk must be positive")
        if len(self.country) != 2 or not self.country.isalpha():
            raise ValueError("country is a two letter code")

    @property
    def reach(self) -> Reach:
        return Reach.PROFESSIONAL if self.holder_is_professional else Reach.RETAIL


@dataclass(frozen=True, slots=True)
class Ruling:
    """Whether this may be written, by whom, how, and why."""

    allowed: bool
    channel: Channel
    settlement: Settlement | None
    max_limit: float
    reasons: tuple[str, ...]
    checked_at_stage: str
    placement: Placement | None = None
    note: Note | None = None
    disclosure: tuple[str, ...] = field(default_factory=tuple)

    @property
    def carrier_id(self) -> str | None:
        best = self.placement.best if self.placement else None
        return best.carrier.carrier_id if best else None

    def to_dict(self) -> dict[str, Any]:
        best = self.placement.best if self.placement else None
        return {
            "allowed": self.allowed,
            "channel": self.channel.value,
            "settlement": self.settlement.value if self.settlement else None,
            "max_limit": round(self.max_limit, 2),
            "reasons": list(self.reasons),
            "disclosure": list(self.disclosure),
            "stage": self.checked_at_stage,
            "carrier": best.to_dict() if best else None,
            "reinsurers": (
                [
                    {"name": r.name, "domicile": r.domicile}
                    for r in self.placement.reinsurers
                ] if self.placement else []
            ),
            "jurisdiction": (
                {
                    "code": self.note.country, "name": self.note.name,
                    "authority": self.note.authority, "note": self.note.text,
                } if self.note else None
            ),
        }


class ComplianceEngine:
    """The gate, run when cover is bound and again before a payout leaves.

    Deliberately a plain object over a registry, with no hidden state: an
    auditor can read the rule, and a buyer can be shown the exact sentence that
    refused them.
    """

    def __init__(
        self, registry: Registry | None = None,
        territories: dict[str, frozenset[str] | None] | None = None,
    ) -> None:
        from .carrier import Registry

        self.registry = registry if registry is not None else Registry()
        if territories is None:
            from ..perils import REGISTRY as PERILS

            territories = {key: peril.territory for key, peril in PERILS.items()}
        # Where each peril can actually be priced. None means anywhere.
        self.territories = territories

    def priceable(self, peril: str, country: str) -> bool:
        """Whether the protocol has a model that can price this peril here.

        The other half of "open". A licence says a company may issue the policy;
        this says there is a price to put on it. Both, or the country is shut.
        """
        if peril not in self.territories:
            return False
        territory = self.territories[peril]
        return territory is None or country.upper() in territory

    def evaluate(
        self,
        *,
        interest: Interest,
        limit: float,
        peril: str,
        term_days: float = 365.0,
        asset: Settlement | None = None,
        stage: str = "purchase",
        book_capacity: float | None = None,
        now: float | None = None,
        carrier_id: str | None = None,
    ) -> Ruling:
        country = interest.country.upper()
        note = note_for(country)
        reasons: list[str] = []
        disclosure: list[str] = []

        # 1. Insurable interest. First, because it is the one test no licence
        #    cures and no country waives.
        if not interest.inside_trigger_area:
            reasons.append(
                "what you are insuring is not inside the area this index "
                "measures, so a payout would not answer a loss you could "
                "actually suffer"
            )
            return Ruling(False, Channel.REFUSED, None, 0.0, tuple(reasons), stage,
                          note=note)

        # 2. Indemnity, enforced as a cap rather than a loss adjustment.
        max_limit = float(interest.value_at_risk)
        if limit > max_limit + 1e-9:
            reasons.append(
                f"cover of {limit:,.0f} exceeds the {max_limit:,.0f} you declared "
                f"at risk; cover above the value at risk is a wager rather than "
                f"an indemnity"
            )
            return Ruling(False, Channel.REFUSED, None, max_limit, tuple(reasons),
                          stage, note=note)

        # 3. A price. A licence to sell something the protocol cannot price is
        #    not cover, and this is checked before placement so the refusal is
        #    about the model rather than blaming a registry that did nothing wrong.
        if not self.priceable(peril, country):
            reasons.append(
                f"this protocol has no model that can price {peril} cover in "
                f"{country} yet, so nothing can be written there whoever is "
                f"licensed"
            )
            return Ruling(False, Channel.REFUSED, None, max_limit, tuple(reasons),
                          stage, note=note)

        # 4. Placement. Which registered company may issue this, if any. Tried
        #    in the order of assets the buyer would prefer, so a country that
        #    permits only fiat is discovered rather than assumed.
        # The asset the buyer named is a preference, not a condition. What they
        # can actually settle in is decided by the licence of whoever issues the
        # policy, so the preferred one is tried first and the other after, and
        # the ruling reports which one it landed on rather than refusing someone
        # over a default they never chose.
        wanted = [Settlement.STABLECOIN, Settlement.FIAT]
        if asset is not None:
            wanted = [asset] + [a for a in wanted if a is not asset]
        placement = None
        settled_as = None
        for candidate in wanted:
            attempt = self.registry.place(
                country=country, peril=peril, limit=limit, term_days=term_days,
                asset=candidate, reach=interest.reach,
                book_capacity=book_capacity, now=now, chosen=carrier_id,
            )
            if attempt.placed:
                placement, settled_as = attempt, candidate
                break
            # Nothing placed. Keep whichever refusal says the most: an attempt
            # that found somebody licensed knows the cover exists and the paper
            # is full, and an attempt that found nobody only knows it tried the
            # wrong asset. Keeping the first one meant a country with fiat-only
            # carriers was always told "nobody is licensed here", because
            # stablecoin is tried first and nobody there settles in it.
            if placement is None or (attempt.licensed and not placement.licensed):
                placement = attempt

        if placement is None or not placement.placed or settled_as is None:
            # Both assets were tried, so the refusal must not name one of them
            # and imply the other would have worked.
            for reason in (placement.reasons if placement else ()):
                for asset_name in ("stablecoin", "fiat"):
                    reason = reason.replace(f", paid in {asset_name}", "")
                reasons.append(reason)
            if note is not None:
                disclosure.append(note.text)
            return Ruling(False, Channel.REFUSED, None, max_limit, tuple(reasons),
                          stage, placement=placement, note=note,
                          disclosure=tuple(disclosure))

        best = placement.best
        assert best is not None
        operator_owned = best.carrier.carrier_id.startswith("clause-")
        channel = (
            Channel.DIRECT if operator_owned
            else Channel.INDEX_CONTRACT if best.licence.reach is Reach.PROFESSIONAL
            else Channel.FRONTED
        )

        if best.carrier.specimen:
            # First, before anything that describes the cover, because
            # everything after it is conditional on this.
            disclosure.append(
                f"{best.carrier.name} is a stand in, not a company. It holds no "
                f"licence, no regulator supervises it, and nothing written "
                f"against it is cover. This deployment is a demonstration."
            )

        if channel is Channel.FRONTED:
            disclosure.append(
                f"{best.carrier.name} is the insurer, supervised by "
                f"{best.licence.authority} under licence {best.licence.reference}. "
                f"Clause is not the insurer: this pool stands behind that policy "
                f"as capital."
            )
        elif channel is Channel.DIRECT:
            disclosure.append(
                f"{best.carrier.name} is the insurer, supervised by "
                f"{best.licence.authority} under licence {best.licence.reference}. "
                f"It is the protocol operator's own licensed entity, and it was "
                f"matched by the same rule as every other company on the registry."
            )
        else:
            disclosure.append(
                "This is an index contract between informed parties, written by "
                f"{best.carrier.name} under {best.licence.authority}. It is not "
                f"insurance and is not offered as insurance."
            )

        if placement.reinsurers:
            disclosure.append(
                "Standing behind it: "
                + ", ".join(f"{r.name} ({r.domicile})" for r in placement.reinsurers)
                + "."
            )
        if best.licence.expiring(now=now):
            disclosure.append(
                "That licence is inside its renewal window. Cover already written "
                "is unaffected; the protocol stops matching on it the day it lapses."
            )
        if note is not None:
            disclosure.append(note.text)

        if asset is not None and settled_as is not asset:
            disclosure.append(
                f"You asked to settle in {asset.value}. No carrier licensed in "
                f"{country} may settle that way for this cover, so this policy "
                f"settles in {settled_as.value} instead. The figures do not change."
            )
        reasons.append(
            f"issued in {country} by {best.carrier.name} under "
            f"{best.licence.authority}, paid in {settled_as.value}"
        )
        return Ruling(
            True, channel, settled_as, max_limit, tuple(reasons), stage,
            placement=placement, note=note, disclosure=tuple(disclosure),
        )

    def recheck_at_settlement(
        self, *, interest: Interest, limit: float, peril: str,
        term_days: float = 365.0, asset: Settlement | None = None,
        now: float | None = None, carrier_id: str | None = None,
    ) -> Ruling:
        """The second run, before a payout leaves the pool.

        A policy that was lawful when it was written can stop being lawful while
        it runs: a licence lapses, a carrier is suspended by its own regulator,
        a country's rule changes. Checking once at the start would discover that
        after the money had gone. This is the same evaluation against the
        registry as it stands now, which is what Rialo's compliance model means
        by re-evaluating on every execution.

        A refusal here does not keep the premium. The policy is unwound on the
        same terms as a source that never published.
        """
        return self.evaluate(
            interest=interest, limit=limit, peril=peril, term_days=term_days,
            asset=asset, stage="settlement", now=now, carrier_id=carrier_id,
        )

    # -- the map ----------------------------------------------------------

    def coverage(self, *, include_closed: bool = False) -> list[dict[str, Any]]:
        """Where cover can actually be bought, and why anywhere else cannot.

        A country is open when three things hold at once: an active carrier is
        licensed there, an active reinsurer stands behind it, and the protocol
        has a model that can price at least one of the perils that carrier will
        write. The first version of this map needed only the first, which is how
        Japan came to be shown open with nothing in it anyone could buy.

        With include_closed, countries where someone is licensed but one of the
        other two is missing come back too, marked closed with the reason, so
        the company side of the interface can show a licensed carrier what its
        country is waiting on instead of pretending it is not there.
        """
        backed = self.registry.backed()
        out = []
        for country, entry in sorted(self.registry.coverage().items()):
            licensed = list(entry["perils"])
            sellable = [p for p in licensed if self.priceable(p, country)]
            unpriced = [p for p in licensed if p not in sellable]
            waiting = []
            if not sellable:
                waiting.append("a model that can price cover here")
            if not backed:
                waiting.append("a reinsurer to stand behind it")
            is_open = not waiting
            if not is_open and not include_closed:
                continue
            note = note_for(country)
            out.append({
                **entry,
                "perils": sellable,
                "unpriced": unpriced,
                "open": is_open,
                "waiting_on": waiting,
                "name": note.name if note else country,
                "note": note.text if note else None,
            })
        return out
