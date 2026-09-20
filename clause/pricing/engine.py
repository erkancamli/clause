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
from collections import OrderedDict
from dataclasses import dataclass, field
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
        trials: int = DEFAULT_TRIALS,
        horizon_years: float = 1.0,
        seed: int = 20260917,
    ) -> None:
        self.cost_of_capital = cost_of_capital
        self.expense_ratio = expense_ratio
        self.reinsurance_multiple = reinsurance_multiple
        self.trials = trials
        self.seed = seed
        self.draws = WorldDraws.draw(trials=trials, years=horizon_years, seed=seed)
        self._book_cache: tuple[frozenset[str], list[float]] | None = None
        # The last few candidates settled, by what they are. A quote settles
        # its candidate once and the capacity checks that follow reuse it,
        # instead of simulating the same policy three times over.
        self._candidates: OrderedDict[tuple[Any, ...], list[float]] = OrderedDict()

    # -- book -------------------------------------------------------------

    def book_losses(self, book: Sequence[Exposure]) -> list[float]:
        """Aggregate loss per trial for a book, cached on its membership."""
        key = frozenset(exposure.policy_id for exposure in book)
        if self._book_cache is not None and self._book_cache[0] == key:
            return self._book_cache[1]

        total = [0.0] * self.trials
        for exposure in book:
            for index, amount in enumerate(settle(exposure, self.draws)):
                total[index] += amount

        self._book_cache = (key, total)
        return total

    def losses_of(self, exposure: Exposure) -> list[float]:
        """One exposure's loss per trial, remembered for the next call about it."""
        key = (exposure.policy_id, exposure.peril_key, exposure.limit, exposure.term_days,
               json.dumps(exposure.subject, sort_keys=True, default=str), exposure.curve)
        found = self._candidates.get(key)
        if found is None:
            found = settle(exposure, self.draws)
            self._candidates[key] = found
            while len(self._candidates) > 8:
                self._candidates.popitem(last=False)
        else:
            self._candidates.move_to_end(key)
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

        marginal = max(0.0, after.solvency_capital - before.solvency_capital)

        term_years = term_days / 365.25
        capital_cost = marginal * self.cost_of_capital * term_years
        transfer_cost = (self.reinsurance_multiple - 1.0) * expected_loss
        if expected_loss > 0 and transfer_cost < capital_cost:
            risk_load, basis = transfer_cost, "reinsurance"
        else:
            risk_load, basis = capital_cost, "capital"
        expense_load = expected_loss * self.expense_ratio
        premium = expected_loss + risk_load + expense_load

        ratio = (
            marginal / alone.solvency_capital
            if alone.solvency_capital > 0
            else 0.0
        )

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
            standalone_capital=alone.solvency_capital,
            risk_basis=basis,
            capital_cost=capital_cost,
            diversification=_verdict(ratio),
            diversification_ratio=ratio,
            notes=self._notes(
                peril=peril,
                subject=subject,
                book=book,
                marginal=marginal,
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
        ratio: float,
        before: CapitalPosition,
    ) -> list[str]:
        """Plain sentences explaining why this price and not another."""
        notes: list[str] = []
        same_peril = [e for e in book if e.peril_key == peril.key]

        if peril.key == "earthquake":
            here = [
                e for e in same_peril
                if e.subject.get("location") == subject.get("location")
            ]
            if here:
                notes.append(
                    f"The pool already holds {len(here)} earthquake "
                    f"{'policy' if len(here) == 1 else 'policies'} at this location. "
                    "They pay together, so this one deepens an exposure rather than "
                    "spreading it."
                )
            elif same_peril:
                notes.append(
                    "The pool's other earthquake exposure sits elsewhere, so this "
                    "policy spreads the book rather than deepening it."
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

        if not book:
            notes.append(
                "This is the first policy in the book, so its risk load carries the "
                "whole capital requirement. It falls as the book diversifies."
            )
        elif ratio < 0.35 and marginal > 0:
            notes.append(
                "Written alone this risk would need roughly "
                f"{1 / ratio:.1f} times the capital it needs here. The rest is "
                "carried by the book's existing diversification, and the buyer keeps "
                "the saving."
            )
        elif marginal <= 0:
            notes.append(
                "This policy adds no measurable capital requirement at the solvency "
                "standard: its losses land where the book already has room."
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
