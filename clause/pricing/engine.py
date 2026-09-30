"""What a policy costs, and why.

A premium here is built from three parts, each of which can be inspected:

    expected loss    the average payout, from the peril's own model
    risk load        the cost of the capital this policy forces the pool to hold
    expense load     the cost of running the protocol

The middle one is where a parametric pool either works or quietly fails. A
naive protocol charges expected loss plus a fixed margin, which prices the
fiftieth earthquake policy in one city exactly like the first. It is not the
same risk. The first diversifies the book and the fiftieth concentrates it, and
the capital standing behind them differs by far more than the margin does.

So the risk load is the marginal cost of capital: what the pool must hold with
this policy, less what it must hold without it, priced at the pool's cost of
capital over the term. A policy that fills a gap in the book is cheap. A policy
that piles onto a fault the pool is already exposed to is expensive, and the
quote says so in words rather than only in the number.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

from ..perils import PayoutCurve, Peril, get_peril
from .simulation import (
    Exposure,
    SimulationResult,
    WorldDraws,
    settle,
)

# The solvency standard: the pool holds enough to survive the average of the
# worst half percent of years. A tail measure rather than a single point,
# because a book with one dominant catastrophe has a tail a value at risk
# cannot see past.
SOLVENCY_LEVEL = 0.995

# Annual return required on the capital a policy ties up. This is the pool's
# cost of capital, and it is what the risk load actually buys.
COST_OF_CAPITAL = 0.12

# What a diversified reinsurer, or a catastrophe bond, charges to take a
# catastrophe risk off a pool: about three times its expected loss for rare
# layers. A pool holding one country's earthquake risk on its own capital
# would charge far more, because nothing it holds diversifies it; no real
# insurer does that, it buys this cover instead. So the price of carrying a
# risk is the cheaper of the two: capital held, or the risk passed on.
REINSURANCE_MULTIPLE = 3.0

# Protocol running costs, as a share of expected loss.
EXPENSE_RATIO = 0.08

# The most diversification credit a policy can be given: it is charged for at
# least this share of the capital it would need standing alone, however well it
# sits against the book today.
#
# Without it a policy that never appears in the book's tail is charged nothing
# at all, because that is what a marginal reading of the tail says and the
# reading is correct. It is the pricing rule built on it that is not. The book
# here is concentrated in Türkiye, so a New York policy of 100,000 measured a
# marginal capital of exactly zero and was sold for its expected loss plus
# expenses: 13.79 against an expected loss of 12.77, which is a bet with an
# eight per cent margin rather than an insurance price.
#
# Two things follow from that and neither is acceptable. The hundred thousandth
# New York policy is priced against a book that does not contain the other
# ninety nine thousand, so a concentration can be built for nothing one policy
# at a time. And the charge is not proportional to the cover: a million of
# cover in one policy measured 8,845 of capital and cost 1,198.55, while the
# same million split into ten policies measured zero and cost 137.90. The same
# risk, split ten ways, for a ninth of the price.
#
# Standalone capital is proportional to the limit -- 1,141.71 at 100,000 and
# 11,417.08 at a million, exactly ten times -- so a floor written against it
# cannot be arbitraged by splitting.
#
# A twentieth is a conservative floor rather than a charge: capital models
# rarely grant more than half to two thirds of diversification credit, and this
# grants ninety five per cent. It binds only where the measured marginal is
# near zero, which is where the rule was broken; every price that had a real
# marginal charge is untouched by it.
LEAST_OF_STANDALONE = 0.05

# Trials behind every capital figure. Large enough that the half percent tail
# holds a hundred draws, which is what makes a marginal charge meaningful.
DEFAULT_TRIALS = 20_000


@dataclass(frozen=True, slots=True)
class Quote:
    """A price, broken into the parts it was built from."""

    peril_key: str
    limit: float
    term_days: float
    expected_loss: float
    risk_load: float
    expense_load: float
    premium: float
    trigger_probability: float
    expected_share: float
    marginal_capital: float
    standalone_capital: float
    diversification: str
    diversification_ratio: float
    notes: list[str] = field(default_factory=list)
    # How the risk load was set: "capital" held by the pool, or "reinsurance",
    # the market price of passing the risk on, where that is cheaper.
    risk_basis: str = "capital"
    capital_cost: float = 0.0

    @property
    def rate_on_line(self) -> float:
        """Premium as a share of the limit, the market's usual shorthand."""
        return self.premium / self.limit if self.limit else 0.0

    @property
    def loss_ratio_at_expectation(self) -> float:
        """What share of the premium is expected to be paid back out."""
        return self.expected_loss / self.premium if self.premium else 0.0

    def priced_at(self, *, cost_of_capital: float, expense_ratio: float) -> "Quote":
        """The same risk, priced by a company with its own numbers.

        Nothing about the risk changes: the expected loss, the trigger
        probability and the capital this policy ties up are all still the
        pool's measurement of it. Only the two loads move, because only they
        were ever the writer's to choose.
        """
        risk_load, expense_load, premium = loads_for(
            expected_loss=self.expected_loss, marginal_capital=self.marginal_capital,
            term_days=self.term_days, cost_of_capital=cost_of_capital,
            expense_ratio=expense_ratio,
        )
        return replace(self, risk_load=risk_load, expense_load=expense_load, premium=premium)

    def to_dict(self) -> dict[str, Any]:
        return {
            "peril": self.peril_key,
            "limit": round(self.limit, 2),
            "term_days": self.term_days,
            "expected_loss": round(self.expected_loss, 2),
            "risk_load": round(self.risk_load, 2),
            "expense_load": round(self.expense_load, 2),
            "premium": round(self.premium, 2),
            "trigger_probability": round(self.trigger_probability, 6),
            "expected_share": round(self.expected_share, 6),
            "marginal_capital": round(self.marginal_capital, 2),
            "risk_basis": self.risk_basis,
            "capital_cost": round(self.capital_cost, 2),
            "standalone_capital": round(self.standalone_capital, 2),
            "rate_on_line": round(self.rate_on_line, 6),
            "loss_ratio_at_expectation": round(self.loss_ratio_at_expectation, 4),
            "diversification": self.diversification,
            "diversification_ratio": round(self.diversification_ratio, 4),
            "notes": list(self.notes),
        }



def loads_for(*, expected_loss: float, marginal_capital: float, term_days: float,
              cost_of_capital: float, expense_ratio: float) -> tuple[float, float, float]:
    """The two loads and the premium, for one view of what the risk costs.

    The expected loss and the capital a policy ties up are facts about the
    risk: the model measures the first and the simulation the second, and both
    are the same whoever writes the cover. What must be earned on that capital,
    and what it costs to run the business that holds it, belong to whoever is
    writing. Here once, so an offer, a price lock and the policy that is
    finally bound cannot answer differently.
    """
    # Both inputs are money and reach this from two places: a Quote's own
    # floats, and the same Quote after to_dict has rounded it for the wire.
    # Rounding here makes the two agree, which they did not: an offer computed
    # one price and the contract another a cent away, the hash over the
    # contract noticed, and the buyer was told the contract had changed when
    # nothing about it had.
    loss = round(float(expected_loss), 2)
    capital = round(float(marginal_capital), 2)
    years = float(term_days) / 365.25
    risk_load = round(capital * float(cost_of_capital) * years, 2)
    expense_load = round(loss * float(expense_ratio), 2)
    return risk_load, expense_load, round(loss + risk_load + expense_load, 2)


@dataclass(frozen=True, slots=True)
class CapitalPosition:
    """What a book costs the pool to stand behind."""

    expected_loss: float
    solvency_capital: float
    tail_at_standard: float
    one_in_hundred: float
    one_in_twenty: float
    trials: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_loss": round(self.expected_loss, 2),
            "solvency_capital": round(self.solvency_capital, 2),
            "tail_at_standard": round(self.tail_at_standard, 2),
            "one_in_hundred": round(self.one_in_hundred, 2),
            "one_in_twenty": round(self.one_in_twenty, 2),
            "solvency_level": SOLVENCY_LEVEL,
            "trials": self.trials,
        }


def capital_from_losses(losses: Sequence[float], trials: int) -> CapitalPosition:
    """Read a loss vector as a capital requirement.

    Capital is held against the gap between the tail and the expected loss,
    because the expected loss is already funded by premium.
    """
    result = SimulationResult(losses=list(losses), trials=trials)
    expected = result.mean()
    tail = result.tail_value_at_risk(SOLVENCY_LEVEL)
    return CapitalPosition(
        expected_loss=expected,
        solvency_capital=max(0.0, tail - expected),
        tail_at_standard=tail,
        one_in_hundred=result.value_at_risk(0.99),
        one_in_twenty=result.value_at_risk(0.95),
        trials=trials,
    )


class PricingEngine:
    """Prices a policy against the book the pool already holds.

    The world is drawn once. A book's loss vector is cached against the set of
    policy identifiers it contains, so quoting settles a single policy rather
    than resimulating everything, and the difference between the book with the
    policy and without it is the policy itself rather than sampling noise.
    """

    def __init__(
        self,
        *,
        cost_of_capital: float = COST_OF_CAPITAL,
        expense_ratio: float = EXPENSE_RATIO,
        reinsurance_multiple: float = REINSURANCE_MULTIPLE,
        # Whether a treaty actually exists. Off, because none does: grep this
        # repository for a cession, a retention, a reinstatement or a treaty
        # and nothing comes back. See the risk load below for what turning it
        # on without buying one was doing to the price.
        reinsurance: bool = False,
        trials: int = DEFAULT_TRIALS,
        horizon_years: float = 1.0,
        seed: int = 20260917,
    ) -> None:
        self.cost_of_capital = cost_of_capital
        self.expense_ratio = expense_ratio
        self.reinsurance_multiple = reinsurance_multiple
        self.reinsurance = reinsurance
        self.trials = trials
        self.seed = seed
        self.draws = WorldDraws.draw(trials=trials, years=horizon_years, seed=seed)
        self._book_cache: tuple[frozenset[tuple[Any, ...]], list[float]] | None = None
        # The last few candidates settled, by what they are. A quote settles
        # its candidate once and the capacity checks that follow reuse it,
        # instead of simulating the same policy three times over.
        self._candidates: OrderedDict[tuple[Any, ...], list[float]] = OrderedDict()
        # Quotes run on several threads at once, each on its own snapshot of
        # the book; the caches are the one thing they share, so the caches
        # are guarded and the simulations, the expensive part, are not.
        self._cache_lock = threading.Lock()

    # -- book -------------------------------------------------------------

    def book_losses(self, book: Sequence[Exposure]) -> list[float]:
        """Aggregate loss per trial for a book, cached on what is in it.

        On what is in it, not on the names of what is in it. The key used to
        be the set of policy ids, so two different books whose policies
        happened to share ids were one book to this cache and the second was
        priced off the first one's losses. Ids are unique in a live book, so
        this was a trap rather than a live fault -- but a cache that can
        silently return another book's tail is the worst place to keep one,
        and it did exactly that to a measurement taken with this code.

        The per-exposure key is the one ``losses_of`` already uses. Building
        it costs a JSON dump per policy on a cache hit, against a full
        simulation per policy on a miss, which is thousands of trials each.
        """
        key = frozenset(self._key_of(exposure) for exposure in book)
        with self._cache_lock:
            cached = self._book_cache
        if cached is not None and cached[0] == key:
            return cached[1]

        total = [0.0] * self.trials
        for exposure in book:
            for index, amount in enumerate(settle(exposure, self.draws)):
                total[index] += amount

        with self._cache_lock:
            self._book_cache = (key, total)
        return total

    @staticmethod
    def _key_of(exposure: Exposure) -> tuple[Any, ...]:
        """Everything about one exposure that changes what it loses."""
        return (exposure.policy_id, exposure.peril_key, exposure.limit,
                exposure.term_days,
                json.dumps(exposure.subject, sort_keys=True, default=str),
                exposure.curve)

    def losses_of(self, exposure: Exposure) -> list[float]:
        """One exposure's loss per trial, remembered for the next call about it."""
        key = self._key_of(exposure)
        with self._cache_lock:
            found = self._candidates.get(key)
            if found is not None:
                self._candidates.move_to_end(key)
        if found is None:
            found = settle(exposure, self.draws)
            with self._cache_lock:
                self._candidates[key] = found
                while len(self._candidates) > 8:
                    self._candidates.popitem(last=False)
        return found

    def losses_with(self, book: Sequence[Exposure], extra: Exposure | None) -> list[float]:
        """The book's loss per trial with one more policy in it: the cached
        book plus that policy, rather than the whole book simulated again
        under a membership the cache has never seen."""
        base = self.book_losses(book)
        if extra is None:
            return base
        return [a + b for a, b in zip(base, self.losses_of(extra))]

    def position(self, book: Sequence[Exposure]) -> CapitalPosition:
        """The capital the pool must hold for a given book."""
        return capital_from_losses(self.book_losses(book), self.trials)

    def simulate(self, book: Sequence[Exposure]) -> SimulationResult:
        """The full result for a book, for the pool's own risk views."""
        trials = self.trials
        total = [0.0] * trials
        by_peril: dict[str, list[float]] = {}
        for exposure in book:
            losses = settle(exposure, self.draws)
            bucket = by_peril.setdefault(exposure.peril_key, [0.0] * trials)
            for index, amount in enumerate(losses):
                total[index] += amount
                bucket[index] += amount
        return SimulationResult(losses=total, trials=trials, by_peril=by_peril)

    # -- quoting ----------------------------------------------------------

    def quote(
        self,
        *,
        peril_key: str,
        subject: dict[str, Any],
        limit: float,
        term_days: float,
        curve: PayoutCurve | None = None,
        book: Sequence[Exposure] = (),
        policy_id: str = "candidate",
    ) -> Quote:
        """Price one prospective policy against the current book."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        if term_days <= 0:
            raise ValueError("term must be positive")

        peril: Peril = get_peril(peril_key)
        subject = peril.validate_subject(subject)
        curve = curve or peril.curve_for(subject)

        # Expected loss comes from the peril's own model rather than from the
        # simulation, so it is exact rather than sampled.
        working_curve = (
            peril.curve_in_mm(subject, curve) if peril_key == "drought" else curve
        )
        exceedance = peril.exceedance(subject, term_days)
        expected_share = working_curve.expected_share(exceedance)
        trigger = exceedance(working_curve.attachment)
        expected_loss = limit * expected_share

        candidate = Exposure(
            policy_id=policy_id,
            peril_key=peril_key,
            subject=subject,
            curve=curve,
            limit=limit,
            term_days=term_days,
        )

        # Marginal capital, on shared draws.
        candidate_losses = self.losses_of(candidate)
        before_losses = self.book_losses(book)
        after_losses = [a + b for a, b in zip(before_losses, candidate_losses)]

        before = capital_from_losses(before_losses, self.trials)
        after = capital_from_losses(after_losses, self.trials)
        alone = capital_from_losses(candidate_losses, self.trials)

        measured = max(0.0, after.solvency_capital - before.solvency_capital)
        # The capital this policy would need standing alone, which the floor is
        # written against, so it has to be a number the simulation can actually
        # produce. For a rare risk it cannot. New York pays about once in three
        # thousand seven hundred years; in twenty thousand trials that is five
        # events, and in a third of runs at four thousand trials it is none at
        # all -- a standalone requirement of exactly zero, and a floor of five
        # per cent of nothing.
        #
        # It does not have to be simulated. Below the solvency tail the answer
        # is exact: if the policy pays at all less often than one time in two
        # hundred, then every outcome in which it pays is inside the worst half
        # per cent, the tail average is the expected loss divided by that half
        # per cent, and the capital is 199 times the expected loss. No draws,
        # no noise, and the same number every time it is asked.
        tail = 1.0 - SOLVENCY_LEVEL
        standalone = (expected_loss * (1.0 / tail - 1.0) if trigger <= tail
                      else alone.solvency_capital)
        # What the book says this policy adds, and what it is charged for. They
        # differ only where the first is below the floor above, which is where
        # a marginal reading stops being a price.
        floor = LEAST_OF_STANDALONE * standalone
        marginal = max(measured, floor)

        term_years = term_days / 365.25
        capital_cost = marginal * self.cost_of_capital * term_years
        transfer_cost = (self.reinsurance_multiple - 1.0) * expected_loss
        # The cheaper of holding the capital and passing the risk on -- but
        # only where the risk is actually passed on. No treaty exists. Nothing
        # in this codebase cedes anything, and the quote was telling the buyer
        # that the price used a diversified reinsurer's rate.
        #
        # For a catastrophe peril the transfer branch always won, because the
        # capital a correlated risk needs is many times its expected loss and
        # the transfer price is a small multiple of it. So the marginal
        # capital engine -- the thing that makes the two hundred and first
        # Istanbul policy dearer than the first -- was computed, compared, and
        # then never used. That is why every earthquake policy came out at
        # exactly 3.08 times expected loss whatever else was in the book.
        if self.reinsurance and expected_loss > 0 and transfer_cost < capital_cost:
            risk_load, basis = transfer_cost, "reinsurance"
        else:
            risk_load, basis = capital_cost, "capital"
        expense_load = expected_loss * self.expense_ratio
        premium = expected_loss + risk_load + expense_load

        # The verdict is about the risk, so it reads the measured marginal: a
        # policy the book absorbs entirely is still one the book absorbs
        # entirely, and saying otherwise because of the floor would hide the
        # very thing the floor exists for.
        ratio = measured / standalone if standalone > 0 else 0.0

        return Quote(
            peril_key=peril_key,
            limit=limit,
            term_days=term_days,
            expected_loss=expected_loss,
            risk_load=risk_load,
            expense_load=expense_load,
            premium=premium,
            trigger_probability=trigger,
            expected_share=expected_share,
            marginal_capital=marginal,
            standalone_capital=standalone,
            risk_basis=basis,
            capital_cost=capital_cost,
            diversification=_verdict(ratio),
            diversification_ratio=ratio,
            notes=self._notes(
                peril=peril,
                subject=subject,
                book=book,
                marginal=marginal,
                measured=measured,
                ratio=ratio,
                before=before,
            ) + ([
                f"Holding capital for this risk would cost {capital_cost:,.0f}. Passing it to a "
                f"diversified reinsurer at the market's usual {self.reinsurance_multiple:g} times "
                f"expected loss costs {transfer_cost:,.0f}, so the price uses that."
            ] if basis == "reinsurance" else []),
        )

    # -- explanation ------------------------------------------------------

    def _notes(
        self,
        *,
        peril: Peril,
        subject: dict[str, Any],
        book: Sequence[Exposure],
        marginal: float,
        measured: float,
        ratio: float,
        before: CapitalPosition,
    ) -> list[str]:
        """Plain sentences explaining why this price and not another."""
        notes: list[str] = []
        same_peril = [e for e in book if e.peril_key == peril.key]

        if peril.key == "earthquake":
            # Near enough that one earthquake can pay both. Each policy watches
            # a circle, so two of them can be paid by a single event exactly
            # when their circles overlap, which is when the centres are no
            # further apart than the two radii added together.
            #
            # This used to compare subject["location"], the place code the
            # buyer typed. By the time a subject reaches here the peril has
            # resolved it to a point and dropped that key, so the comparison
            # was None against None: true for every pair of earthquake
            # policies on earth. A New York quote was told the pool already
            # held two hundred policies at its location while every one of
            # them was in Istanbul, and the sentence for a policy that really
            # does spread the book could never be reached at all.
            from ..perils.geo import distance_km

            try:
                point = (float(subject["latitude"]), float(subject["longitude"]))
                radius = float(subject.get("radius_km", 0.0))
            except (KeyError, TypeError, ValueError):
                here: list[Exposure] = []
            else:
                def overlaps(other: Exposure) -> bool:
                    try:
                        there = (float(other.subject["latitude"]),
                                 float(other.subject["longitude"]))
                        reach = float(other.subject.get("radius_km", 0.0)) + radius
                    except (KeyError, TypeError, ValueError):
                        return False
                    return distance_km(point, there) <= reach

                here = [e for e in same_peril if overlaps(e)]
            # What the sentence says is what was measured and no more: the
            # circles overlap, so an earthquake inside the overlap is one
            # earthquake that pays both.
            if here:
                notes.append(
                    f"The pool already holds {len(here)} earthquake "
                    f"{'policy' if len(here) == 1 else 'policies'} watching ground "
                    "that overlaps this one's. An earthquake in the overlap pays "
                    "both, so this policy deepens that exposure rather than "
                    "spreading it."
                )
            elif same_peril:
                notes.append(
                    "No earthquake policy the pool holds watches ground that "
                    "overlaps this one's, so this policy spreads the book rather "
                    "than deepening it."
                )
            note = peril.radius_note(subject)
            if note:
                notes.append(note)

        if peril.key == "drought":
            station = subject.get("station")
            here = [e for e in same_peril if e.subject.get("station") == station]
            if here:
                notes.append(
                    f"{len(here)} other {'policy' if len(here) == 1 else 'policies'} "
                    "already settle on this station's reading. A dry season pays all "
                    "of them at once."
                )
            verdict, correlation = peril.basis_risk_for(subject)
            notes.append(
                f"Field to station correlation is about {correlation:.2f}: {verdict}."
            )

        # Wind and rain both settle on a station's reading and both carry a
        # shared factor across a region, so cover on one station accumulates the
        # way cover on one fault does. A storm or a car quote used to say nothing
        # at all about that, while an earthquake and a drought quote each said
        # what they sat beside: the same price, explained to one buyer and not
        # another.
        WEATHER = {
            "storm": ("One front is hundreds of kilometres wide, so a day that "
                      "takes roofs here takes them there."),
            "vehicle_flood": ("One storm system floods several provinces in the "
                              "same year, so a day like that pays them together."),
        }
        if peril.key in WEATHER:
            station = subject.get("station")
            here = [e for e in same_peril
                    if station and e.subject.get("station") == station]
            if here:
                notes.append(
                    f"{len(here)} other {'policy' if len(here) == 1 else 'policies'} "
                    f"already settle on this station's reading. {WEATHER[peril.key]}"
                )
            elif same_peril:
                notes.append(
                    "No other policy the pool holds settles on this station's "
                    "reading, so this policy spreads the book rather than "
                    "deepening it."
                )

        if not book:
            notes.append(
                "This is the first policy in the book, so its risk load carries the "
                "whole capital requirement. It falls as the book diversifies."
            )
        elif measured <= 0:
            notes.append(
                "This policy adds no measurable capital requirement at the solvency "
                "standard: its losses land where the book already has room. It is "
                f"charged for {LEAST_OF_STANDALONE:.0%} of what it would need standing "
                "alone all the same, because the book it diversifies against is "
                "today's book: priced at nothing, the same risk could be written "
                "again and again, each time against a book that does not hold the "
                "others."
            )
        elif ratio < 0.35 and marginal > measured:
            notes.append(
                f"Written alone this risk would need roughly {1 / ratio:.1f} times the "
                "capital the book says it adds here. Most of that saving is passed on, "
                f"but not all of it: the charge is held at {LEAST_OF_STANDALONE:.0%} of "
                "the standalone requirement, because today's diversification is not a "
                "promise about tomorrow's book."
            )
        elif ratio < 0.35 and marginal > 0:
            notes.append(
                "Written alone this risk would need roughly "
                f"{1 / ratio:.1f} times the capital it needs here. The rest is "
                "carried by the book's existing diversification, and the buyer keeps "
                "the saving."
            )

        if before.solvency_capital > 0 and marginal > 0:
            share = marginal / before.solvency_capital
            if share > 0.25:
                notes.append(
                    f"It raises the pool's capital requirement by {share * 100:.0f}%, "
                    "which is a large step for one policy."
                )

        return [note for note in notes if note]


def _verdict(ratio: float) -> str:
    """How this policy sits against the book, in one word.

    The comparison is against what the same risk would need standing alone,
    which is the only reading that means anything: a low frequency peril always
    needs capital many times its expected loss, whether or not it diversifies.
    """
    if ratio <= 0:
        return "absorbed"
    if ratio < 0.35:
        return "diversifying"
    if ratio < 0.85:
        return "partly diversifying"
    if ratio <= 1.15:
        return "standalone"
    return "concentrating"
