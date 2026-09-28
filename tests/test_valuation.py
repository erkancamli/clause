"""Cover is capped by what the thing is worth, and what it is worth comes from
its size. A 100 m² garden cannot buy a 100 hectare farm's cover.

The rest of this file is about where the per unit figures come from, because
every country publishes four numbers for the same thing and three of them
would under-insure a family badly. The tests name each trap: a permit fee base
used as a rebuild cost, a level read at another year's exchange rate, a
national rate applied to a region that costs twice as much, and a crop priced
by a number nobody published.
"""

from __future__ import annotations

import datetime as dt

import pytest

from clause.protocol.valuation import (
    ESCALATION, FX, NO_REGIONS, REBUILD, REFUSED, REGIONS, REVENUE, YEAR_FX,
    Figure, ValuationError, carried_forward, rate_for, schedule, value_of,
)
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_api_security import buy_body, buy_terms, client, buyer  # noqa: F401


def test_a_bigger_field_carries_more_cover() -> None:
    small = value_of({"kind": "field", "crop": "wheat", "area_ha": 0.01}, country="TR")
    large = value_of({"kind": "field", "crop": "wheat", "area_ha": 10}, country="TR")
    assert large.value == pytest.approx(small.value * 1000)
    assert small.value < 20


def test_a_home_is_valued_by_floor_area_and_country() -> None:
    istanbul = value_of({"kind": "home", "building": "flat", "area_m2": 100, "built": 2005}, country="TR")
    tokyo = value_of({"kind": "home", "building": "flat", "area_m2": 100, "built": 2005}, country="JP")
    assert tokyo.value > istanbul.value > 0
    assert "100 m²" in istanbul.basis


@pytest.mark.parametrize("size", [
    {"kind": "home", "building": "castle", "area_m2": 100, "built": 2005},
    {"kind": "home", "building": "flat", "area_m2": 5, "built": 2005},
    {"kind": "field", "crop": "wheat", "area_ha": 0},
    {"kind": "field", "crop": "gold", "area_ha": 1},
    {"kind": "boat"},
])
def test_a_description_that_gives_no_value_is_refused(size) -> None:
    with pytest.raises(ValuationError):
        value_of(size, country="TR")


def test_no_schedule_means_no_home_cover() -> None:
    with pytest.raises(ValuationError, match="no rebuild cost schedule"):
        value_of({"kind": "home", "building": "flat", "area_m2": 100, "built": 2005}, country="FR")


# ---------------------------------------------------------------- the traps

def test_a_permit_fee_base_can_never_set_a_sum_insured() -> None:
    """The most official looking number in every country, and the most wrong.

    Italy's costo di costruzione is the base for a building permit
    contribution and is about a quarter of what rebuilding costs; Chile's
    MINVU table is five to eight times low; the Philippine figure is what an
    applicant declares to a building officer. All three are real government
    publications, and none of them may price a policy.
    """
    for country, figure in REFUSED.items():
        if figure.kind != "permit":
            continue
        with pytest.raises(ValuationError, match="cannot set a sum insured"):
            carried_forward(figure, country, dt.datetime.now(dt.timezone.utc).timestamp())


def test_no_figure_in_use_is_a_permit_figure() -> None:
    """The refused ones are written down so nobody adds them back by mistake."""
    for country, table in REBUILD.items():
        for building, figure in table.items():
            assert figure.kind != "permit", f"{country} {building} is a permit base"


def test_a_figure_without_a_kind_a_date_and_a_source_cannot_be_made() -> None:
    with pytest.raises(ValueError):
        Figure(1.0, "EUR", "2026-01-01", "somebody", "guess")
    for country, table in REBUILD.items():
        for building, figure in table.items():
            dt.date.fromisoformat(figure.as_at)
            assert len(figure.source) > 20, f"{country} {building} has no real source"
            assert figure.currency in FX


def test_a_level_is_carried_forward_by_an_index_and_never_further_than_three_years() -> None:
    """A statistics office publishes how fast costs rise, not what they are.

    Türkiye's schedule is a January figure and building costs there rise by
    more than a quarter a year, so by September it is a fifth short. The index
    is the only thing that can close that, and it is the only thing it may do.
    """
    now = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp()
    figure = REBUILD["TR"]["flat"]
    grown, said = carried_forward(figure, "TR", now)
    assert "carried forward" in said and ESCALATION["TR"].source in said
    assert grown > figure.amount / FX["TRY"].per_unit
    # Ten years on, the table has not compounded into fiction.
    far = dt.datetime(2036, 10, 1, tzinfo=dt.timezone.utc).timestamp()
    capped, _ = carried_forward(figure, "TR", far)
    assert capped == pytest.approx(
        figure.amount / FX["TRY"].per_unit * (1 + ESCALATION["TR"].per_year) ** 3)


def test_a_season_is_converted_at_its_own_years_rate() -> None:
    """A Turkish hectare of maize earned 105,353 lira in the 2025 season. At
    that year's rate that is 2,662 of the unit of account; at today's it would
    read 2,157, and the farmer would be a fifth short for no reason but
    arithmetic done on the wrong day."""
    maize = REVENUE["TR"]["maize"]
    assert maize.year == 2025
    assert maize.per_unit == YEAR_FX[(2025, "TRY")]
    assert maize.per_unit < FX["TRY"].per_unit
    field = value_of({"kind": "field", "crop": "maize", "area_ha": 1}, country="TR")
    assert field.value == pytest.approx(2662.5, abs=1.0)


def test_wheat_is_priced_from_the_season_being_covered_not_from_two_years_ago() -> None:
    """Turkish farm prices rise by a third a year, so a 2024 average would
    under-cover the 2026 harvest it is meant to replace."""
    wheat = REVENUE["TR"]["wheat"]
    assert wheat.year == 2026 and "TMO" in wheat.source


def test_a_crop_nobody_publishes_a_price_for_cannot_be_covered() -> None:
    """Italy grows barley and files no barley price to anyone: Eurostat has
    none and FAOSTAT's Italian series died in 1999. So Italian barley cannot
    be covered, and the refusal says what can be instead of leaving the buyer
    to guess."""
    assert "barley" not in REVENUE["IT"]
    with pytest.raises(ValuationError) as raised:
        value_of({"kind": "field", "crop": "barley", "area_ha": 10}, country="IT")
    assert "wheat" in str(raised.value) and "maize" in str(raised.value)


def test_turkish_cotton_is_priced_from_the_statistics_office_and_not_the_trade_press() -> None:
    """The largest hole in this table for a while. Cotton is 467,000 hectares
    at 4,804 kg/ha, so a lira on the price is 4,804 lira a hectare of cover,
    and the only numbers going round were trade press. TUIK publishes the
    price farmers were actually paid, for the unginned crop by name."""
    cotton = REVENUE["TR"]["cotton"]
    assert cotton.year == 2025 and "TUIK" in cotton.source
    assert "kutlu" in cotton.note and "cottonseed" in cotton.note
    assert cotton.revenue == pytest.approx(4.804 * 25_966.34, rel=1e-3)


def test_a_crop_a_country_does_not_grow_is_simply_absent() -> None:
    for grown in ("wheat", "barley", "sunflower", "chickpea", "lentil", "sugar_beet"):
        assert grown not in REVENUE["ID"] and grown not in REVENUE["PH"]
    assert "maize" in REVENUE["ID"]


# ------------------------------------------------------------- where it is

def test_only_a_published_region_moves_the_rate() -> None:
    """Three countries publish what building costs in each of their regions.
    Tokyo is a quarter dearer than the Japanese average for a flat, and
    Indonesia's own index puts the Papuan highlands at twice Jakarta."""
    flat, _ = rate_for("JP", "flat")
    tokyo, how = rate_for("JP", "flat", region="Tokyo")
    assert tokyo == pytest.approx(flat * 1.25)
    assert how["region"]["name"] == "Tokyo"
    highlands, _ = rate_for("ID", "house", region="Papua Pegunungan")
    jakarta, _ = rate_for("ID", "house", region="Jakarta")
    assert highlands == pytest.approx(jakarta * 2.170)


def test_a_region_nobody_published_leaves_the_rate_alone() -> None:
    plain, _ = rate_for("TR", "flat")
    rize, how = rate_for("TR", "flat", region="Rize")
    assert rize == pytest.approx(plain)
    assert how["region"]["factor"] == 1.0
    assert "no provincial figure is published" in how["region"]["basis"]


def test_every_country_either_has_regions_or_says_why_not() -> None:
    """Silence would read as an oversight. Each country has been asked."""
    for country in REBUILD:
        assert country in REGIONS or country in NO_REGIONS, country


def test_a_building_type_nobody_publishes_says_what_stood_in_for_it() -> None:
    """Only Türkiye publishes a commercial class, so a shop elsewhere takes
    the rate for the flats above it, and the quote says so."""
    _, how = rate_for("IT", "shop")
    assert "no commercial schedule is published" in how["stands_in"]
    # And where the stand-in itself has no figure, the chain is followed and
    # every step of it is said: no Italian source publishes a rate for a plain
    # detached house either, so that one takes the condominium rate.
    _, house = rate_for("IT", "house")
    assert "condominium rate is used" in house["stands_in"]
    turkish, how = rate_for("TR", "shop")
    assert "stands_in" not in how and turkish > rate_for("TR", "flat")[0]


# --------------------------------------------------------------- the whole

def test_the_protocol_refuses_cover_above_what_the_size_supports(client, buyer) -> None:
    """The buyer claims a large value but describes a small flat: the size wins."""
    device, address = buyer
    size = {"kind": "home", "building": "flat", "area_m2": 40.0, "built": 2005}
    ceiling = value_of(size, country="TR").value
    terms = buy_terms(limit=50_000.0, value_at_risk=90_000.0, size=size)
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms}).json()
    body = buy_body(address, challenge["nonce"], device.sign(challenge["message"]), client=client)
    body["interest"]["size"] = size
    reply = client.post("/api/policies", json=body)
    assert reply.status_code == 451
    # To the penny, because the refusal compares two arithmetics and used to
    # print both of them rounded to the same whole number.
    assert f"{ceiling:,.2f}" in reply.text


def test_earthquake_cover_needs_a_description(client, buyer) -> None:
    device, address = buyer
    terms = buy_terms()
    terms.pop("size")
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms}).json()
    body = buy_body(address, challenge["nonce"], device.sign(challenge["message"]), client=client)
    body["interest"].pop("size")
    reply = client.post("/api/policies", json=body)
    assert reply.status_code == 422
    assert "floor area" in reply.text


def test_the_schedule_is_published(client) -> None:
    table = client.get("/api/valuation").json()
    assert table["rebuild_per_m2"]["TR"]["flat"] > 0 and "wheat" in table["crops"]
    assert table["revenue_per_ha"]["TR"]["wheat"] > 0


def test_the_schedule_carries_what_is_behind_every_figure() -> None:
    """A buyer who asks why the ceiling is what it is gets an answer, and the
    page has the material to give it without asking us."""
    published = schedule()
    behind = published["rebuild_basis"]["TR"]["flat"]
    assert behind["figure"]["kind"] == "rebuild"
    assert "Resmi Gazete" in behind["figure"]["source"]
    assert behind["figure"]["as_at"] == "2026-01-01"
    assert published["fx"]["TRY"]["source"].startswith("TCMB")
    # And the figures that must never price a policy travel with it, named.
    assert published["refused"]["IT"]["kind"] == "permit"


def test_a_budget_ceiling_is_refused_the_same_way_a_permit_base_is() -> None:
    """Indonesia's is the rare instrument that disqualifies itself in its own
    text: article 2(4) of the Jakarta decree says the standard may not be used
    as the basis for a cost estimate. It is a ceiling on what a city budget may
    appropriate, which is a different thing from a permit fee base and is
    equally not a measure of what building costs."""
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    figure = REFUSED["ID"]
    assert figure.kind == "budget" and figure.amount is None
    with pytest.raises(ValuationError, match="cannot set a sum insured"):
        carried_forward(figure, "ID", now)


def test_a_figure_a_scheme_sets_by_decision_is_not_carried_forward() -> None:
    """An index carries a cost forward because a cost drifts. Greece's 900 a
    square metre does not drift: a minister set it for the year and will set
    the next one. Escalating it would invent a number nobody published."""
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    figure = REBUILD["GR"]["flat"]
    assert figure.kind == "insurance"
    amount, said = carried_forward(figure, "GR", now)
    assert amount == pytest.approx(figure.amount / FX["EUR"].per_unit)
    assert "reset by its author" in said
    # Türkiye's ministry schedule is a cost, so it is carried forward.
    grown, moved = carried_forward(REBUILD["TR"]["flat"], "TR", now)
    assert "carried forward" in moved and grown > REBUILD["TR"]["flat"].amount / FX["TRY"].per_unit


def test_every_country_with_a_trap_has_it_written_down_by_name() -> None:
    """The traps are the point of this module, so each is recorded where a
    later reader will find it before re-adding it as a discovery."""
    for country, figure in REFUSED.items():
        assert figure.kind in ("permit", "budget", "insurance"), country
        assert len(figure.note) > 60, f"{country} does not say why"


def test_a_refused_figure_says_so_in_a_sentence() -> None:
    """These names are read back inside two sentences, so they have to be noun
    phrases. Written as questions, a buyer was shown "what the trip cost must
    be between 50 and 20000", which is not English.
    """
    from clause.protocol.valuation import ValuationError, value_of

    for size, head in (({"kind": "trip"}, "give "),
                       ({"kind": "vehicle", "model_year": 2020}, "give ")):
        try:
            value_of(size)
        except ValuationError as error:
            said = str(error)
            assert said.startswith(head), said
            assert not said.startswith(head + "what "), (
                f"reads as a question rather than a thing: {said!r}"
            )
        else:
            raise AssertionError(f"{size} gave a value with nothing to value")

    for size in ({"kind": "trip", "value": 10 ** 6},
                 {"kind": "vehicle", "value": 1, "model_year": 2020}):
        try:
            value_of(size)
        except ValuationError as error:
            said = str(error)
            assert " must be between " in said, said
            assert not said.startswith("what "), (
                f"reads as a question rather than a thing: {said!r}"
            )
        else:
            raise AssertionError(f"{size} was accepted and should not be")
