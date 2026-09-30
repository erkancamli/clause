"""The registry: who may issue a policy, and the ways of not being allowed to.

The registry is the reason this protocol can operate in a country nobody wrote
code for, and the reason it refuses in one where nobody has put up a licence.
Both halves matter, and a bug in either is a regulatory event rather than a
defect, so the tests here are about the rule rather than the plumbing.
"""

from __future__ import annotations

import re
import time

import pytest

from clause.protocol.carrier import (
    CARRIER_CONCENTRATION_LIMIT,
    Appetite,
    Carrier,
    CarrierError,
    Licence,
    Reach,
    Registry,
    Role,
    Settlement,
    Status,
    specimen_registry,
)

YEAR = 365 * 86400
QUAKE = "earthquake"
NOW = time.time()


def licence(**overrides) -> Licence:
    base = dict(
        country="TR", authority="SEDDK", reference="SEDDK/2026/1",
        perils=frozenset({QUAKE}), reach=Reach.RETAIL,
        settlement=frozenset({Settlement.FIAT}), expires_at=NOW + YEAR,
    )
    base.update(overrides)
    return Licence(**base)


def company(**overrides) -> Carrier:
    base = dict(
        carrier_id="test-co", name="Test Sigorta", role=Role.CARRIER,
        domicile="TR", licences=(licence(),),
        appetite=Appetite(max_limit=500_000, max_term_days=400,
                          perils=frozenset({QUAKE})),
        capacity=5_000_000,
    )
    base.update(overrides)
    return Carrier(**base)


def active(registry: Registry, carrier: Carrier) -> Carrier:
    registry.register(carrier)
    return registry.activate(carrier.carrier_id)


def place(registry: Registry, **overrides):
    base = dict(country="TR", peril=QUAKE, limit=100_000.0, term_days=365.0,
                asset=Settlement.FIAT, reach=Reach.RETAIL)
    base.update(overrides)
    return registry.place(**base)


# ---------------------------------------------------------------------------
# A licence has to be a licence
# ---------------------------------------------------------------------------


def test_a_licence_names_a_country_an_authority_and_a_number() -> None:
    with pytest.raises(CarrierError):
        licence(country="Türkiye")
    with pytest.raises(CarrierError):
        licence(authority="  ")
    with pytest.raises(CarrierError):
        licence(reference="")
    with pytest.raises(CarrierError):
        licence(perils=frozenset())
    with pytest.raises(CarrierError):
        licence(settlement=frozenset())


def test_a_carrier_without_a_licence_cannot_be_registered() -> None:
    with pytest.raises(CarrierError):
        company(licences=())


def test_a_reinsurer_needs_no_licence_where_the_buyer_is() -> None:
    """It never faces the buyer, which is the whole point of the role."""
    assert Carrier(
        carrier_id="re", name="Somewhere Re", role=Role.REINSURER, domicile="BM",
        licences=(), appetite=Appetite(500_000, 400, frozenset({QUAKE})),
        capacity=10_000_000,
    )


def test_a_company_with_no_capacity_cannot_write() -> None:
    with pytest.raises(CarrierError):
        company(capacity=0)


def test_a_fronting_fee_cannot_eat_the_premium() -> None:
    with pytest.raises(CarrierError):
        company(fronting_fee=0.8)


# ---------------------------------------------------------------------------
# Registration is not permission
# ---------------------------------------------------------------------------


def test_a_registered_company_writes_nothing_until_a_person_checks_it() -> None:
    """The one manual step in the protocol, and it is manual on purpose: nothing
    here can read a regulator's register, and a registration that activated
    itself would let anyone claim to be an insurer."""
    registry = Registry()
    registry.register(company())
    assert registry.carriers["test-co"].status is Status.PENDING
    assert not place(registry).placed

    registry.activate("test-co")
    assert place(registry).offers


def test_activating_records_when_the_licence_was_checked() -> None:
    registry = Registry()
    active(registry, company())
    assert all(l.verified_at for l in registry.carriers["test-co"].licences)


def test_the_same_company_cannot_register_twice() -> None:
    registry = Registry()
    registry.register(company())
    with pytest.raises(CarrierError):
        registry.register(company())


def test_suspension_stops_matching_at_once() -> None:
    registry = Registry()
    active(registry, company())
    assert place(registry).offers
    registry.suspend("test-co")
    assert not place(registry).offers


# ---------------------------------------------------------------------------
# What a licence actually permits
# ---------------------------------------------------------------------------


def test_a_licence_is_for_one_country() -> None:
    registry = Registry()
    active(registry, company())
    assert place(registry, country="DE").offers == ()


def test_a_licence_is_for_named_perils() -> None:
    registry = Registry()
    active(registry, company())
    assert place(registry, peril="drought").offers == ()


def test_a_retail_licence_reaches_professionals_and_not_the_other_way() -> None:
    registry = Registry()
    active(registry, company())
    assert place(registry, reach=Reach.PROFESSIONAL).offers

    professional_only = Registry()
    active(professional_only, company(
        carrier_id="pro-co", licences=(licence(reach=Reach.PROFESSIONAL),),
    ))
    assert place(professional_only, reach=Reach.PROFESSIONAL).offers
    assert place(professional_only, reach=Reach.RETAIL).offers == ()


def test_a_licence_is_for_named_settlement_assets() -> None:
    registry = Registry()
    active(registry, company())
    assert place(registry, asset=Settlement.STABLECOIN).offers == ()


def test_an_expired_licence_stops_matching_without_anyone_doing_anything() -> None:
    """The case a table compiled into the source could never handle."""
    registry = Registry()
    # Read the clock here rather than at import, so the window cannot close
    # while the rest of the suite runs.
    now = time.time()
    active(registry, company(licences=(licence(expires_at=now + 3600),)))
    assert place(registry).offers
    assert registry.place(
        country="TR", peril=QUAKE, limit=100_000.0, term_days=365.0,
        asset=Settlement.FIAT, now=now + 7200,
    ).offers == ()


def test_a_licence_inside_its_renewal_window_still_binds_and_says_so() -> None:
    soon = licence(expires_at=NOW + 10 * 86400)
    assert soon.live()
    assert soon.expiring()


# ---------------------------------------------------------------------------
# Appetite is not the same thing as a licence
# ---------------------------------------------------------------------------


def test_a_company_can_want_less_than_it_is_allowed() -> None:
    registry = Registry()
    active(registry, company(appetite=Appetite(
        max_limit=50_000, max_term_days=400, perils=frozenset({QUAKE}),
    )))
    assert place(registry, limit=40_000.0).offers
    assert place(registry, limit=100_000.0).offers == ()
    # And the refusal says so in terms of appetite, not of licensing.
    reasons = " ".join(place(registry, limit=100_000.0).reasons)
    assert "licensed in TR but none will take this risk" in reasons


def test_a_company_can_exclude_a_country_it_is_licensed_for() -> None:
    registry = Registry()
    active(registry, company(appetite=Appetite(
        max_limit=500_000, max_term_days=400, perils=frozenset({QUAKE}),
        excluded_countries=frozenset({"TR"}),
    )))
    assert place(registry).offers == ()


def test_a_term_longer_than_the_appetite_is_refused() -> None:
    registry = Registry()
    active(registry, company(appetite=Appetite(
        max_limit=500_000, max_term_days=180, perils=frozenset({QUAKE}),
    )))
    assert place(registry, term_days=365.0).offers == ()
    assert place(registry, term_days=150.0).offers


# ---------------------------------------------------------------------------
# Capacity, and not putting everything on one company
# ---------------------------------------------------------------------------


def test_a_company_is_held_to_the_capacity_it_stated() -> None:
    registry = Registry()
    active(registry, company(capacity=250_000))
    registry.record("test-co", 200_000)
    assert place(registry, limit=100_000.0).offers == ()
    assert place(registry, limit=50_000.0).offers


def test_releasing_a_settled_policy_gives_the_capacity_back() -> None:
    registry = Registry()
    active(registry, company(capacity=250_000))
    registry.record("test-co", 200_000)
    registry.release("test-co", 200_000)
    assert place(registry, limit=200_000.0).offers


def test_no_single_company_may_carry_the_whole_book() -> None:
    """A protocol whose entire book sits on one carrier fails when it does."""
    registry = Registry()
    active(registry, company(capacity=10_000_000))
    book = 1_000_000.0
    registry.record("test-co", book * CARRIER_CONCENTRATION_LIMIT)
    assert place(registry, limit=100_000.0, book_capacity=book).offers == ()


def test_placement_needs_a_reinsurer_behind_it() -> None:
    """A carrier fronting with nobody behind it is not this structure."""
    registry = Registry()
    active(registry, company())
    attempt = place(registry)
    assert attempt.offers and not attempt.placed
    assert "no reinsurer" in " ".join(attempt.reasons)

    active(registry, Carrier(
        carrier_id="re", name="Somewhere Re", role=Role.REINSURER, domicile="BM",
        licences=(), appetite=Appetite(2_000_000, 400, frozenset({QUAKE})),
        capacity=20_000_000,
    ))
    assert place(registry).placed


def test_the_cheapest_paper_wins_and_ties_break_on_room() -> None:
    """Cheapest, because the fee comes out of the buyer's premium and the pool
    carries the risk either way."""
    registry = specimen_registry()
    active(registry, company(
        carrier_id="cheap-co", name="Cheap Sigorta", fronting_fee=0.01,
    ))
    best = place(registry).best
    assert best is not None and best.carrier.carrier_id == "cheap-co"


# ---------------------------------------------------------------------------
# The map
# ---------------------------------------------------------------------------


def test_the_coverage_map_comes_from_the_registry() -> None:
    registry = specimen_registry()
    before = set(registry.coverage())
    assert "JP" not in before
    active(registry, company(
        carrier_id="jp-co", name="Tokio Parametric K.K.", domicile="JP",
        licences=(licence(country="JP", authority="FSA", reference="KFB-1"),),
    ))
    assert "JP" in registry.coverage()


def test_the_map_only_counts_perils_the_company_actually_wants() -> None:
    """Licensed for three and writing one is a common and honest position."""
    registry = Registry()
    active(registry, company(
        licences=(licence(perils=frozenset({QUAKE, "drought", "flight_delay"})),),
        appetite=Appetite(500_000, 400, frozenset({QUAKE})),
    ))
    assert registry.coverage()["TR"]["perils"] == [QUAKE]


def test_not_one_company_in_the_shipped_registry_claims_to_be_real() -> None:
    """The bug this replaced: invented insurers with licence references in the
    exact format the regulator uses, published on a live public site. A visitor
    could not tell, and one of those references may belong to a real firm.

    So the rule is mechanical rather than a matter of taste. Every shipped
    record is marked, says so in its name, and carries nothing shaped like a
    licence number.
    """
    registry = specimen_registry()
    assert registry.carriers
    for carrier in registry.carriers.values():
        assert carrier.specimen, carrier.carrier_id
        assert "not a real company" in carrier.name.lower(), carrier.name
        for licence in carrier.licences:
            assert "SPECIMEN" in licence.reference, licence.reference
            # Nothing that reads as a regulator's own reference format.
            assert not re.search(r"\d{3,}", licence.reference), licence.reference
            assert not re.search(r"[A-Z]{2,}[/-]\d", licence.reference), licence.reference


def test_a_company_that_registers_is_not_marked_as_a_specimen() -> None:
    """The flag is ours to set on stand ins, never something a registration
    can claim or a real company inherits."""
    registry = Registry()
    registry.register(company())
    assert registry.carriers["test-co"].specimen is False
    assert registry.carriers["test-co"].to_dict()["specimen"] is False


def test_a_decision_about_a_company_is_kept_with_the_company() -> None:
    """Activation is the one step here a person takes, and the one that decides
    whether a company may issue insurance to people. A step of that weight with
    no record of who took it or what they say they checked is a button, not a
    review."""
    registry = Registry()
    registry.register(company())
    assert registry.carriers["test-co"].reviews == ()

    registry.activate("test-co", reviewer="Erkan", note="checked the SEDDK register")
    trail = registry.carriers["test-co"].reviews
    assert len(trail) == 1
    assert trail[0].action == "activated"
    assert trail[0].reviewer == "Erkan"
    assert trail[0].note == "checked the SEDDK register"


def test_suspending_never_erases_the_approval_that_came_before() -> None:
    registry = Registry()
    active(registry, company())
    registry.activate("test-co", reviewer="Erkan", note="checked")
    registry.suspend("test-co", "licence lapsed", reviewer="Erkan")
    actions = [r.action for r in registry.carriers["test-co"].reviews]
    assert actions == ["activated", "activated", "suspended"]


def test_the_trail_is_private_to_the_operator() -> None:
    """Who let a company in belongs in front of whoever is auditing the
    registry, not on the public page a buyer reads."""
    registry = Registry()
    active(registry, company())
    carrier = registry.carriers["test-co"]
    assert "reviews" not in carrier.to_dict()
    assert carrier.to_dict(private=True)["reviews"]


def test_a_reviewer_name_is_recorded_as_self_declared() -> None:
    """One shared operator token cannot prove which person is holding it, and a
    field that implied otherwise would be worse than an honest one."""
    registry = Registry()
    active(registry, company())
    row = registry.carriers["test-co"].to_dict(private=True)["reviews"][0]
    assert row["reviewer"] == "operator"
    assert row["reviewer_self_declared"] is True


def test_stand_in_companies_open_every_inhabited_country_and_say_what_they_are() -> None:
    from clause.protocol.carrier import add_world_specimens, retire_world_specimens
    from clause.protocol.compliance import ComplianceEngine

    registry = Registry()
    added = add_world_specimens(registry)
    assert added > 200
    assert add_world_specimens(registry) == 0, "running it again adds nothing"
    for carrier in registry.carriers.values():
        assert carrier.specimen and "(not a real company)" in carrier.name
        for licence in carrier.licences:
            assert licence.reference.startswith("SPECIMEN")
    open_rows = [r for r in ComplianceEngine(registry).coverage(include_closed=True) if r["open"]]
    countries = {r["country"] for r in open_rows}
    assert {"JP", "TR", "KE", "BR", "US"} <= countries
    assert not countries & {"KP", "IR", "CU", "SY", "AQ"}
    japan = next(r for r in open_rows if r["country"] == "JP")
    assert "earthquake" in japan["perils"]
    # Where crypto payments are banned, a stand in settles in local money only.
    turkey = next(r for r in open_rows if r["country"] == "TR")
    assert set(turkey["settlement"]) == {"fiat"}

    assert retire_world_specimens(registry) > 200
    assert not [r for r in ComplianceEngine(registry).coverage(include_closed=True)
                if r["open"] and r["country"] == "KE"]


def test_a_stand_in_saved_by_an_earlier_build_learns_the_new_peril_and_a_real_company_does_not() -> None:
    """A book written before storm cover existed carries the stand ins with
    four perils; restored under this build they would refuse the fifth with
    "registered here, but not for this risk". Only specimens are brought up
    to date; a real company's licence is what it registered."""
    import dataclasses

    from clause.protocol.carrier import EVERY_PERIL, refresh_specimens, specimen_registry

    registry = specimen_registry()
    old = frozenset(EVERY_PERIL - {"storm"})
    for carrier in registry.carriers.values():
        carrier.licences = tuple(dataclasses.replace(l, perils=l.perils & old) for l in carrier.licences)
        carrier.appetite = dataclasses.replace(carrier.appetite, perils=carrier.appetite.perils & old)
    real = Carrier(
        carrier_id="real-tr", name="A Real Company", role=Role.CARRIER, domicile="TR",
        contact="x@example.com",
        licences=(Licence(country="TR", authority="SEDDK", reference="TR-1", perils=frozenset({"earthquake"}),
                          reach=Reach.RETAIL, settlement=frozenset({Settlement.FIAT}), expires_at=time.time() + YEAR),),
        appetite=Appetite(max_limit=100_000, max_term_days=400, perils=frozenset({"earthquake"})),
        capacity=1_000_000,
    )
    registry.register(real)
    assert not any("storm" in l.perils for c in registry.carriers.values() for l in c.licences)
    refreshed = refresh_specimens(registry)
    assert refreshed > 0
    assert refresh_specimens(registry) == 0, "running it again changes nothing"
    # Each stand in is back to exactly this build's definition: the ones
    # licensed for every peril now carry storm, the one licensed for
    # earthquake and drought alone is still that.
    fresh = specimen_registry().carriers
    for carrier_id, carrier in registry.carriers.items():
        if carrier.specimen:
            assert [l.perils for l in carrier.licences] == [l.perils for l in fresh[carrier_id].licences]
    assert any("storm" in l.perils for c in registry.carriers.values() if c.specimen and c.domicile == "TR"
               for l in c.licences)
    assert registry.carriers["real-tr"].licences[0].perils == frozenset({"earthquake"})


# ---------------------------------------------------------------------------
# Two carriers per peril, not two per country
# ---------------------------------------------------------------------------


def test_every_peril_offered_in_a_country_has_a_second_carrier() -> None:
    """The failure this exists to stop, which happened.

    Türkiye had two specimen carriers, which reads like enough. The second was
    licensed for earthquake and drought only, so when the first crossed the
    concentration limit against the pool — which the limit guarantees it
    eventually will — storm, vehicle flood and flight delay had nobody left
    that could write them, and three of the five covers on the site simply
    could not be bought. Nothing failed loudly: the offers came back empty and
    the buyer was told nobody was licensed.

    So the rule is not two carriers in a country. It is two for each peril the
    country is open for, because a carrier that cannot write a peril is not a
    second carrier for it.
    """
    from collections import defaultdict

    from clause.protocol.carrier import Reach, Role, Settlement, Status, specimen_registry

    registry = specimen_registry()
    writers: dict[tuple[str, str], set[str]] = defaultdict(set)
    for carrier in registry.carriers.values():
        if carrier.role is not Role.CARRIER or carrier.status is not Status.ACTIVE:
            continue
        for licence in carrier.licences:
            for peril in licence.perils:
                if carrier.appetite.perils and peril not in carrier.appetite.perils:
                    continue
                writers[(licence.country, peril)].add(carrier.carrier_id)

    thin = {key: sorted(who) for key, who in writers.items() if len(who) < 2}
    assert not thin, (
        "one carrier is the whole market for these, so the country closes for "
        f"them the day it fills up: {thin}"
    )


def test_a_refusal_says_whether_anyone_was_licensed_at_all() -> None:
    """"Nobody is licensed here" and "somebody is, and is full" are different
    answers, and the buyer is owed the true one. They were not told apart,
    because placement is tried in stablecoin first and a country whose carriers
    settle in the local currency only always failed that attempt with "nobody
    is licensed", which was then the answer kept."""
    from clause.protocol.carrier import Reach, Settlement, specimen_registry

    registry = specimen_registry()
    fiat = registry.place(country="TR", peril="storm", limit=20_000, term_days=365,
                          asset=Settlement.FIAT, reach=Reach.RETAIL)
    assert fiat.licensed and fiat.offers

    coin = registry.place(country="TR", peril="storm", limit=20_000, term_days=365,
                          asset=Settlement.STABLECOIN, reach=Reach.RETAIL)
    assert not coin.licensed and not coin.offers


def test_a_saved_registry_gains_a_stand_in_this_build_added() -> None:
    """The half that would have kept a running deployment broken.

    refresh_specimens brought a saved stand in's licences up to date but
    skipped one that was not in the file at all, so the day Türkiye gained a
    third carrier the fix reached the tests and not the deployment: it restores
    its registry from disk, found two Turkish carriers, and storm, vehicle
    flood and flight delay stayed unbuyable there.
    """
    from clause.protocol.carrier import Registry, refresh_specimens, specimen_registry

    saved = Registry()
    for carrier in specimen_registry().carriers.values():
        if carrier.carrier_id == "specimen-tr-three":
            continue
        saved.register(carrier)
        saved.activate(carrier.carrier_id)
    assert "specimen-tr-three" not in saved.carriers

    assert refresh_specimens(saved) >= 1
    added = saved.carriers["specimen-tr-three"]
    assert added.status is Status.ACTIVE
    assert "storm" in {p for lic in added.licences for p in lic.perils}


def test_a_buyer_in_turkiye_is_offered_a_choice_and_not_a_company() -> None:
    """Three times now the live site has shown one insurer and no explanation.

    The first time the country's only licensed carrier had breached the
    concentration limit. The second time two carriers between them had divided
    the perils, so three of the five covers had a single writer. Each time the
    list shrank silently, which is why it took a person noticing to find it.
    This asks the question directly, for every peril, at a size an ordinary
    buyer would ask for.
    """
    from clause.protocol.carrier import EVERY_PERIL, specimen_registry, Reach, Settlement

    registry = specimen_registry()
    for peril in sorted(EVERY_PERIL):
        placement = registry.place(country="TR", peril=peril, limit=20_000.0,
                                   term_days=180.0, asset=Settlement.FIAT,
                                   reach=Reach.RETAIL)
        names = {o.carrier.carrier_id for o in placement.offers}
        assert len(names) >= 5, f"{peril} in TR is offered by {len(names)}: {sorted(names)}"
        # And a choice means the prices differ; five companies quoting the same
        # fee is a list, not a choice.
        fees = {o.fronting_fee for o in placement.offers}
        assert len(fees) >= 4, f"{peril} in TR has {len(fees)} distinct fees"


def test_a_company_that_cannot_offer_says_so_instead_of_vanishing() -> None:
    """A list that has quietly gone from five names to one reads exactly like a
    country with one insurer in it. The buyer cannot tell those apart, and
    neither could we: every time this happened it had to be diagnosed from the
    outside. Now the placement carries the ones it dropped, and why."""
    from clause.protocol.carrier import specimen_registry, Reach, Settlement

    registry = specimen_registry()
    # Larger than the smaller stand ins will write, so some must drop out.
    placement = registry.place(country="TR", peril="earthquake", limit=400_000.0,
                               term_days=365.0, asset=Settlement.FIAT, reach=Reach.RETAIL)
    assert placement.offers, "somebody should still write this"
    assert placement.held_back, "the ones that could not should be named"
    for name, why in placement.held_back:
        assert name and why
        assert "its most is" in why or "full" in why or "of the book" in why


def test_one_company_offering_usdc_does_not_hide_nine_offering_a_bank_transfer() -> None:
    """The fourth time the live site showed a single insurer, and the cause was
    neither licensing nor capacity.

    Placement tries stablecoin first and stopped at the first asset that placed.
    Every Turkish stand in settles in lira, so locally the first attempt found
    nobody and the second found six. On the deployment one company had declared
    it could settle in USDC, the first attempt succeeded, and the nine that pay
    into a bank vanished behind it. How a company pays is one of the things the
    buyer is choosing between, not a filter applied before they get to choose.
    """
    import time
    from clause.protocol.carrier import (Appetite, BOTH_ASSETS, Carrier, EVERY_PERIL,
                                         Licence, Reach, Role, specimen_registry)
    from clause.protocol.compliance import ComplianceEngine, Interest

    now = time.time()
    registry = specimen_registry(now=now)
    # Supervised in Germany, permitted to sell into Türkiye. A company
    # supervised in Türkiye could not offer this and is refused if it claims
    # to; see the test below.
    registry.register(Carrier(
        carrier_id="both-ways", name="Settles either way", role=Role.CARRIER,
        domicile="DE", contact="a company", licences=(Licence(
            country="TR", authority="SEDDK", reference="X-1", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=BOTH_ASSETS, expires_at=now + 2 * 365 * 86400),),
        appetite=Appetite(max_limit=500_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=9_000_000, fronting_fee=0.025))
    registry.activate("both-ways", now=now)

    ruling = ComplianceEngine(registry).evaluate(
        interest=Interest(what="a flat", country="TR", inside_trigger_area=True,
                          value_at_risk=50_000.0, holder_resident_in="DE"),
        limit=50_000.0, peril="earthquake", term_days=365.0)
    assert ruling.allowed
    offered = {o.carrier.carrier_id for o in ruling.placement.offers}
    assert "both-ways" in offered
    assert len(offered) >= 6, f"the fiat companies were hidden again: {sorted(offered)}"


def test_where_the_law_says_local_currency_the_protocol_obeys_its_own_note() -> None:
    """Türkiye's note tells the buyer that premiums and claims settle in lira,
    because the 2021 central bank regulation prohibits paying in crypto assets.

    That was a sentence on a screen and nothing else, and when it was first
    enforced it was enforced against the wrong thing: the country the risk sat
    in. The prohibition binds institutions and protects residents, so it is
    read twice, against two different countries, and both have to allow it.
    """
    import time

    import pytest

    from clause.protocol.carrier import (Appetite, BOTH_ASSETS, Carrier, CarrierError,
                                         EVERY_PERIL, Licence, PAYMENT_BAN_COUNTRIES,
                                         Reach, Role, Settlement, specimen_registry)
    from clause.protocol.compliance import ComplianceEngine, Interest

    assert "TR" in PAYMENT_BAN_COUNTRIES
    now = time.time()

    # Condition one, the company. Supervised where paying in crypto assets is
    # prohibited, so the claim is refused at the door, wherever it writes.
    would_rather = Carrier(
        carrier_id="usdc-please", name="Would rather pay in USDC",
        role=Role.CARRIER, domicile="TR", contact="a company", licences=(Licence(
            country="DE", authority="BaFin", reference="X-2", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=BOTH_ASSETS,
            expires_at=now + 2 * 365 * 86400),),
        appetite=Appetite(max_limit=500_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=9_000_000, fronting_fee=0.01)
    with pytest.raises(CarrierError, match="supervised in TR"):
        specimen_registry(now=now).register(would_rather)

    # Condition two, the buyer. A company that may pay either way, and a
    # resident of a country that prohibits being paid that way.
    registry = specimen_registry(now=now)
    registry.register(Carrier(
        carrier_id="foreign-paper", name="Supervised elsewhere", role=Role.CARRIER,
        domicile="DE", contact="a company", licences=(Licence(
            country="TR", authority="SEDDK", reference="X-3", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=BOTH_ASSETS,
            expires_at=now + 2 * 365 * 86400),),
        appetite=Appetite(max_limit=500_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=9_000_000, fronting_fee=0.01))
    registry.activate("foreign-paper", now=now)
    engine = ComplianceEngine(registry)

    resident = engine.evaluate(
        interest=Interest(what="a flat", country="TR", inside_trigger_area=True,
                          value_at_risk=50_000.0, holder_resident_in="TR"),
        limit=50_000.0, peril="earthquake", term_days=365.0)
    assert resident.allowed
    assert resident.settlement is Settlement.FIAT
    assert any("where you live" in line for line in resident.disclosure)

    # The same flat, the same company, someone the prohibition was never about.
    visitor = engine.evaluate(
        interest=Interest(what="a flat", country="TR", inside_trigger_area=True,
                          value_at_risk=50_000.0, holder_resident_in="DE"),
        limit=50_000.0, peril="earthquake", term_days=365.0)
    assert visitor.allowed
    assert visitor.settlement is Settlement.STABLECOIN
    # And the policy says why, naming both countries it was read against.
    why = [line for line in visitor.disclosure if "Paid in stablecoin" in line]
    assert why and "DE" in why[0]


def test_a_turkish_resident_is_paid_in_lira_on_a_building_abroad() -> None:
    """The rule follows the person. Reading it off the country of the risk got
    this exactly backwards: it paid a resident of Türkiye in stablecoin as soon
    as the thing they insured was somewhere else, and refused stablecoin to a
    foreigner whose flat happened to be in Istanbul."""
    import time
    from clause.protocol.carrier import (Appetite, BOTH_ASSETS, Carrier, EVERY_PERIL,
                                         Licence, Reach, Role, Settlement,
                                         specimen_registry)
    from clause.protocol.compliance import ComplianceEngine, Interest

    now = time.time()
    registry = specimen_registry(now=now)
    registry.register(Carrier(
        carrier_id="tokyo-paper", name="Tokyo paper", role=Role.CARRIER,
        domicile="JP", contact="a company", licences=(Licence(
            country="JP", authority="the FSA", reference="X-4", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=BOTH_ASSETS,
            expires_at=now + 2 * 365 * 86400),),
        appetite=Appetite(max_limit=500_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=9_000_000, fronting_fee=0.01))
    registry.activate("tokyo-paper", now=now)

    ruling = ComplianceEngine(registry).evaluate(
        interest=Interest(what="a flat in Tokyo", country="JP",
                          inside_trigger_area=True, value_at_risk=50_000.0,
                          holder_resident_in="TR"),
        limit=50_000.0, peril="earthquake", term_days=365.0)
    assert ruling.allowed
    assert ruling.settlement is Settlement.FIAT


def test_every_country_offers_more_than_one_company() -> None:
    """A list of one is not a market. Outside the three countries that had been
    given a second stand in by hand, every buyer in the world was being handed
    a company rather than offered a choice."""
    import collections
    from clause.protocol.carrier import world_specimens

    by_country = collections.Counter(c.domicile for c in world_specimens())
    assert by_country, "there should be stand ins"
    thin = {code: n for code, n in by_country.items() if n < 3}
    assert not thin, f"these countries have fewer than three stand ins: {sorted(thin)}"
    # And they differ on what a buyer can see and weigh.
    brazil = [c for c in world_specimens() if c.domicile == "BR"]
    assert len({c.fronting_fee for c in brazil}) == len(brazil)
    assert len({c.fiat_payout_days for c in brazil}) == len(brazil)


def test_a_rule_about_what_may_be_accepted_is_not_asked_of_the_saved_book() -> None:
    """The failure that took the live service down and kept it down.

    The settlement rule went into ``Carrier.__post_init__``. A dataclass's
    validation runs wherever the class is built, and one of those places is
    reading the saved book back off disk. The live book already held a Turkish
    company that had declared it could settle in USDC -- the very record an
    earlier commit had described -- so the new rule refused to decode it,
    ``restore`` raised, startup failed, and systemd restarted the service
    forty-five times against the same book.

    A rule about what may be accepted must not be asked of what was already
    accepted. The door refuses; what is already inside is repaired.
    """
    import time

    from clause.protocol.carrier import (Appetite, BOTH_ASSETS, Carrier, EVERY_PERIL,
                                         Licence, Reach, Registry, Role, Settlement,
                                         lawful_settlement)

    now = time.time()
    # Decoding it must not raise: this is history, not an application.
    in_the_book = Carrier(
        carrier_id="tr-usdc", name="Already in the live book", role=Role.CARRIER,
        domicile="TR", contact="a company", licences=(Licence(
            country="TR", authority="SEDDK", reference="X", perils=EVERY_PERIL,
            reach=Reach.RETAIL, settlement=BOTH_ASSETS,
            expires_at=now + 2 * 365 * 86400),),
        appetite=Appetite(max_limit=500_000, max_term_days=400, perils=EVERY_PERIL),
        capacity=9_000_000)

    registry = Registry()
    registry.carriers[in_the_book.carrier_id] = in_the_book
    assert lawful_settlement(registry) == 1

    mended = registry.carriers["tr-usdc"]
    assert Settlement.STABLECOIN not in mended.licences[0].settlement
    assert Settlement.FIAT in mended.licences[0].settlement, (
        "the narrowest repair: it keeps the licence and loses the asset")
    # Running it again is not an event.
    assert lawful_settlement(registry) == 0


def test_three_stand_ins_in_a_country_do_not_quote_one_price() -> None:
    """A list of one price with three names is not a market.

    Companies were given their own cost of capital and expense ratio, and the
    eight written out by hand got them while the three hundred generated per
    country did not. So it was fixed everywhere except where most buyers are:
    outside those eight countries three companies quoted the same premium to the
    penny and differed only in the fee on top.
    """
    from clause.protocol.carrier import priced_by, world_specimens

    by_country: dict[str, list] = {}
    for carrier in world_specimens():
        by_country.setdefault(carrier.domicile, []).append(carrier)

    for code, carriers in list(by_country.items())[:8]:
        assert len(carriers) >= 3, code
        priced = [priced_by(c, expected_loss=4000.0, marginal_capital=8000.0,
                            term_days=365.0)["premium"] for c in carriers]
        assert len(set(priced)) == len(priced), f"{code} quotes one premium {priced}"
        # And the cheapest on the total is not the cheapest on the risk, so the
        # buyer has a trade to make rather than an order to read off.
        totals = [p * (1 + c.fronting_fee) for p, c in zip(priced, carriers)]
        assert totals.index(min(totals)) != priced.index(max(priced))
        assert max(totals) / min(totals) > 1.03, f"{code} spread {totals}"


def test_a_saved_stand_in_gets_this_builds_terms() -> None:
    """A book saved before the terms changed kept quoting the old ones."""
    from dataclasses import replace as _replace

    from clause.protocol.carrier import (Registry, refresh_specimens,
                                         specimen_registry, world_specimens)

    registry = specimen_registry()
    fresh = next(c for c in world_specimens() if c.domicile == "US" and c.carrier_id.endswith("-2"))
    stale = _replace(fresh, cost_of_capital=0.2, expense_ratio=0.2, fronting_fee=0.09)
    registry.register(stale)
    registry.activate(stale.carrier_id)
    assert refresh_specimens(registry) >= 1
    now = registry.carriers[stale.carrier_id]
    assert now.cost_of_capital == fresh.cost_of_capital
    assert now.expense_ratio == fresh.expense_ratio
    assert now.fronting_fee == fresh.fronting_fee


def test_no_two_stand_ins_answer_to_the_same_name() -> None:
    """Two companies called "Specimen Carrier B, Türkiye", on the paying screen.

    The eight written out by hand are all in one country and were lettered A,
    B, D, E, F, G. The three generated for every country are lettered nothing,
    B and C. So Türkiye had two Specimen Carrier B, `specimen-tr-two` and
    `specimen-tr-2`, and both of them appear in the list of who will issue the
    policy, at different prices, on the screen where somebody is about to pay.
    One collision in seven hundred and two, in the one country the
    demonstration is actually used in, which is the worst place for the only
    one to be.

    The ids do not move: a saved book holds them and renumbering would rewrite
    the terms an older policy was bought on. Only the spoken name moves, to the
    first letter that country has not used, and Türkiye now reads A to H with
    nothing missing.

    Held for every country rather than for that one, because the next hand
    written company added anywhere would do it again and nothing would say so.
    """
    import collections

    from clause.protocol.carrier import add_world_specimens, specimen_registry

    registry = specimen_registry()
    add_world_specimens(registry)

    spoken = collections.Counter(c.name for c in registry.carriers.values())
    twice = {name: n for name, n in spoken.items() if n > 1}
    assert not twice, f"more than one company answers to these names: {twice}"

    # And the one country with both kinds reads as one series.
    turkish = sorted(c.name for c in registry.carriers.values() if c.domicile == "TR")
    assert len(turkish) == len(set(turkish)), "Türkiye has two companies of one name"
    assert len(turkish) >= 8, f"Türkiye is down to {len(turkish)} companies"
