"""What a policy actually costs, in numbers.

An independent pass over the suite mutation-tested 55 assertions and found
sixteen that could not fail. The worst of them was this: no test anywhere
asserted a price *figure*. The two tests that look like they do are both
identities --

    assert quote.premium == approx(quote.expected_loss + quote.risk_load
                                   + quote.expense_load)

is the definition of premium read back, true for any three numbers, and
test_carrier_prices compares priced_by() with loads_for() where priced_by
does nothing but call loads_for.

Proved: EXPENSE_RATIO 0.08 -> 0.0, which removes eight per cent of the
expected loss from every premium the protocol quotes, left the whole suite
green. So did doubling the buyer's capital charge in loads_for (146 tests
across nine money files), doubling the quoted capital charge (99 tests, and
x1.5 and x1.25 too), and dropping the term factor from the risk load.

The suite could only see a price change by side effect: when the pool's quote
and the company's price stopped agreeing and the API answered 409, when a
"more than twice" ratio between two premiums stopped holding, or when a
premium grew enough to exhaust a test wallet. A constant edited by one digit
moves every price together, keeps every ratio, and trips none of them.

So: five policies, one per peril, priced by an engine with a fixed seed, and
the four figures each of them comes out at. PricingEngine(trials, seed) is
deterministic -- a fresh engine on the same seed returns the same premium to
the sixth decimal, measured -- so these are facts about the code and not
about the machine.

When a price is *meant* to move, these numbers move with it, and the diff
says by how much on each peril. That is the point of them. To re-pin, run:

    PYTHONPATH=. .venv/bin/python -m pytest tests/test_pricing_figures.py \
        -q -k repin -s
"""

from __future__ import annotations

import pytest

from clause.pricing import PricingEngine

TRIALS = 4_000
SEED = 99
#: To the cent. The engine is deterministic, so a wider tolerance would only
#: hide the smaller of the two mutations that went unnoticed.
TO_THE_CENT = 0.005

#: peril, subject, limit, term -> premium, expected loss, risk load, expenses
GOLDEN = [
    ("earthquake",
     {"latitude": 40.99, "longitude": 29.03, "radius_km": 50.0,
      "place": "İstanbul, Kadıköy"}, 100_000.0, 365.0,
     (15372.84, 3542.55, 11546.89, 283.40)),
    ("earthquake",
     {"latitude": 37.76, "longitude": 38.28, "radius_km": 100.0,
      "place": "Adıyaman"}, 50_000.0, 365.0,
     (9588.22, 3455.79, 5855.96, 276.46)),
    ("storm",
     {"latitude": 41.0, "longitude": 28.9, "station": "İstanbul",
      "country": "TR", "distance_km": 6.8}, 40_000.0, 365.0,
     (5612.88, 838.82, 4706.96, 67.11)),
    ("vehicle_flood",
     {"latitude": 41.0, "longitude": 28.9, "station": "İstanbul",
      "country": "TR", "distance_km": 6.8}, 30_000.0, 365.0,
     (4937.93, 1408.99, 3416.22, 112.72)),
    ("drought",
     {"station": "TR-KONYA", "distance_km": 8.0, "hectares": 50.0},
     60_000.0, 150.0,
     (10800.95, 7595.27, 2598.06, 607.62)),
]

PARTS = ("premium", "expected_loss", "risk_load", "expense_load")


@pytest.fixture(scope="module")
def engine() -> PricingEngine:
    return PricingEngine(trials=TRIALS, seed=SEED)


def priced(engine: PricingEngine, peril: str, subject: dict, limit: float,
           term: float):
    return engine.quote(peril_key=peril, subject=subject, limit=limit,
                        term_days=term, book=[])


@pytest.mark.parametrize("peril,subject,limit,term,figures", GOLDEN,
                         ids=[f"{row[0]}-{row[2]:.0f}" for row in GOLDEN])
def test_the_price_is_the_price(engine, peril, subject, limit, term,
                                figures) -> None:
    quote = priced(engine, peril, subject, limit, term)
    for name, want in zip(PARTS, figures):
        got = getattr(quote, name)
        assert abs(got - want) < TO_THE_CENT, (
            f"{peril} at {limit:,.0f}: {name} is {got:.2f}, was {want:.2f}. "
            f"If that is deliberate, re-pin this file; if it is not, a "
            f"constant moved.")


def test_a_fresh_engine_on_the_same_seed_says_the_same(engine) -> None:
    """Which is what makes the figures above facts about the code. Without
    this they would be facts about one run."""
    peril, subject, limit, term, figures = GOLDEN[0]
    again = priced(PricingEngine(trials=TRIALS, seed=SEED), peril, subject,
                   limit, term)
    assert abs(again.premium - figures[0]) < TO_THE_CENT
    assert again.premium == pytest.approx(
        priced(engine, peril, subject, limit, term).premium, abs=1e-9)


def test_the_parts_are_the_whole(engine) -> None:
    """The identity the old test asserted on its own. It is worth keeping --
    as well as the figures, not instead of them."""
    for peril, subject, limit, term, _figures in GOLDEN:
        quote = priced(engine, peril, subject, limit, term)
        assert quote.premium == pytest.approx(
            quote.expected_loss + quote.risk_load + quote.expense_load)


def test_the_expense_load_is_actually_loaded(engine) -> None:
    """Named, because zeroing EXPENSE_RATIO is the mutation that passed 1303
    tests. Eight per cent of the expected loss, in every premium."""
    from clause.pricing.engine import EXPENSE_RATIO

    assert EXPENSE_RATIO > 0
    for peril, subject, limit, term, _figures in GOLDEN:
        quote = priced(engine, peril, subject, limit, term)
        assert quote.expense_load == pytest.approx(
            quote.expected_loss * EXPENSE_RATIO, rel=1e-6), peril
        assert quote.expense_load > 0, peril


@pytest.mark.skip(reason="run with -k repin -s to print fresh figures")
def test_repin() -> None:
    engine = PricingEngine(trials=TRIALS, seed=SEED)
    for peril, subject, limit, term, _figures in GOLDEN:
        quote = priced(engine, peril, subject, limit, term)
        print(f'    ("{peril}",\n     {subject!r}, {limit}, {term},\n'
              f'     ({quote.premium:.2f}, {quote.expected_loss:.2f}, '
              f'{quote.risk_load:.2f}, {quote.expense_load:.2f})),')
