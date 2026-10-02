"""Nine companies quoted one price to the penny, and it was the pool's.

The offers endpoint said so in its own docstring -- "the pool's premium is the
same whoever issues it: the risk is the risk" -- and what differed between nine
companies was the fee each added on top, two per cent to six. Measured live,
that made a market of nine look like one price with nine names: every row read
2,633.21 and the totals spanned seven per cent.

A price has three parts and only one of them is the risk. The expected loss is
the model's answer and every company reads the same one; no insurer disputes an
exceedance curve, they dispute what to charge for it. What the capital a policy
ties up must earn, and what it costs to run the business holding it, were a
single figure inside the pricing engine. They belong to whoever is writing.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from clause.pricing.engine import COST_OF_CAPITAL, EXPENSE_RATIO, loads_for
from clause.protocol.carrier import (
    Appetite, Carrier, CarrierError, Licence, Reach, Role,
    Settlement, most_it_will_write, priced_by, specimen_registry,
)

RISK = {"expected_loss": 1000.0, "marginal_capital": 20000.0, "term_days": 365.0}


def test_a_company_that_says_nothing_prices_as_the_pool_always_did() -> None:
    """Nothing moves for a company registered before either was asked for."""
    lean = specimen_registry().carriers["specimen-tr-four"]
    plain = Carrier(
        carrier_id="plain", name="States neither", role=Role.CARRIER, domicile="TR",
        licences=lean.licences, appetite=lean.appetite, capacity=1_000_000,
    )
    assert plain.cost_of_capital == COST_OF_CAPITAL
    assert plain.expense_ratio == EXPENSE_RATIO

    said = priced_by(plain, **RISK)
    # Against loads_for, which is what priced_by calls: the two agree, which
    # says the company's own figures are not being substituted anywhere.
    risk_load, expense_load, premium = loads_for(
        cost_of_capital=COST_OF_CAPITAL, expense_ratio=EXPENSE_RATIO, **RISK)
    assert said["premium"] == pytest.approx(round(premium, 2))
    assert said["risk_load"] == pytest.approx(round(risk_load, 2))
    assert said["expense_load"] == pytest.approx(round(expense_load, 2))

    # And against the arithmetic, written out here rather than fetched.
    #
    # The three assertions above were the whole of it, and both sides of each
    # is loads_for on the same inputs: any error inside it is invisible to
    # them. That function is where a company's offer, the price lock and the
    # policy that is finally bound are all priced -- "Here once, so an offer,
    # a price lock and the policy that is finally bound cannot answer
    # differently" -- and it is the figure that leaves the buyer's wallet.
    # Measured by mutating it: doubling the capital charge passed 146 tests
    # across nine money files, dropping the term passed, and setting the
    # expense load to zero passed. The whole suite caught the doubling only
    # through a 409 about two prices disagreeing, and caught a halved
    # EXPENSE_RATIO not at all.
    #
    # 20,000 of marginal capital at 12% for 365 of 365.25 days, plus 8% of a
    # 1,000 expected loss, plus the expected loss itself.
    assert said["risk_load"] == pytest.approx(2398.36, abs=0.01)
    assert said["expense_load"] == pytest.approx(80.00, abs=0.01)
    assert said["premium"] == pytest.approx(3478.36, abs=0.02)

    # The two constants, against their published values rather than against
    # the defaults they are. A company that says nothing takes them, so
    # comparing the default to the constant that is the default was true for
    # any value of either: a cost of capital raised from 12% to 50% passed
    # this file untouched.
    assert COST_OF_CAPITAL == 0.12
    assert EXPENSE_RATIO == 0.08


def test_the_same_risk_is_priced_differently_by_different_companies() -> None:
    """Which is the whole of it: a list of nine is a market or it is theatre.

    The expected loss is the same figure for all of them, because it is the
    model's and not anybody's opinion. Everything above it moves.
    """
    registry = specimen_registry()
    turkish = [c for c in registry.carriers.values()
               if c.domicile == "TR" and "earthquake" in c.appetite.perils]
    assert len(turkish) >= 4, "too few companies to be a market"

    quoted = {c.carrier_id: priced_by(c, **RISK) for c in turkish}
    premiums = {round(q["premium"], 2) for q in quoted.values()}
    assert len(premiums) == len(quoted), "two companies still quote the same price"

    losses = {q["expected_loss"] for q in quoted.values()}
    assert len(losses) == 1, "companies disagree about the risk itself, which they cannot"

    totals = sorted(q["total"] for q in quoted.values())
    assert totals[-1] / totals[0] > 1.25, (
        f"the cheapest and the dearest are within {100 * (totals[-1] / totals[0] - 1):.0f}%; "
        "that is a rounding difference, not a market")


def test_a_keener_price_on_a_smaller_line_is_a_different_offer() -> None:
    """So the offer carries what the company would actually write.

    A buyer comparing two companies is comparing this as much as the price. A
    company that will take 150,000 and one that will take 500,000 are not
    offering the same thing at two prices.
    """
    registry = specimen_registry()
    lines = {c.carrier_id: most_it_will_write(c)
             for c in registry.carriers.values()
             if c.domicile == "TR" and "earthquake" in c.appetite.perils}
    assert len(set(lines.values())) > 1, "every company writes the same line"
    assert min(lines.values()) > 0

    # And it is the smaller of what it wants and what it has left, which only
    # shows on a company that has written something: on an empty book the
    # appetite always binds and the room is never tested.
    one = registry.carriers["specimen-tr-four"]
    room = one.appetite.max_limit / 2
    filled = replace(one, in_force=one.capacity - room)
    assert most_it_will_write(one) == one.appetite.max_limit
    assert most_it_will_write(filled) == pytest.approx(room), (
        "a company nearly full still offers the whole line its appetite allows")


def test_a_price_nobody_could_charge_is_refused() -> None:
    """Both figures set what a buyer pays, so both are bounded."""
    base = specimen_registry().carriers["specimen-tr-four"]
    for bad in ({"cost_of_capital": 0.0}, {"cost_of_capital": 0.8},
                {"expense_ratio": -0.1}, {"expense_ratio": 0.9}):
        with pytest.raises(CarrierError):
            Carrier(
                carrier_id="bad", name="Out of bounds", role=Role.CARRIER, domicile="TR",
                licences=base.licences, appetite=base.appetite, capacity=1_000_000, **bad)
