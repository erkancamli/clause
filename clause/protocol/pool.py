"""The underwriting pool.

Someone has to be able to pay. In a parametric protocol that someone is a pool
of capital put up by people who are paid to carry the risk, and everything
interesting about the pool is the rule that stops it writing more than it can
stand behind.

Three rules govern it, and each exists because of a way pools fail:

  Solvency. The pool may not write a policy that would leave its capital below
  what the book needs to survive the worst half percent of years. Sized from
  the simulated book, not from a sum of limits, because the limits never all
  pay at once and pretending they might makes cover unaffordable.

  Concentration. No single catastrophe may consume more than a set share of the
  pool, whatever the overall solvency figure says. A pool can be solvent on
  average and still be one earthquake away from nothing.

  Locked capital. A provider may withdraw only what is not standing behind live
  policies. Capital that can leave the moment it is needed was never capital.

Tranches
--------
Not every provider wants the same risk. The capital is held in three tranches,
and a loss is taken from the most junior first:

  first_loss   takes every loss until it is gone, and is paid the most for it
  mezzanine    takes what the first loss tranche could not
  senior       is touched only when both below it are exhausted

Each premium is split in two. The part that pays for expected loss goes to
the tranches in proportion to the loss each is expected to take, so the layer
that will pay the claims is the one funded for them. The rest, the margin for
holding capital, is shared by capital times a yield weight: a unit of first
loss capital earns three times the margin a unit of senior capital does. The
order, the weights and the split are the whole contract between the tranches,
and all three are published with every figure.

One more rule follows from the order. The senior tranche is safe only while
there is capital beneath it, so the tranches below may not withdraw while that
would leave them smaller than the book's one in ten year loss. Without that
rule the first loss capital could walk away the day the season turned.

Accounting is in whole units of the settlement asset and every movement is
recorded, so the ledger can be replayed and checked rather than trusted.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

from ..pricing import Exposure, PricingEngine, Quote, capital_from_losses
from ..pricing.engine import COST_OF_CAPITAL, EXPENSE_RATIO
from .policy import Policy, PolicyStatus

# No single modelled catastrophe may take more than this share of pool capital.
CONCENTRATION_LIMIT = 0.35

#: The most cover this pool will have in force in one accumulation zone, as a
#: share of its balance. A zone is what pays together: one fault system, one
#: rainfall station, one province's weather. At the top of an earthquake's
#: curve every magnitude policy in the zone pays its whole limit at once, so
#: the zone's aggregate limit *is* the loss from one event there -- there is no
#: modelling left to do and no diversification to hope for.
#:
#: The pool's other rule caps the worst modelled *year* at 35% of capital, one
#: order statistic out of twenty thousand trials. That is a different question
#: from "what does one rupture take", and it was the only one being asked. A
#: quarter is a number an actuary should set against a real capital plan; it
#: is here so that the question is asked at all, and so that a pool cannot be
#: filled to the brim with one fault.
ZONE_LIMIT = 0.25

# The pool keeps this much more capital than the solvency figure demands, so a
# book does not sit exactly on its limit and refuse the next policy.
CAPITAL_BUFFER = 1.15

# Most senior first. Losses run the other way.
TRANCHES = ("senior", "mezzanine", "first_loss")
# Premium is shared by capital times this weight.
YIELD_WEIGHT = {"senior": 1.0, "mezzanine": 1.75, "first_loss": 3.0}
# The pool's own account: shares minted to it for income that accrued while no
# provider held any (see deposit).
RETAINED = "pool.retained"
# The capital beneath the senior tranche may not fall below the book's loss at
# this return period while senior capital stands behind it.
SUBORDINATION_YEARS = 10


def _tranche(name: str | None) -> str:
    name = (name or "senior").strip().lower()
    if name not in TRANCHES:
        raise PoolError(f"a tranche is one of {', '.join(TRANCHES)}")
    return name


@dataclass(slots=True)
class Tranche:
    """One layer of the pool's capital."""

    name: str
    balance: float = 0.0
    shares: float = 0.0

    @property
    def price(self) -> float:
        return self.balance / self.shares if self.shares > 0 else 1.0


class EntryKind(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    PREMIUM = "premium"
    PAYOUT = "payout"
    REFUND = "refund"
    COMMISSION = "commission"
    INSTALMENT = "instalment"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One movement of value, recorded so the pool can be audited."""

    at: float
    kind: EntryKind
    amount: float
    account: str
    reference: str
    balance_after: float
    # How the movement fell across the tranches, when it touched more than one
    # or any but the senior.
    split: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "at": self.at,
            "kind": self.kind.value,
            "amount": round(self.amount, 2),
            "account": self.account,
            "reference": self.reference,
            "balance_after": round(self.balance_after, 2),
        }
        if self.split:
            out["split"] = {k: round(v, 2) for k, v in self.split.items()}
        return out


class PoolError(RuntimeError):
    """Raised when an operation would break one of the pool's rules."""


class PriceMoved(PoolError):
    """The premium at bind time is above what the buyer agreed to pay.

    Its own type because its message is the one refusal a buyer must be told
    verbatim. Everything else the pool refuses says why in terms that would
    describe the book, and the book is nobody's business but the pool's; this
    one names only two figures the buyer already has, so passing it through
    leaks nothing and withholding it would leave them guessing.
    """


@dataclass(slots=True)
class Provider:
    """One capital provider and the shares they hold."""

    account: str
    shares: float
    deposited: float = 0.0
    withdrawn: float = 0.0
    tranche: str = "senior"

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "tranche": self.tranche,
            "shares": round(self.shares, 6),
            "deposited": round(self.deposited, 2),
            "withdrawn": round(self.withdrawn, 2),
        }


def provider_key(account: str, tranche: str) -> str:
    """Senior holdings keep the bare address, as they did before tranches."""
    return account if tranche == "senior" else f"{account}/{tranche}"


class Pool:
    """Capital, policies, and the rules between them."""

    def __init__(
        self,
        *,
        engine: PricingEngine | None = None,
        concentration_limit: float = CONCENTRATION_LIMIT,
        zone_limit: float = ZONE_LIMIT,
        capital_buffer: float = CAPITAL_BUFFER,
        wallets: Any = None,
    ) -> None:
        self.engine = engine or PricingEngine()
        self.concentration_limit = concentration_limit
        self.zone_limit = zone_limit
        self.capital_buffer = capital_buffer
        # The counterparty side of every movement, keyed by address. Optional,
        # because the pool's own accounting has to balance whether or not
        # anyone is watching the other end of the transfer.
        self.wallets = wallets

        # Held around every movement of value. Set by the API to the same lock
        # the chain thread and the arrivals task use, so a balance check and the
        # debit that follows it cannot be interleaved with another caller's.
        self.lock = threading.RLock()

        self.tranches: dict[str, Tranche] = {name: Tranche(name) for name in TRANCHES}
        self.providers: dict[str, Provider] = {}
        self.policies: dict[str, Policy] = {}
        self.ledger: list[LedgerEntry] = []

        # Called with (account, amount, reference, kind) after money leaves the
        # pool for an address, so a payout can be routed on to a bank.
        self.listeners: list[Any] = []

        self.premiums_earned: float = 0.0
        self.claims_paid: float = 0.0
        self.refunds_paid: float = 0.0

    # -- reporting --------------------------------------------------------

    @property
    def open_policies(self) -> list[Policy]:
        return [p for p in self.policies.values() if p.is_open]

    def snapshot(self) -> tuple[list[Exposure], float]:
        """The book and the balance at one moment, taken under the lock and
        handed out, so a quote can be worked on a copy while the lock is
        free for the purchases and payouts that actually move money."""
        with self.lock:
            return self.exposures(), self.balance

    def exposures(self, extra: Exposure | None = None) -> list[Exposure]:
        """The live book, as the capital model sees it."""
        book = [
            Exposure(
                policy_id=policy.policy_id,
                peril_key=policy.peril_key,
                subject=dict(policy.subject),
                curve=policy.curve,
                limit=policy.limit,
                term_days=policy.term_days,
            )
            for policy in self.open_policies
        ]
        if extra is not None:
            book.append(extra)
        return book

    # -- the tranches -----------------------------------------------------

    @property
    def balance(self) -> float:
        """All the capital, every tranche together."""
        return sum(t.balance for t in self.tranches.values())

    @balance.setter
    def balance(self, value: float) -> None:
        # Anything that moves the total without naming a tranche is a gain
        # shared by the yield weights or a loss taken from the bottom up.
        delta = float(value) - self.balance
        if delta > 0:
            self._gain(delta)
        elif delta < 0:
            self._lose(-delta)

    @property
    def total_shares(self) -> float:
        """Senior shares: a pool with one tranche is its senior tranche."""
        return self.tranches["senior"].shares

    @total_shares.setter
    def total_shares(self, value: float) -> None:
        self.tranches["senior"].shares = float(value)

    @property
    def share_price(self) -> float:
        """Value of one senior share, the pool's headline figure."""
        return self.tranches["senior"].price

    def _gain(self, amount: float) -> dict[str, float]:
        """Share income across the tranches by capital times yield weight."""
        weights = {n: t.balance * YIELD_WEIGHT[n] for n, t in self.tranches.items() if t.balance > 0}
        total = sum(weights.values())
        if total <= 0:
            weights, total = {"senior": 1.0}, 1.0
        split = {n: amount * w / total for n, w in weights.items()}
        for name, part in split.items():
            self.tranches[name].balance += part
        return split

    def _loss_shares(self, losses: Sequence[float] | None = None) -> dict[str, float]:
        """Expected loss of each tranche on the book as it stands."""
        if losses is None:
            losses = self.engine.simulate(self.exposures()).losses
        n = len(losses) or 1
        out: dict[str, float] = {}
        attach = 0.0
        for name in reversed(TRANCHES):
            size = max(0.0, self.tranches[name].balance)
            out[name] = sum(min(max(x - attach, 0.0), size) for x in losses) / n if size > 0 else 0.0
            attach += size
        return out

    def _premium_split(self, premium: float, expected_loss: float,
                       losses: Sequence[float] | None = None) -> dict[str, float]:
        """How one premium is owed across the tranches (not yet applied)."""
        el = min(max(expected_loss, 0.0), premium)
        margin = premium - el
        split: dict[str, float] = {}
        shares = self._loss_shares(losses) if el > 0 else {}
        total = sum(shares.values())
        weights = {n: t.balance * YIELD_WEIGHT[n] for n, t in self.tranches.items() if t.balance > 0}
        wtotal = sum(weights.values()) or 1.0
        if not weights:
            weights = {"senior": 1.0}
        for name in TRANCHES:
            part = margin * weights.get(name, 0.0) / wtotal
            if total > 0:
                part += el * shares.get(name, 0.0) / total
            else:
                part += el * weights.get(name, 0.0) / wtotal
            if part:
                split[name] = part
        return split

    def _lose(self, amount: float) -> dict[str, float]:
        """Take a loss from the most junior tranche upward."""
        split: dict[str, float] = {}
        left = amount
        for name in reversed(TRANCHES):
            tranche = self.tranches[name]
            take = min(left, max(0.0, tranche.balance))
            if take > 0:
                tranche.balance -= take
                split[name] = take
                left -= take
            if left <= 1e-12:
                break
        if left > 1e-12:
            # Only reachable if a caller skipped the balance check; recorded on
            # the senior tranche so the books still sum to what was paid.
            self.tranches["senior"].balance -= left
            split["senior"] = split.get("senior", 0.0) + left
        return split

    def _reverse(self, split: dict[str, float], amount: float) -> dict[str, float]:
        """Take back income as it was shared; anything left, from the bottom."""
        taken: dict[str, float] = {}
        left = amount
        for name, part in split.items():
            tranche = self.tranches.get(name)
            if tranche is None:
                continue
            take = min(part, left, max(0.0, tranche.balance))
            tranche.balance -= take
            taken[name] = take
            left -= take
        if left > 1e-12:
            for name, part in self._lose(left).items():
                taken[name] = taken.get(name, 0.0) + part
        return taken

    def subordination_floor(self) -> float:
        """The capital that must stay beneath the senior tranche."""
        result = self.engine.simulate(self.exposures())
        losses = sorted(result.losses)
        if not losses:
            return 0.0
        at = min(len(losses) - 1, int(len(losses) * (1.0 - 1.0 / SUBORDINATION_YEARS)))
        return losses[at]

    def tranche_view(self, losses: Sequence[float] | None = None) -> list[dict[str, Any]]:
        """Each tranche's size, where it attaches, and what it can expect.

        Attachment and exhaustion are in loss: the first loss tranche attaches
        at nothing, the mezzanine at the first loss tranche's size, the senior
        above both. The chance and expected size of a loss come from the same
        simulated years that price the book, so they move with it.
        """
        if losses is None:
            losses = self.engine.simulate(self.exposures()).losses
        n = len(losses) or 1
        annual_premium = sum(
            p.premium * 365.0 / max(1.0, p.term_days) for p in self.open_policies
        )
        annual_el = sum(
            min(p.expected_loss, p.premium) * 365.0 / max(1.0, p.term_days) for p in self.open_policies
        )
        income_by = self._premium_split(annual_premium, annual_el, losses) if annual_premium > 0 else {}
        out: list[dict[str, Any]] = []
        attach = 0.0
        for name in reversed(TRANCHES):
            tranche = self.tranches[name]
            size = tranche.balance
            top = attach + size
            if size > 0:
                hit = sum(1 for x in losses if x > attach) / n
                gone = sum(1 for x in losses if x >= top) / n
                expected = sum(min(max(x - attach, 0.0), size) for x in losses) / n
            else:
                hit = gone = expected = 0.0
            income = income_by.get(name, 0.0)
            holders = sum(1 for p in self.providers.values() if p.tranche == name and p.shares > 0)
            out.append({
                "name": name,
                "balance": round(size, 2),
                "shares": round(tranche.shares, 6),
                "share_price": round(tranche.price, 6),
                "providers": holders,
                "yield_weight": YIELD_WEIGHT[name],
                "attaches_at": round(attach, 2),
                "exhausted_at": round(top, 2),
                "probability_of_loss": round(hit, 4),
                "probability_exhausted": round(gone, 4),
                "expected_loss": round(expected, 2),
                "expected_premium": round(income, 2),
                "expected_return": round((income - expected) / size, 4) if size > 0 else None,
            })
            attach = top
        out.reverse()
        return out

    def required_capital(self, extra: Exposure | None = None, *,
                         book: list[Exposure] | None = None) -> float:
        """Capital the book needs at the solvency standard, with the buffer."""
        losses = self.engine.losses_with(self.exposures() if book is None else book, extra)
        position = capital_from_losses(losses, self.engine.trials)
        return position.solvency_capital * self.capital_buffer

    def free_capital(self) -> float:
        """What could leave the pool without breaking the solvency rule.

        Not :meth:`own_funds`, which is the balance less the premium owed to
        cover already sold. This one is about withdrawal; that one is about
        capacity.
        """
        return max(0.0, self.balance - self.required_capital())

    def worst_modelled_year(self, extra: Exposure | None = None, *,
                            book: list[Exposure] | None = None) -> float:
        """The worst modelled year: one order statistic out of every trial run.

        Not the worst event. A year can hold several, and one event can be
        worse than the worst year is deep, because what a single rupture takes
        from a concentrated book does not depend on how the rest of the year
        goes. What one event takes is :meth:`zone_exposure`.
        """
        losses = self.engine.losses_with(self.exposures() if book is None else book, extra)
        return max(losses) if losses else 0.0

    #: The old name, which said "single event" and measured a year. Kept so
    #: nothing that calls it breaks, and deprecated because the name was the
    #: reason nobody noticed the pool had no per event rule at all.
    largest_single_event_loss = worst_modelled_year

    def unearned_premium(self, now: float | None = None) -> float:
        """Premium taken for cover that has not been given yet.

        Every premium was booked as the pool's own money the moment it was
        taken, and it is not: the part of it that belongs to days the policy
        has not run yet is owed back if the cover is cancelled and is owed to
        the risk if it is not. It is a liability against the balance, not
        capital standing behind other people's policies.

        Earned on a day basis, pro rata temporis, which is what the Turkish
        technical provisions regulation under Law 5684 requires and what
        Solvency II's premium provision starts from. It is the wrong shape for
        drought -- a season's risk is not spread evenly across its days -- and
        it is what the statute prescribes; a pattern that followed the hazard
        would need the regulator's blessing and a stated basis.
        """
        now = time.time() if now is None else now
        total = 0.0
        for policy in self.open_policies:
            span = policy.ends_at - policy.starts_at
            if span <= 0:
                continue
            # Before it starts nothing is earned; after it ends nothing is left.
            left = min(max(policy.ends_at - now, 0.0), span)
            total += policy.premium * (left / span)
        return round(total, 2)

    def own_funds(self, now: float | None = None) -> float:
        """The balance less what is owed to cover already sold.

        Solvency II's own term for it, because it is Solvency II's quantity:
        assets less technical provisions. It is not :meth:`free_capital`,
        which asks what could leave the pool without breaking the solvency
        rule -- a different question, and the two were briefly the same name
        here, which would have let capital walk out that the solvency rule was
        holding.

        The capacity rules used to measure themselves against the whole
        balance, unearned premium included, so a pool could sell cover and
        count the money it had just taken as the capital that made the next
        sale safe. Each policy paid for the capacity to write the next one.
        """
        return max(0.0, self.balance - self.unearned_premium(now))

    def accumulation(self, extra: Any = None) -> dict[str, float]:
        """Cover in force in each accumulation zone, largest first.

        What pays together, added up. With ``extra`` the candidate is counted
        in, which is the question the capacity gate asks: not "how exposed are
        we" but "how exposed would writing this make us".
        """
        totals: dict[str, float] = {}
        for policy in self.open_policies:
            key = _accumulation_key(policy)
            totals[key] = totals.get(key, 0.0) + policy.limit
        if extra is not None:
            key = _accumulation_key(extra)
            totals[key] = totals.get(key, 0.0) + float(extra.limit)
        return dict(sorted(totals.items(), key=lambda item: -item[1]))

    def zone_exposure(self, extra: Any = None) -> tuple[str, float]:
        """The fullest accumulation zone and what it holds. ('', 0.0) if empty."""
        totals = self.accumulation(extra)
        if not totals:
            return "", 0.0
        zone = next(iter(totals))
        return zone, totals[zone]

    # -- capital ----------------------------------------------------------

    def deposit(self, account: str, amount: float, *, tranche: str | None = None,
                now: float | None = None) -> float:
        """Add capital to a tranche and receive its shares at its price."""
        with self.lock:
            if amount <= 0:
                raise PoolError("a deposit must be positive")
            name = _tranche(tranche)
            layer = self.tranches[name]

            if layer.shares <= 0 and layer.balance > 0:
                # Income accrued with nobody holding shares (every provider
                # withdrew). It belongs to the pool; shares for it are minted
                # to the pool's own account so the next depositor buys in at
                # par rather than being handed it.
                keeper = self.providers.setdefault(
                    provider_key(RETAINED, name), Provider(RETAINED, 0.0, tranche=name))
                keeper.shares += layer.balance
                layer.shares += layer.balance
            price = layer.price
            shares = amount / price

            # Capital comes from an address too. A liquidity provider is not a
            # different kind of user, only a different side of the book.
            if self.wallets is not None:
                self.wallets.debit(account, amount, "pool", kind="deposit")

            provider = self.providers.setdefault(
                provider_key(account, name), Provider(account, 0.0, tranche=name))
            provider.shares += shares
            provider.deposited += amount
            layer.shares += shares
            layer.balance += amount

            self._record(EntryKind.DEPOSIT, amount, account,
                         "capital in" if name == "senior" else f"capital in, {name.replace('_', ' ')}",
                         now, {name: amount})
            return shares
    def withdraw(self, account: str, shares: float, *, tranche: str | None = None,
                 now: float | None = None) -> float:
        """Redeem shares, but only against capital that is not committed."""
        with self.lock:
            name = _tranche(tranche)
            layer = self.tranches[name]
            provider = self.providers.get(provider_key(account, name))
            if provider is None or provider.shares <= 0:
                raise PoolError(f"{account} holds no shares")
            if shares <= 0:
                raise PoolError("a withdrawal must be positive")
            if shares > provider.shares + 1e-9:
                raise PoolError(
                    f"{account} holds {provider.shares:.6f} shares and asked for {shares:.6f}"
                )

            amount = shares * layer.price
            free = self.free_capital()
            if amount > free + 1e-6:
                raise PoolError(
                    f"only {free:,.2f} is free to leave; the rest is standing behind "
                    f"{len(self.open_policies)} live policies"
                )
            if name != "senior" and self.tranches["senior"].balance > 0 and self.open_policies:
                beneath = sum(self.tranches[n].balance for n in TRANCHES if n != "senior")
                floor = self.subordination_floor()
                if beneath - amount < floor - 1e-6:
                    raise PoolError(
                        f"the capital beneath the senior tranche has to stay above the "
                        f"book's one in {SUBORDINATION_YEARS} year loss of {floor:,.2f}; "
                        f"{max(0.0, beneath - floor):,.2f} of it can leave now"
                    )

            provider.shares -= shares
            provider.withdrawn += amount
            layer.shares -= shares
            layer.balance -= amount

            self._record(EntryKind.WITHDRAWAL, -amount, account,
                         "capital out" if name == "senior" else f"capital out, {name.replace('_', ' ')}",
                         now, {name: amount})
            if self.wallets is not None:
                self.wallets.credit(account, amount, "pool", kind="withdrawal")
            return amount

        # -- underwriting -----------------------------------------------------
    def quote(
        self,
        *,
        peril_key: str,
        subject: dict[str, Any],
        limit: float,
        term_days: float,
        curve: Any = None, book: list[Exposure] | None = None,
    ) -> Quote:
        """Price a prospective policy against the live book, or against a
        snapshot of it taken earlier (see ``snapshot``)."""
        return self.engine.quote(
            peril_key=peril_key,
            subject=subject,
            limit=limit,
            term_days=term_days,
            curve=curve,
            book=self.exposures() if book is None else book,
        )

    def can_write(
        self, *, peril_key: str, subject: dict[str, Any], limit: float, term_days: float,
        curve: Any = None, book: list[Exposure] | None = None, balance: float | None = None,
    ) -> tuple[bool, list[str]]:
        """Whether the pool may write this policy, and why not if it may not.
        On a snapshot when ``book`` and ``balance`` are given."""
        if balance is None:
            # Own funds, not the whole balance: premium taken for cover that
            # has not run yet is owed to that cover and cannot also be the
            # capital that makes the next sale safe.
            balance = self.own_funds()
        from ..perils import get_peril

        peril = get_peril(peril_key)
        candidate = Exposure(
            policy_id="candidate",
            peril_key=peril_key,
            subject=peril.validate_subject(subject),
            curve=curve or peril.curve_for(subject),
            limit=limit,
            term_days=term_days,
        )

        reasons: list[str] = []

        # Timing first: it is the one reason a bigger pool would not fix, and
        # the buyer should hear it before anything about capital.
        refusal = peril.refuse_to_write(candidate.subject)
        if refusal:
            reasons.append(refusal)

        required = self.required_capital(candidate, book=book)
        if required > balance:
            reasons.append(
                f"writing it would need {required:,.0f} of capital against a pool of "
                f"{balance:,.0f}"
            )

        worst = self.worst_modelled_year(candidate, book=book)
        cap = balance * self.concentration_limit
        if worst > cap and balance > 0:
            reasons.append(
                f"a single modelled year could take {worst:,.0f}, above the "
                f"{self.concentration_limit * 100:.0f}% concentration limit of "
                f"{cap:,.0f}"
            )

        # And what one event takes, which is a different question and was not
        # being asked. At the top of an earthquake's curve every magnitude
        # policy on the fault pays its whole limit at once, so the zone's
        # aggregate is the loss from one rupture there. A pool can pass every
        # test above and still be one earthquake away from nothing.
        if balance > 0:
            zone, held = self.zone_exposure(candidate)
            zone_cap = balance * self.zone_limit
            if held > zone_cap:
                reasons.append(
                    f"this would put {held:,.0f} of cover on {zone}, which pays "
                    f"together: above the {self.zone_limit * 100:.0f}% limit of "
                    f"{zone_cap:,.0f} for one event"
                )

        return (not reasons), reasons

    def write(
        self,
        *,
        peril_key: str,
        subject: dict[str, Any],
        limit: float,
        term_days: float,
        holder: str,
        curve: Any = None,
        now: float | None = None,
        max_premium: float | None = None,
        payer: str | None = None,
        locked: Quote | None = None,
        paid_now: float | None = None,
        simulated: bool = False,
        # The company issuing the policy prices the risk the model measured.
        # Without these the pool's own figures are used, which is what every
        # policy written before companies had their own was priced at.
        cost_of_capital: float | None = None,
        expense_ratio: float | None = None,
    ) -> Policy:
        """Price, check and bind a policy, taking the premium into the pool.

        ``payer`` is who the premium comes from when it is not the holder: a
        company selling cover inside its own product pays for it and the cover,
        and every payout, belongs to the person it insures.

        The price is struck here rather than when the quote was given, because a
        premium depends on the book and the book moves between the two. That is
        correct and it is also a way to charge more than was shown, so a buyer
        may name the most they agreed to pay. If the price has moved past it the
        policy is refused and nothing is taken: better to send someone back for a
        fresh price than to bind them at one they never saw.
        """
        with self.lock:
            from .policy import build_policy

            allowed, reasons = self.can_write(
                peril_key=peril_key, subject=subject, limit=limit,
                term_days=term_days, curve=curve,
            )
            if not allowed:
                raise PoolError("; ".join(reasons))

            # A price the buyer was promised for a while is the price, as long
            # as the pool can still carry the cover; the capital rules above
            # are checked again regardless.
            quoted = locked or self.quote(
                peril_key=peril_key, subject=subject, limit=limit,
                term_days=term_days, curve=curve,
            )
            # The company's own price for it. The expected loss and the capital
            # this policy ties up are the pool's arithmetic and the same
            # whoever writes the cover; what is charged for them is the
            # company's, and it is the figure the buyer was shown on the offer
            # they chose. Applied here too, or the screen and the charge would
            # be two different numbers.
            if cost_of_capital is not None or expense_ratio is not None:
                quoted = quoted.priced_at(
                    cost_of_capital=(cost_of_capital if cost_of_capital is not None
                                     else COST_OF_CAPITAL),
                    expense_ratio=(expense_ratio if expense_ratio is not None
                                   else EXPENSE_RATIO),
                )
            # Quotes are shown in cents. Comparing the agreed figure, rounded to
            # a cent, with a premium carried to many places refused every
            # purchase whose price happened to round down, so the comparison
            # allows the cent that the rounding itself introduced.
            if max_premium is not None and quoted.premium > max_premium + 0.01:
                raise PriceMoved(
                    f"the price moved while you were deciding: {quoted.premium:,.2f} "
                    f"against the {max_premium:,.2f} you agreed to. Nothing was "
                    f"taken; ask for a fresh price."
                )
            policy = build_policy(
                peril_key=peril_key,
                subject=subject,
                limit=limit,
                term_days=term_days,
                holder=holder,
                premium=quoted.premium,
                expected_loss=quoted.expected_loss,
                risk_load=quoted.risk_load,
                expense_load=quoted.expense_load,
                marginal_capital=quoted.marginal_capital,
                curve=curve,
                now=now,
                simulated=simulated,
            )

            # The premium leaves the buyer's address before the policy exists. An
            # address that cannot pay does not get cover, and nothing is recorded.
            # With an instalment plan only the first part is taken now; the
            # rest is owed to the pool and collected on its due dates. The
            # tranches are credited with what was actually received, in the
            # proportions the whole premium would be shared in; each later
            # instalment is credited the same way when it arrives, and what
            # is still owed is written off if the policy ends before then.
            taken = policy.premium if paid_now is None else min(policy.premium, max(0.0, paid_now))
            taken = round(taken, 2)
            if self.wallets is not None:
                self.wallets.debit(
                    payer or holder, taken, policy.policy_id, kind="premium"
                )
            if taken < policy.premium:
                policy.metadata["premium_owed"] = round(policy.premium - taken, 2)

            self.policies[policy.policy_id] = policy
            full = self._premium_split(policy.premium, policy.expected_loss)
            ratio = {k: v / policy.premium for k, v in full.items()} if policy.premium > 0 else {"senior": 1.0}
            split = {k: taken * r for k, r in ratio.items()}
            for name, part in split.items():
                self.tranches[name].balance += part
            policy.metadata["split_ratio"] = {k: round(v, 8) for k, v in ratio.items()}
            policy.metadata["tranche_split"] = {k: round(v, 6) for k, v in split.items()}
            if payer and payer != holder:
                policy.metadata["paid_by"] = payer
            self.premiums_earned += taken
            self._record(
                EntryKind.PREMIUM, taken, payer or holder, policy.policy_id, now, split
            )
            return policy

        # -- settlement -------------------------------------------------------
    def pay(
        self, policy: Policy, index_value: float, *, note: str = "",
        now: float | None = None,
    ) -> float:
        """Settle a triggered policy and move the payout out of the pool."""
        with self.lock:
            from .policy import settle_index

            if not policy.is_open:
                raise PoolError(f"{policy.policy_id} is already {policy.status.value}")

            amount = settle_index(policy, index_value)
            if amount <= 0:
                raise PoolError(
                    f"an index of {index_value} pays nothing on {policy.policy_id}"
                )
            if amount > self.balance:
                # Recorded rather than hidden: a pool that cannot pay must say so.
                raise PoolError(
                    f"{policy.policy_id} is owed {amount:,.2f} and the pool holds "
                    f"{self.balance:,.2f}"
                )

            # Anything still owed on the premium comes off the payout, as
            # every insurer's policy provides.
            owed = float((policy.metadata or {}).get("premium_owed", 0.0))
            withheld = min(owed, amount) if owed > 0 else 0.0
            policy.status = PolicyStatus.PAID
            policy.payout = amount
            policy.settled_index = index_value
            policy.settled_at = now if now is not None else time.time()
            policy.settlement_note = note or (
                f"index of {index_value:g} attested, paid without a claim being filed"
            )

            split = self._lose(amount)
            policy.metadata["tranche_loss"] = {k: round(v, 6) for k, v in split.items()}
            self.claims_paid += amount
            self._record(EntryKind.PAYOUT, -amount, policy.holder, policy.policy_id, now, split)
            if withheld > 0:
                # Collected out of the payout: the pool is paid what it was owed.
                self._book_instalment(policy, withheld)
                policy.metadata["premium_owed"] = round(owed - withheld, 2)
                policy.metadata["withheld_from_payout"] = round(withheld, 2)
                self._record(EntryKind.INSTALMENT, withheld, policy.holder, policy.policy_id, now)
            # The money arrives at the address. Nobody was asked, including the
            # holder, who does not have to be watching for this to happen.
            if self.wallets is not None:
                self.wallets.credit(
                    policy.holder, amount - withheld, policy.policy_id, kind="payout"
                )
            self._notify(policy.holder, amount - withheld, policy.policy_id, "payout")
            return amount
    def lapse(self, policy: Policy, *, note: str = "", now: float | None = None) -> None:
        """Close a policy whose term ended without a trigger."""
        with self.lock:
            if not policy.is_open:
                raise PoolError(f"{policy.policy_id} is already {policy.status.value}")
            policy.status = PolicyStatus.LAPSED
            policy.settled_at = now if now is not None else time.time()
            policy.settlement_note = note or "the term ended without the index triggering"
            self._write_off(policy, now)

    def expire(self, policy: Policy, *, note: str = "", now: float | None = None) -> float:
        """Return the premium on a policy whose data never arrived.

        This is the case a parametric protocol has to name. The index was never
        published, so the policy can settle neither way, and keeping the premium
        would be charging for cover that could not have worked.
        """
        with self.lock:
            if not policy.is_open:
                raise PoolError(f"{policy.policy_id} is already {policy.status.value}")

            meta = policy.metadata or {}
            paid = policy.premium - float(meta.get("premium_owed", 0.0))
            refund = round(max(0.0, paid - float(meta.get("commission", 0.0))), 2)
            if refund > self.balance:
                raise PoolError(
                    f"{policy.policy_id} is owed a refund of {refund:,.2f} and the pool "
                    f"holds {self.balance:,.2f}"
                )

            policy.status = PolicyStatus.EXPIRED
            self._write_off(policy, now)
            policy.settled_at = now if now is not None else time.time()
            policy.settlement_note = note or (
                "the data source never published a settlement reading, so the premium "
                "was returned in full"
            )

            split = self._reverse(self._unpaid_split(policy), refund)
            self.refunds_paid += refund
            self.premiums_earned -= refund
            payer = (policy.metadata or {}).get("paid_by") or policy.holder
            self._record(EntryKind.REFUND, -refund, payer, policy.policy_id, now, split)
            if self.wallets is not None:
                # Back to whoever paid it.
                self.wallets.credit(payer, refund, policy.policy_id, kind="refund")
            self._notify(payer, refund, policy.policy_id, "refund")
            return refund

    def collect(self, policy: Policy, amount: float, *, extra: float = 0.0,
                now: float | None = None) -> float:
        """Take one instalment of a premium still owed, from the holder.

        ``extra`` is a financing surcharge the plan carries on top of the
        premium: income to the pool for carrying the debt, taken in the same
        debit and shared like any other income. Returns the premium part."""
        with self.lock:
            if not policy.is_open:
                return 0.0
            owed = float((policy.metadata or {}).get("premium_owed", 0.0))
            amount = round(min(amount, owed), 2)
            extra = round(max(0.0, extra), 2)
            if amount <= 0 and extra <= 0:
                return 0.0
            if self.wallets is not None:
                self.wallets.debit(policy.holder, amount + extra, policy.policy_id, kind="instalment")
            if amount > 0:
                split = self._book_instalment(policy, amount)
                policy.metadata["premium_owed"] = round(owed - amount, 2)
                self._record(EntryKind.INSTALMENT, amount, policy.holder, policy.policy_id, now, split)
            if extra > 0:
                split = self._gain(extra)
                self.premiums_earned += extra
                policy.metadata["financing_paid"] = round(float(policy.metadata.get("financing_paid", 0.0)) + extra, 2)
                self._record(EntryKind.INSTALMENT, extra, policy.holder, policy.policy_id, now, split)
            return amount

    def _book_instalment(self, policy: Policy, amount: float) -> dict[str, float]:
        """Credit the tranches with premium that has just arrived, in the
        proportions the whole premium is shared in."""
        meta = policy.metadata
        ratio = meta.get("split_ratio") or {"senior": 1.0}
        split = {k: amount * r for k, r in ratio.items()}
        booked = dict(meta.get("tranche_split") or {})
        for name, part in split.items():
            self.tranches[name].balance += part
            booked[name] = round(booked.get(name, 0.0) + part, 6)
        meta["tranche_split"] = booked
        self.premiums_earned += amount
        return split

    def _write_off(self, policy: Policy, now: float | None) -> None:
        """Forget what a policy still owed: it ends, and so does the debt."""
        owed = float((policy.metadata or {}).get("premium_owed", 0.0))
        if owed > 0:
            policy.metadata["premium_owed"] = 0.0
            policy.metadata["written_off"] = round(owed, 2)
            self._record(EntryKind.INSTALMENT, 0.0, policy.holder, policy.policy_id, now)

    def cancel(self, policy: Policy, *, note: str = "", now: float | None = None,
               refund: float | None = None) -> float:
        """End a policy at the holder's request, returning all of the premium
        or, where only part is owed back, that part."""
        with self.lock:
            if not policy.is_open:
                raise PoolError(f"{policy.policy_id} is already {policy.status.value}")
            if (policy.metadata or {}).get("provisional"):
                raise PoolError("the index has already been reached; this policy is settling")
            meta = policy.metadata or {}
            # Paid in parts: only what was paid can come back, and what was
            # still owed is written off with the policy.
            owed = float(meta.get("premium_owed", 0.0))
            paid = policy.premium - owed
            whole = max(0.0, paid - float(meta.get("commission", 0.0)))
            refund = whole if refund is None else max(0.0, min(float(refund), whole))
            refund = round(refund, 2)
            if refund > self.balance:
                raise PoolError(f"{policy.policy_id} is owed {refund:,.2f} and the pool holds {self.balance:,.2f}")
            self._write_off(policy, now)
            policy.status = PolicyStatus.CANCELLED
            policy.settled_at = now if now is not None else time.time()
            policy.settlement_note = note or "cancelled at the holder's request, premium returned"
            unpaid = self._unpaid_split(policy)
            scale = refund / whole if whole > 0 else 0.0
            split = self._reverse({k: v * scale for k, v in unpaid.items()}, refund)
            self.refunds_paid += refund
            self.premiums_earned -= refund
            payer = (policy.metadata or {}).get("paid_by") or policy.holder
            self._record(EntryKind.REFUND, -refund, payer, policy.policy_id, now, split)
            if self.wallets is not None:
                self.wallets.credit(payer, refund, policy.policy_id, kind="refund")
            self._notify(payer, refund, policy.policy_id, "refund")
            return refund

    def _unpaid_split(self, policy: Policy) -> dict[str, float]:
        """What each tranche still holds of this premium, net of commission."""
        meta = policy.metadata or {}
        split = dict(meta.get("tranche_split") or {})
        for name, part in (meta.get("commission_split") or {}).items():
            split[name] = split.get(name, 0.0) - part
        return split

    def pay_commission(self, policy: Policy, account: str, amount: float,
                       *, now: float | None = None) -> float:
        """Pay a distributor its share of a premium it sold, out of that premium."""
        with self.lock:
            if amount <= 0:
                return 0.0
            if not policy.is_open:
                raise PoolError(f"{policy.policy_id} is already {policy.status.value}")
            if "commission" in (policy.metadata or {}):
                raise PoolError(f"{policy.policy_id} has already paid its commission")
            paid = round(policy.premium - float((policy.metadata or {}).get("premium_owed", 0.0)), 2)
            amount = min(amount, paid)
            if amount <= 0:
                return 0.0
            split = self._reverse(dict((policy.metadata or {}).get("tranche_split") or {}), amount)
            policy.metadata["commission"] = round(amount, 6)
            policy.metadata["commission_split"] = {k: round(v, 6) for k, v in split.items()}
            policy.metadata["commission_to"] = account
            self.premiums_earned -= amount
            self._record(EntryKind.COMMISSION, -amount, account, policy.policy_id, now, split)
            if self.wallets is not None:
                self.wallets.credit(account, amount, policy.policy_id, kind="commission")
            return amount

    # -- ledger -----------------------------------------------------------
    def _notify(self, account: str, amount: float, reference: str, kind: str) -> None:
        """Tell whoever routes money off the protocol that some has arrived."""
        for listener in list(self.listeners):
            try:
                listener(account, amount, reference, kind)
            except Exception:  # a router failing must never undo a settlement
                import logging
                logging.getLogger("clause.pool").exception("payout listener failed")

    def _record(
        self, kind: EntryKind, amount: float, account: str, reference: str,
        now: float | None, split: dict[str, float] | None = None,
    ) -> None:
        self.ledger.append(
            LedgerEntry(
                at=now if now is not None else time.time(),
                kind=kind,
                amount=amount,
                account=account,
                reference=reference,
                balance_after=self.balance,
                split={k: v for k, v in (split or {}).items() if v},
            )
        )

    def check_ledger(self) -> None:
        """Replay the ledger and confirm it lands on the current balance.

        Cheap, and the only way to know the accounting has not drifted.
        """
        running = 0.0
        for entry in self.ledger:
            running += entry.amount
            if abs(running - entry.balance_after) > 1e-6:
                raise PoolError(
                    f"ledger disagrees at {entry.reference}: running total "
                    f"{running:.6f} against recorded {entry.balance_after:.6f}"
                )
        if abs(running - self.balance) > 1e-6:
            raise PoolError(
                f"ledger sums to {running:.6f} against a balance of {self.balance:.6f}"
            )

    # -- views ------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        position = self.engine.position(self.exposures())
        required = position.solvency_capital * self.capital_buffer
        open_policies = self.open_policies
        exposure = sum(policy.exposure_remaining() for policy in open_policies)
        unearned = self.unearned_premium()
        own = max(0.0, self.balance - unearned)

        return {
            "balance": round(self.balance, 2),
            "share_price": round(self.share_price, 6),
            "total_shares": round(self.total_shares, 6),
            "providers": len({p.account for p in self.providers.values() if p.shares > 0 and p.account != RETAINED}),
            "open_policies": len(open_policies),
            "total_policies": len(self.policies),
            "limit_at_risk": round(exposure, 2),
            "premiums_earned": round(self.premiums_earned, 2),
            "claims_paid": round(self.claims_paid, 2),
            "refunds_paid": round(self.refunds_paid, 2),
            "underwriting_result": round(
                self.premiums_earned - self.claims_paid, 2
            ),
            "required_capital": round(required, 2),
            "free_capital": round(max(0.0, self.balance - required), 2),
            "solvency_ratio": round(
                self.balance / required, 4
            ) if required > 0 else None,
            # The two the writing rule itself measures against. The balance
            # holds premium taken for cover that has not run yet, which is owed
            # to that cover; a page that shows only the balance shows a pool
            # larger than the one the next sale is tested against.
            "unearned_premium": round(unearned, 2),
            "own_funds": round(own, 2),
            "own_funds_ratio": round(own / required, 4) if required > 0 else None,
            "capital_position": position.to_dict(),
            "concentration_limit": self.concentration_limit,
            "tranches": [
                {"name": n, "balance": round(self.tranches[n].balance, 2),
                 "share_price": round(self.tranches[n].price, 6),
                 "yield_weight": YIELD_WEIGHT[n]}
                for n in TRANCHES
            ],
        }

    def risk_view(self) -> dict[str, Any]:
        """The pool's own exposure, by peril and by accumulation."""
        result = self.engine.simulate(self.exposures())
        by_peril: dict[str, dict[str, float]] = {}
        for key, losses in result.by_peril.items():
            mean = sum(losses) / len(losses) if losses else 0.0
            by_peril[key] = {
                "expected_loss": round(mean, 2),
                "worst_modelled": round(max(losses), 2) if losses else 0.0,
            }

        accumulation = self.accumulation()

        return {
            "by_peril": by_peril,
            "accumulation": dict(
                sorted(accumulation.items(), key=lambda item: -item[1])
            ),
            "exceedance_curve": result.exceedance_curve(),
            "worst_modelled_year": round(max(result.losses), 2) if result.losses else 0.0,
            "unearned_premium": self.unearned_premium(),
            "own_funds": round(self.own_funds(), 2),
            "concentration_cap": round(self.own_funds() * self.concentration_limit, 2),
            "zone_cap": round(self.own_funds() * self.zone_limit, 2),
            "tranches": self.tranche_view(result.losses),
            "subordination_years": SUBORDINATION_YEARS,
        }


def _accumulation_key(policy: Policy) -> str:
    """How exposure is grouped when asking what pays together.

    For earthquake the grouping is the fault system a site sits on rather than
    the site itself, because that is what actually accumulates: two towns a
    hundred kilometres apart on the same fault are one exposure to one rupture
    sequence, and grouping them by name would hide exactly the concentration the
    capital rules exist to catch.
    """
    subject = policy.subject
    if policy.peril_key == "earthquake":
        from ..perils import EARTHQUAKE
        from ..perils.geo import site_at

        grid = EARTHQUAKE.grid_model(subject)
        if grid is not None:
            # No fault map outside Türkiye: group by the whole degree square,
            # about a hundred kilometres, the scale one large event reaches.
            lat, lon = float(subject["latitude"]), float(subject["longitude"])
            return f"earthquake near {grid.name} {round(lat)}°, {round(lon)}°"

        site = site_at(subject["latitude"], subject["longitude"])
        where = site.nearest.name if site.nearest else site.zone_name
        return f"earthquake on {where}"
    if policy.peril_key == "drought":
        return f"drought at {subject['station']}"
    if policy.peril_key == "flight_delay":
        return (
            f"flights on {subject.get('origin', '')} to {subject.get('destination', '')}"
            if subject.get("origin") else f"flights on {subject.get('route', '')}"
        )
    if policy.peril_key == "storm":
        # One front takes the roofs of a whole province; two provinces apart
        # share less, and the capital model carries that as correlation.
        return f"storm at {subject.get('station', '')}"
    return policy.peril_key


def seed_providers(pool: Pool, entries: Iterable[tuple[str, float]]) -> None:
    """Convenience for setting a pool up with capital already in it."""
    for account, amount in entries:
        pool.deposit(account, amount)
