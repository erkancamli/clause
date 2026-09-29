"""Pricing and capital.

The claim being tested is the one the protocol is built on: the price of a
policy depends on the book it joins. A test suite that only checked a premium
came out positive would not notice if that broke, so the behaviour under
different books is what is pinned down here.
"""

from __future__ import annotations

import pytest

from clause.perils import DROUGHT, EARTHQUAKE, FLIGHT_DELAY
from clause.pricing import (
    SOLVENCY_LEVEL,
    Exposure,
    PricingEngine,
    SimulationResult,
    WorldDraws,
    capital_from_losses,
    settle,
)

TRIALS = 4_000

from conftest import FLIGHT_DATE


@pytest.fixture(scope="module")
def engine() -> PricingEngine:
    return PricingEngine(trials=TRIALS, seed=99)


def quake(policy_id: str, location: str, limit: float = 100_000.0, radius: float = 50.0) -> Exposure:
    return Exposure(
        policy_id=policy_id,
        peril_key="earthquake",
        subject={"location": location, "radius_km": radius},
        curve=EARTHQUAKE.default_curve(),
        limit=limit,
        term_days=365,
    )


def drought(policy_id: str, station: str, limit: float = 60_000.0) -> Exposure:
    return Exposure(
        policy_id=policy_id,
        peril_key="drought",
        subject={"station": station, "distance_km": 8.0, "hectares": 50.0},
        curve=DROUGHT.default_curve(),
        limit=limit,
        term_days=150,
    )


def flight(policy_id: str, limit: float = 1_500.0) -> Exposure:
    return Exposure(
        policy_id=policy_id,
        peril_key="flight_delay",
        subject={
            "route": "TK-IST-LHR",
            "flight_number": f"TK{policy_id[-3:]}",
            "departure_date": FLIGHT_DATE,
        },
        curve=FLIGHT_DELAY.default_curve(),
        limit=limit,
        term_days=2,
    )


# ---------------------------------------------------------------------------
# Loss measures
# ---------------------------------------------------------------------------


def test_value_at_risk_reads_the_right_point() -> None:
    losses = [float(i) for i in range(100)]
    result = SimulationResult(losses=losses, trials=100)
    assert result.value_at_risk(0.95) == 94.0
    assert result.value_at_risk(0.50) == 49.0


def test_tail_measure_averages_beyond_the_point() -> None:
    losses = [0.0] * 98 + [100.0, 900.0]
    result = SimulationResult(losses=losses, trials=100)
    assert result.value_at_risk(0.99) == 100.0
    assert result.tail_value_at_risk(0.99) == 500.0


def test_the_tail_measure_notices_what_the_point_cannot() -> None:
    """Two books with the same value at risk and very different tails."""
    mild = SimulationResult(losses=[0.0] * 99 + [100.0], trials=100)
    severe = SimulationResult(losses=[0.0] * 99 + [10_000.0], trials=100)
    assert mild.value_at_risk(0.99) == severe.value_at_risk(0.99) == 0.0
    assert severe.tail_value_at_risk(0.99) > mild.tail_value_at_risk(0.99) * 50


def test_capital_is_the_gap_between_the_tail_and_expectation() -> None:
    losses = [0.0] * 990 + [1_000.0] * 10
    position = capital_from_losses(losses, 1000)
    assert position.expected_loss == pytest.approx(10.0)
    assert position.tail_at_standard == pytest.approx(1_000.0)
    assert position.solvency_capital == pytest.approx(990.0)


def test_capital_on_an_empty_book_is_nothing() -> None:
    position = capital_from_losses([0.0] * 100, 100)
    assert position.solvency_capital == 0.0


# ---------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------


def test_the_world_is_reproducible() -> None:
    a = WorldDraws.draw(trials=500, years=1.0, seed=7)
    b = WorldDraws.draw(trials=500, years=1.0, seed=7)
    assert a.ruptures == b.ruptures
    assert a.rain_uniform == b.rain_uniform
    # And the conversion to millimetres is deterministic, so two draws of one
    # seed give the same season for the same station.
    assert a.rainfall("TR-KONYA") == b.rainfall("TR-KONYA")


def test_settling_a_policy_does_not_depend_on_the_rest_of_the_book() -> None:
    """Common random numbers, without which a marginal charge is noise."""
    draws = WorldDraws.draw(trials=800, years=1.0, seed=11)
    once = settle(quake("a", "IST-KADIKOY"), draws)
    again = settle(quake("a", "IST-KADIKOY"), draws)
    assert once == again


def test_two_policies_at_one_location_pay_together() -> None:
    """The correlation the capital model exists to price."""
    draws = WorldDraws.draw(trials=3_000, years=1.0, seed=13)
    first = settle(quake("a", "IST-KADIKOY"), draws)
    second = settle(quake("b", "IST-KADIKOY"), draws)

    both = sum(1 for x, y in zip(first, second) if x > 0 and y > 0)
    either = sum(1 for x, y in zip(first, second) if x > 0 or y > 0)
    assert either > 0
    # They are not independent: most trials that pay one pay the other.
    assert both / either > 0.5


def test_policies_in_different_cities_are_far_less_correlated() -> None:
    draws = WorldDraws.draw(trials=3_000, years=1.0, seed=13)
    istanbul = settle(quake("a", "IST-KADIKOY"), draws)
    ankara = settle(quake("b", "ANK-CANKAYA"), draws)

    both = sum(1 for x, y in zip(istanbul, ankara) if x > 0 and y > 0)
    either = sum(1 for x, y in zip(istanbul, ankara) if x > 0 or y > 0)
    assert either > 0
    assert both / either < 0.2


def test_a_tighter_radius_pays_less_often() -> None:
    draws = WorldDraws.draw(trials=3_000, years=1.0, seed=17)
    wide = settle(quake("a", "IST-KADIKOY", radius=100.0), draws)
    tight = settle(quake("b", "IST-KADIKOY", radius=25.0), draws)
    assert sum(1 for x in wide if x > 0) >= sum(1 for x in tight if x > 0)


def test_drought_policies_on_one_station_pay_together() -> None:
    draws = WorldDraws.draw(trials=2_000, years=1.0, seed=19)
    first = settle(drought("a", "TR-KONYA"), draws)
    second = settle(drought("b", "TR-KONYA"), draws)
    for x, y in zip(first, second):
        assert (x > 0) == (y > 0)


# ---------------------------------------------------------------------------
# Quoting
# ---------------------------------------------------------------------------


def test_a_premium_is_its_three_parts(engine: PricingEngine) -> None:
    quote = engine.quote(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365, book=[],
    )
    assert quote.premium == pytest.approx(
        quote.expected_loss + quote.risk_load + quote.expense_load
    )
    assert quote.expected_loss > 0
    assert quote.risk_load > 0
    assert 0 < quote.rate_on_line < 1


def test_expected_loss_matches_the_perils_own_model(engine: PricingEngine) -> None:
    """Exact rather than sampled, which is why it comes from the model."""
    subject = {"location": "IST-KADIKOY", "radius_km": 50.0}
    quote = engine.quote(
        peril_key="earthquake", subject=subject, limit=100_000, term_days=365,
    )
    # The curve for this subject, not the default one. They used to be the
    # same thing here, because a subject with no year built was priced as a
    # building of the current code and that is where the default curve sits.
    # An unsaid year is the oldest building now, so the curve it is priced on
    # is the shifted one and the test has to ask for that.
    share = EARTHQUAKE.curve_for(EARTHQUAKE.validate_subject(subject)).expected_share(
        EARTHQUAKE.exceedance(EARTHQUAKE.validate_subject(subject), 365)
    )
    assert quote.expected_loss == pytest.approx(100_000 * share, rel=1e-12)


def test_premium_scales_with_the_limit(engine: PricingEngine) -> None:
    small = engine.quote(
        peril_key="drought",
        subject={"station": "TR-KONYA", "distance_km": 8, "hectares": 50},
        limit=50_000, term_days=150,
    )
    large = engine.quote(
        peril_key="drought",
        subject={"station": "TR-KONYA", "distance_km": 8, "hectares": 50},
        limit=100_000, term_days=150,
    )
    assert large.expected_loss == pytest.approx(small.expected_loss * 2)
    assert large.premium > small.premium


def test_the_same_policy_costs_less_against_a_diversified_book(
    engine: PricingEngine,
) -> None:
    """The protocol's central claim, in one assertion."""
    subject = {"location": "IST-KADIKOY", "radius_km": 50.0}

    concentrated = [quake(f"i{i}", "IST-KADIKOY") for i in range(12)]
    elsewhere = [flight(f"f{i:03d}") for i in range(12)] + [
        drought(f"d{i}", "TR-KONYA") for i in range(6)
    ]

    onto_concentrated = engine.quote(
        peril_key="earthquake", subject=subject, limit=100_000,
        term_days=365, book=concentrated,
    )
    onto_elsewhere = engine.quote(
        peril_key="earthquake", subject=subject, limit=100_000,
        term_days=365, book=elsewhere,
    )

    assert onto_elsewhere.premium < onto_concentrated.premium
    assert onto_elsewhere.marginal_capital < onto_concentrated.marginal_capital


def test_a_quiet_location_is_far_cheaper_than_a_crowded_one(
    engine: PricingEngine,
) -> None:
    book = [quake(f"i{i}", "IST-KADIKOY") for i in range(12)]

    istanbul = engine.quote(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365, book=book,
    )
    ankara = engine.quote(
        peril_key="earthquake",
        subject={"location": "ANK-CANKAYA", "radius_km": 50},
        limit=100_000, term_days=365, book=book,
    )

    assert ankara.premium < istanbul.premium
    # Ankara sits on no mapped system and correlates with nothing in a book of
    # Istanbul cover, so the pool carries it almost for free.
    assert ankara.diversification in {"diversifying", "absorbed"}
    assert ankara.marginal_capital < istanbul.marginal_capital
    assert istanbul.diversification in {"standalone", "concentrating"}


def test_the_verdict_compares_against_standing_alone(engine: PricingEngine) -> None:
    """A low frequency peril always needs capital many times its expected loss,
    so the verdict has to be relative to the same risk written alone."""
    book = [flight(f"f{i:03d}") for i in range(20)]
    quote = engine.quote(
        peril_key="earthquake",
        subject={"location": "ADY-MERKEZ", "radius_km": 50},
        limit=100_000, term_days=365, book=book,
    )
    assert quote.standalone_capital > 0
    assert quote.marginal_capital <= quote.standalone_capital * 1.2
    assert 0 <= quote.diversification_ratio


def test_the_quote_explains_itself(engine: PricingEngine) -> None:
    book = [quake(f"i{i}", "IST-KADIKOY") for i in range(4)]
    quote = engine.quote(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365, book=book,
    )
    joined = " ".join(quote.notes)
    assert "already holds" in joined
    assert "North Anatolian Fault" in joined


def test_the_radius_lever_is_explained_in_the_quote(engine: PricingEngine) -> None:
    """The buyer's main control over basis risk, so it is spelled out."""
    tight = engine.quote(
        peril_key="earthquake",
        subject={"location": "ADY-MERKEZ", "radius_km": 25},
        limit=100_000, term_days=365,
    )
    joined = " ".join(tight.notes)
    assert "East Anatolian Fault" in joined
    assert "radius" in joined

    wide = engine.quote(
        peril_key="earthquake",
        subject={"location": "ADY-MERKEZ", "radius_km": 100},
        limit=100_000, term_days=365,
    )
    assert wide.expected_loss > tight.expected_loss


def test_a_seismic_gap_is_disclosed_rather_than_only_priced(
    engine: PricingEngine,
) -> None:
    """A buyer paying more for the Marmara should be told why."""
    quote = engine.quote(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365,
    )
    joined = " ".join(quote.notes)
    assert "has not ruptured" in joined


def test_quote_rejects_a_bad_limit_or_term(engine: PricingEngine) -> None:
    for kwargs in ({"limit": 0}, {"limit": -1}, {"term_days": 0}):
        with pytest.raises(ValueError):
            engine.quote(
                peril_key="earthquake",
                subject={"location": "IST-KADIKOY", "radius_km": 50},
                **{"limit": 1000, "term_days": 365, **kwargs},
            )


def test_quoting_is_deterministic(engine: PricingEngine) -> None:
    book = [quake(f"i{i}", "IZM-KONAK") for i in range(5)]
    first = engine.quote(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365, book=book,
    )
    second = engine.quote(
        peril_key="earthquake",
        subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365, book=book,
    )
    assert first.premium == second.premium


def test_the_book_cache_returns_the_same_losses(engine: PricingEngine) -> None:
    book = [quake(f"c{i}", "IZM-KONAK") for i in range(6)]
    first = engine.book_losses(book)
    second = engine.book_losses(book)
    assert first is second


def test_capital_rises_as_the_book_concentrates(engine: PricingEngine) -> None:
    thin = [quake(f"t{i}", "IST-KADIKOY") for i in range(3)]
    thick = [quake(f"t{i}", "IST-KADIKOY") for i in range(12)]
    assert (
        engine.position(thick).solvency_capital
        > engine.position(thin).solvency_capital
    )


def test_the_solvency_standard_is_a_half_percent_tail() -> None:
    assert SOLVENCY_LEVEL == 0.995


def test_the_quote_does_not_claim_a_distance_it_never_priced(engine: PricingEngine) -> None:
    """Past twenty kilometres the quote used to tell a farmer that the gap
    between their field and the station was priced for.

    It was not, at any distance. The payout follows the station's reading, so
    what the pool pays does not depend on where the field is -- which is why
    the two quotes below come out identical, and why loading the distant one
    would be charging for a risk the pool does not carry. The gap is the
    buyer's, and it is the whole of what they give up by buying an index
    rather than an adjuster. The quote says that now.
    """
    def priced(distance_km: float):
        return engine.quote(
            peril_key="drought",
            subject={"station": "TR-KONYA", "distance_km": distance_km, "hectares": 50},
            limit=80_000, term_days=150, book=[],
        )

    near, far = priced(1.0), priced(59.0)
    assert far.premium == pytest.approx(near.premium), (
        "if distance moved the premium, the old sentence would have been true")

    said = " ".join(far.notes)
    assert "priced for it" not in said
    assert "not in the premium and cannot be" in said
    # And the number it rests on is still shown, because it is the one thing
    # the buyer can use to judge the trade.
    verdict, correlation = DROUGHT.basis_risk_for(
        DROUGHT.validate_subject({"station": "TR-KONYA", "distance_km": 59.0,
                                  "hectares": 50}))
    assert f"{correlation:.2f}" in said
    assert correlation < 0.2, "at this separation the index barely follows the field"


# ---------------------------------------------------------------------------
# The floor under the marginal charge
# ---------------------------------------------------------------------------


def _new_york(limit: float = 100_000.0) -> dict:
    return EARTHQUAKE.validate_subject(
        {"latitude": 40.7128, "longitude": -74.0060, "radius_km": 50, "index": "shaking"})


def _istanbul_book(engine: PricingEngine, count: int = 40) -> list[Exposure]:
    """A book concentrated where the live one is, so its tail is Turkish."""
    here = [(41.02, 28.95), (40.99, 29.03), (41.05, 29.00), (40.97, 29.09)]
    out = []
    for i in range(count):
        latitude, longitude = here[i % len(here)]
        subject = EARTHQUAKE.validate_subject(
            {"latitude": latitude, "longitude": longitude, "radius_km": 50,
             "index": "shaking"})
        out.append(Exposure(policy_id=f"tr-{i}", peril_key="earthquake", subject=subject,
                            curve=EARTHQUAKE.curve_for(subject), limit=100_000.0,
                            term_days=365.0))
    return out


def test_a_risk_the_book_never_feels_is_still_charged_for(engine: PricingEngine) -> None:
    """Marginal pricing says zero, and zero is not a price.

    The book is concentrated in Türkiye, so its worst half per cent is Turkish
    earthquakes and a New York policy is never in it. The marginal reading of
    that is exactly zero, and it is correct: this policy adds nothing to the
    tail of this book. What followed from it was not. The policy was sold for
    its expected loss plus expenses -- 13.79 against an expected loss of 12.77
    on the live book, ninety three per cent of the premium expected to be paid
    straight back out -- which is a bet with an eight per cent margin rather
    than an insurance price.

    A policy is charged for at least a twentieth of what it would need standing
    alone, however well it sits against today's book, because today's book is
    not tomorrow's: at nothing, the same risk can be written again and again,
    each time against a book that does not hold the others.
    """
    book = _istanbul_book(engine)
    quote = engine.quote(peril_key="earthquake", subject=_new_york(),
                         limit=100_000.0, term_days=365.0, book=book)

    assert quote.diversification == "absorbed", quote.diversification
    assert quote.diversification_ratio == 0.0
    assert quote.risk_load > 0.0, "a risk the book absorbs is written for nothing"
    assert quote.marginal_capital == pytest.approx(
        0.05 * quote.standalone_capital, rel=1e-6)
    # And the premium keeps something back for the risk rather than handing it
    # all over as expected loss.
    assert quote.expected_loss / quote.premium < 0.6


def test_the_same_cover_costs_the_same_split_or_whole(engine: PricingEngine) -> None:
    """Ten policies of a hundred thousand, or one of a million.

    On the live book a million of New York cover in one policy measured 8,845
    of capital and cost 1,198.55, while the same million split into ten
    policies measured zero and cost 137.90: the same risk, split ten ways, for
    a ninth of the price. Anyone wanting a million simply bought ten.

    Standalone capital is proportional to the limit, so a floor written against
    it cannot be arbitraged by splitting.
    """
    book = _istanbul_book(engine)
    one = engine.quote(peril_key="earthquake", subject=_new_york(),
                       limit=1_000_000.0, term_days=365.0, book=book)
    ten = engine.quote(peril_key="earthquake", subject=_new_york(),
                       limit=100_000.0, term_days=365.0, book=book)
    assert one.premium == pytest.approx(ten.premium * 10, rel=1e-6), (one.premium, ten.premium)


def test_a_rare_risk_knows_its_own_capital_without_drawing_for_it() -> None:
    """The floor rests on standalone capital, so that has to be a real number.

    New York pays about once in three thousand seven hundred years. In twenty
    thousand trials that is five events; in four thousand it is one, and in a
    third of such runs it is none at all -- a standalone requirement of exactly
    zero, and a floor of five per cent of nothing.

    It does not have to be drawn for. Below the solvency tail the answer is
    exact: if a policy pays less often than one time in two hundred, every
    outcome in which it pays is inside the worst half per cent, so the tail
    average is the expected loss divided by that half per cent and the capital
    is 199 times the expected loss. The same number however many trials are
    run, which is what this checks.
    """
    book_seed = 99
    quotes = []
    for trials in (2_000, 8_000):
        engine = PricingEngine(trials=trials, seed=book_seed)
        quotes.append(engine.quote(peril_key="earthquake", subject=_new_york(),
                                   limit=100_000.0, term_days=365.0,
                                   book=_istanbul_book(engine)))
    first, second = quotes
    assert first.trigger_probability <= 1 - SOLVENCY_LEVEL
    for quote in quotes:
        assert quote.standalone_capital == pytest.approx(
            quote.expected_loss * (1 / (1 - SOLVENCY_LEVEL) - 1), rel=1e-9)
    # Same at both trial counts, where a drawn figure would not be.
    assert first.standalone_capital == pytest.approx(second.standalone_capital, rel=0.02)
    assert first.risk_load > 0 and second.risk_load > 0


def test_the_floor_leaves_a_real_marginal_charge_alone(engine: PricingEngine) -> None:
    """It binds where the reading broke, and nowhere else.

    A policy in the book's own peak zone adds capital the tail can see, many
    times the floor, so the floor is not what sets its price and this change
    does not touch it.
    """
    book = _istanbul_book(engine)
    subject = EARTHQUAKE.validate_subject(
        {"latitude": 40.99, "longitude": 29.03, "radius_km": 50, "index": "shaking"})
    quote = engine.quote(peril_key="earthquake", subject=subject,
                         limit=100_000.0, term_days=365.0, book=book)
    assert quote.marginal_capital > 0.05 * quote.standalone_capital * 5
    assert quote.diversification_ratio > 0.35
