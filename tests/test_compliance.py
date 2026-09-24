"""The gate: insurable interest, indemnity, and whose paper the policy is on.

These tests changed shape when the module did. They used to assert facts about
a table of countries compiled into the source, which meant they were testing our
documentation. They now assert facts about the registry: that the universal
tests bind everywhere, that a country is open exactly when a licensed company is
registered for it, and that both are checked again before a payout leaves.
"""

from __future__ import annotations

import re
import time

import pytest

from clause.protocol.carrier import (
    Appetite,
    Carrier,
    Licence,
    Reach,
    Registry,
    Role,
    Settlement,
    specimen_registry,
)
from clause.protocol.compliance import (
    Channel,
    ComplianceEngine,
    Interest,
    note_for,
)

YEAR = 365 * 86400
QUAKE = "earthquake"

# Most tests here are about the registry, so they price everything everywhere
# and let the registry alone decide. The pricing gate has its own tests below,
# against the real models.
ANYWHERE = {"earthquake": None, "drought": None, "flight_delay": None}


def Engine(registry=None) -> ComplianceEngine:
    return ComplianceEngine(registry, territories=ANYWHERE)


@pytest.fixture
def engine() -> ComplianceEngine:
    return Engine(specimen_registry())


def interest(**overrides):
    base = dict(
        what="a flat in Kadıköy", country="TR", inside_trigger_area=True,
        value_at_risk=400_000.0, holder_is_professional=False,
    )
    base.update(overrides)
    return Interest(**base)


def rule(engine, *, limit=100_000.0, peril=QUAKE, asset=None, **kw):
    return engine.evaluate(
        interest=interest(**kw), limit=limit, peril=peril, asset=asset,
    )


# ---------------------------------------------------------------------------
# The tests no licence cures
# ---------------------------------------------------------------------------


def test_cover_on_something_outside_the_measured_area_is_refused(engine) -> None:
    """Same contract, no exposure. That is a wager, whatever it is called."""
    ruling = rule(engine, inside_trigger_area=False)
    assert not ruling.allowed
    assert "not inside the area" in " ".join(ruling.reasons)


def test_that_test_is_not_cured_by_being_somewhere_permissive(engine) -> None:
    """It runs before placement, so no country and no carrier can wave it."""
    for country in ("TR", "GB", "IE", "AE", "JP"):
        ruling = rule(engine, country=country, inside_trigger_area=False,
                      holder_is_professional=True)
        assert not ruling.allowed, country
        assert "not inside the area" in " ".join(ruling.reasons), country


def test_cover_above_the_declared_value_at_risk_is_refused(engine) -> None:
    ruling = rule(engine, limit=500_000.0, value_at_risk=200_000.0)
    assert not ruling.allowed
    assert "wager rather than an indemnity" in " ".join(ruling.reasons)
    assert ruling.max_limit == pytest.approx(200_000.0)


def test_cover_at_exactly_the_value_at_risk_is_allowed(engine) -> None:
    """The cap is a cap, not a margin. Equal is fine."""
    assert rule(engine, limit=200_000.0, value_at_risk=200_000.0).allowed


def test_an_interest_must_actually_state_something() -> None:
    with pytest.raises(ValueError):
        interest(what="   ")
    with pytest.raises(ValueError):
        interest(value_at_risk=0.0)
    with pytest.raises(ValueError):
        interest(country="Türkiye")


# ---------------------------------------------------------------------------
# Whose paper it is on
# ---------------------------------------------------------------------------


def test_a_policy_is_issued_by_a_named_company_under_a_named_regulator(engine) -> None:
    """The buyer is told who is actually on the hook, before they buy."""
    ruling = rule(engine)
    assert ruling.allowed
    carrier = ruling.to_dict()["carrier"]
    assert carrier["name"] and carrier["authority"] and carrier["licence"]
    assert carrier["country"] == "TR"


def test_turkey_settles_in_lira_because_the_licence_says_so(engine) -> None:
    """Not because this file says so. The 2021 prohibition is in the note; the
    carrier's licence is what the code reads."""
    ruling = rule(engine, asset=Settlement.STABLECOIN)
    assert ruling.allowed
    assert ruling.settlement is Settlement.FIAT
    assert any("settles in fiat" in d for d in ruling.disclosure)


def test_the_turkish_note_still_names_the_law_it_rests_on(engine) -> None:
    """Shown rather than enforced, but shown, so a reader can check the claim."""
    note = note_for("TR")
    assert note is not None
    for citation in ("5684", "1401", "5363", "2021"):
        assert citation in note.text
    assert any("5684" in d for d in rule(engine).disclosure)


def test_a_country_with_nobody_registered_is_refused_with_a_fact_about_us(engine) -> None:
    """The old answer blamed the country. This one blames the registry, which is
    the true and fixable thing."""
    ruling = rule(engine, country="JP")
    assert not ruling.allowed
    reasons = " ".join(ruling.reasons)
    assert "no licensed carrier is registered" in reasons
    assert "JP" in reasons
    # And it does not name an asset, because both were tried.
    assert "paid in" not in reasons


def test_a_professional_only_licence_refuses_a_consumer(engine) -> None:
    assert not rule(engine, country="AE").allowed


def test_a_professional_there_gets_an_index_contract_not_insurance(engine) -> None:
    ruling = rule(engine, country="AE", holder_is_professional=True)
    assert ruling.allowed
    assert ruling.channel is Channel.INDEX_CONTRACT
    assert any("not insurance" in d for d in ruling.disclosure)


def test_every_allowed_ruling_says_the_issuer_is_a_stand_in(engine) -> None:
    """Said before anything that describes the cover, because everything after
    it is conditional on it. A buyer on the live site must not be able to
    conclude that a licensed insurer stands behind them."""
    for country, pro in (("TR", False), ("IE", False), ("DE", False), ("AE", True)):
        ruling = rule(engine, country=country, holder_is_professional=pro)
        assert ruling.allowed, country
        assert any("stand in, not a company" in d for d in ruling.disclosure), country
        assert ruling.to_dict()["carrier"]["specimen"] is True, country


def test_an_empty_registry_is_the_default(engine) -> None:
    """A deployment starts with nobody registered, so nothing can be written
    anywhere until a real company registers and its licence is checked. The
    stand ins load only in a demonstration."""
    from clause.protocol.compliance import ComplianceEngine

    bare = ComplianceEngine()
    assert bare.registry.carriers == {}
    assert not bare.evaluate(
        interest=interest(), limit=100_000.0, peril=QUAKE
    ).allowed
    assert bare.coverage() == []


def test_a_fronted_policy_says_plainly_that_we_are_not_the_insurer(engine) -> None:
    ruling = rule(engine)
    assert ruling.channel is Channel.FRONTED
    assert any("Clause is not the insurer" in d for d in ruling.disclosure)


def test_every_allowed_policy_names_who_stands_behind_it(engine) -> None:
    ruling = rule(engine)
    assert ruling.to_dict()["reinsurers"], "a carrier alone is not the structure"


# ---------------------------------------------------------------------------
# The registry is the map
# ---------------------------------------------------------------------------


def japanese_carrier(*, now: float | None = None) -> Carrier:
    now = time.time() if now is None else now
    return Carrier(
        carrier_id="tokio-parametric", name="Tokio Parametric K.K.",
        role=Role.CARRIER, domicile="JP",
        licences=(Licence(
            country="JP", authority="Financial Services Agency",
            reference="KFB 2026-4471", perils=frozenset({QUAKE}),
            reach=Reach.RETAIL, settlement=frozenset({Settlement.FIAT}),
            expires_at=now + YEAR,
        ),),
        appetite=Appetite(max_limit=400_000, max_term_days=400,
                          perils=frozenset({QUAKE})),
        capacity=5_000_000,
        fronting_fee=0.05,
    )


def test_a_country_opens_when_a_company_registers_for_it_and_not_before() -> None:
    """The whole argument for a registry, in one test. No code changes here."""
    registry = specimen_registry()
    engine = Engine(registry)
    assert not rule(engine, country="JP").allowed

    registry.register(japanese_carrier())
    assert not rule(engine, country="JP").allowed, "pending is not active"

    registry.activate("tokio-parametric")
    ruling = rule(engine, country="JP")
    assert ruling.allowed
    assert ruling.to_dict()["carrier"]["name"] == "Tokio Parametric K.K."
    assert "JP" in {row["country"] for row in engine.coverage()}


def test_a_country_closes_when_its_carrier_is_suspended() -> None:
    registry = specimen_registry()
    engine = Engine(registry)
    registry.register(japanese_carrier())
    registry.activate("tokio-parametric")
    assert rule(engine, country="JP").allowed

    registry.suspend("tokio-parametric")
    assert not rule(engine, country="JP").allowed
    assert "JP" not in {row["country"] for row in engine.coverage()}


def test_the_coverage_map_is_earned_rather_than_declared(engine) -> None:
    """Every country on it has a named company and a named regulator behind it."""
    rows = engine.coverage()
    assert rows
    for row in rows:
        assert row["carriers"], row
        assert row["authorities"], row
        assert row["perils"], row


def test_a_country_we_wrote_a_note_about_is_not_thereby_open(engine) -> None:
    """Notes are disclosure. A paragraph in our documentation sells nothing."""
    assert note_for("US") is not None
    assert not rule(engine, country="US").allowed


# ---------------------------------------------------------------------------
# Run again before the money leaves
# ---------------------------------------------------------------------------


def test_the_check_runs_again_before_a_payout(engine) -> None:
    ruling = engine.recheck_at_settlement(
        interest=interest(), limit=100_000.0, peril=QUAKE,
    )
    assert ruling.allowed
    assert ruling.checked_at_stage == "settlement"


def test_a_suspended_carrier_hands_its_country_to_the_next_one() -> None:
    """Two carriers in a country is not decoration.

    With one, the country closes the moment that company is suspended or fills
    up, and a buyer's cover depends on a single firm's licence staying valid.
    With two, the second takes the business and the buyer never notices, which
    is the resilience the registry is for.
    """
    registry = specimen_registry()
    engine = Engine(registry)
    first = engine.evaluate(interest=interest(), limit=100_000.0, peril=QUAKE)
    assert first.allowed and first.carrier_id

    # Whoever the cheapest paper turns out to be, the country does not depend
    # on it. Suspend it and somebody else writes the same cover; the test is
    # about that and not about which stand in happens to be cheapest today.
    registry.suspend(first.carrier_id)
    second = engine.evaluate(interest=interest(), limit=100_000.0, peril=QUAKE)
    assert second.allowed and second.carrier_id != first.carrier_id


def test_a_country_closes_when_its_last_carrier_goes() -> None:
    """Rialo re-evaluates compliance on every execution. So does this.

    The policy was lawful when it was written. Between then and the payout the
    carriers' own regulator stopped them. A protocol that checked once would pay
    out on paper that is no longer valid and find out afterwards.
    """
    registry = specimen_registry()
    engine = Engine(registry)
    assert engine.evaluate(
        interest=interest(), limit=100_000.0, peril=QUAKE
    ).allowed

    for carrier_id, carrier in list(registry.carriers.items()):
        if any(lic.country == "TR" for lic in carrier.licences):
            registry.suspend(carrier_id)
    after = engine.recheck_at_settlement(
        interest=interest(), limit=100_000.0, peril=QUAKE,
    )
    assert not after.allowed
    assert "no licensed carrier is registered" in " ".join(after.reasons)


def test_a_licence_that_lapsed_after_binding_stops_the_payout() -> None:
    """The case a table in the source could never catch: time passing."""
    registry = specimen_registry()
    engine = Engine(registry)
    now = time.time()
    assert engine.evaluate(
        interest=interest(), limit=100_000.0, peril=QUAKE, now=now
    ).allowed

    # Past the longest Turkish licence in the opening registry.
    later = now + 3 * 365 * 86400
    after = engine.recheck_at_settlement(
        interest=interest(), limit=100_000.0, peril=QUAKE, now=later,
    )
    assert not after.allowed


# ---------------------------------------------------------------------------
# What the refused person is told
# ---------------------------------------------------------------------------


def test_every_ruling_can_be_shown_to_the_person_it_refused(engine) -> None:
    """A refusal with no reason is indistinguishable from a bug."""
    for kw in (
        {"inside_trigger_area": False},
        {"country": "JP"},
        {"country": "AE"},
        {"limit": 900_000.0, "value_at_risk": 100_000.0},
    ):
        limit = kw.pop("limit", 100_000.0)
        ruling = rule(engine, limit=limit, **kw)
        assert not ruling.allowed
        assert ruling.reasons and all(r.strip() for r in ruling.reasons)
        payload = ruling.to_dict()
        assert payload["reasons"]
        assert payload["stage"] == "purchase"



# ---------------------------------------------------------------------------
# A licence is not a price
# ---------------------------------------------------------------------------


def with_japan(registry: Registry, perils=frozenset({QUAKE, "flight_delay"}),
               country: str = "JP") -> Registry:
    carrier = japanese_carrier()
    carrier.licences = (Licence(
        country=country, authority="Financial Services Agency",
        reference="SPECIMEN", perils=perils, reach=Reach.RETAIL,
        settlement=frozenset({Settlement.FIAT}), expires_at=time.time() + YEAR,
    ),)
    carrier.appetite = Appetite(400_000, 400, perils)
    registry.register(carrier)
    registry.activate(carrier.carrier_id)
    return registry


def test_a_licence_where_no_model_can_price_opens_nothing() -> None:
    """The bug a live test found: a carrier licensed in Japan made the map call
    Japan open, and nobody in Japan could pick anything to insure. Japan now has
    a tested model; Greece's model failed its backtest, so a licence there
    still opens nothing for earthquake."""
    engine = ComplianceEngine(with_japan(specimen_registry(), country="GR"))
    ruling = rule(engine, country="GR")
    assert not ruling.allowed
    assert "no model that can price earthquake cover in GR" in " ".join(ruling.reasons)


def test_a_country_whose_model_passed_can_be_priced() -> None:
    engine = ComplianceEngine(with_japan(specimen_registry()))
    assert engine.priceable(QUAKE, "JP")
    assert not engine.priceable(QUAKE, "GR")


def test_cover_that_follows_a_person_opens_where_they_are_licensed() -> None:
    """A flight is a flight wherever the traveller lives, so a carrier licensed
    in Japan can write delay cover for someone who lives there."""
    engine = ComplianceEngine(with_japan(specimen_registry()))
    ruling = engine.evaluate(
        interest=interest(country="JP", what="one flight"), limit=1_000.0,
        peril="flight_delay", term_days=2.0,
    )
    assert ruling.allowed, ruling.reasons


def test_the_map_shows_only_what_can_be_bought() -> None:
    engine = ComplianceEngine(with_japan(specimen_registry(), country="GR"))
    rows = {row["country"]: row for row in engine.coverage(include_closed=True)}
    greece = rows["GR"]
    assert greece["open"] is True
    assert greece["perils"] == ["flight_delay"]
    assert greece["unpriced"] == [QUAKE]


def test_a_country_with_only_unpriceable_perils_waits_on_a_model() -> None:
    engine = ComplianceEngine(with_japan(specimen_registry(), frozenset({QUAKE}), country="GR"))
    assert "GR" not in {row["country"] for row in engine.coverage()}
    waiting = {row["country"]: row for row in engine.coverage(include_closed=True)}
    assert waiting["GR"]["open"] is False
    assert "a model that can price cover here" in waiting["GR"]["waiting_on"]


def test_no_country_is_open_without_a_reinsurer() -> None:
    """The map and placement ask the same question, so the map cannot call a
    country open that placement would refuse for want of a reinsurer."""
    registry = Registry()
    registry.register(japanese_carrier())
    registry.activate("tokio-parametric")
    engine = Engine(registry)
    assert engine.coverage() == []
    closed = engine.coverage(include_closed=True)
    assert closed and "a reinsurer to stand behind it" in closed[0]["waiting_on"]
    assert not rule(engine, country="JP").allowed


def test_turkey_is_still_open_on_the_real_models() -> None:
    engine = ComplianceEngine(specimen_registry())
    assert rule(engine).allowed
    assert "TR" in {row["country"] for row in engine.coverage()}
