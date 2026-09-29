"""The earthquake models outside Türkiye, as the server uses them.

The build (numpy, the catalogue, the network) is offline and not run here. What
is tested is what ships: the model files, the reader, the rule that only a
model which passed its backtest is sold, and that the page, the price and the
capital model all ask the same model the same question.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.hazard.model import haversine_km, model_for, models, priced_countries
from clause.perils import EARTHQUAKE
from clause.perils.places import search_world
from clause.pricing.simulation import Exposure, WorldDraws, settle

TOKYO = {"latitude": 35.68, "longitude": 139.69, "radius_km": 50.0}
SANTIAGO = {"latitude": -33.45, "longitude": -70.66, "radius_km": 50.0}


def test_every_model_carries_its_backtest() -> None:
    for code, model in models().items():
        v = model.validation
        assert set(v) >= {"passed", "failed", "count", "where", "sites", "record"}, code
        assert v["fitted_until"] < v["tested_from"], code
        assert bool(v["passed"]) == (not v["failed"]), code


def test_a_country_is_sold_on_a_model_that_passed_or_on_its_own_authority() -> None:
    """Two grounds, and nothing else, decide where earthquake cover is written.

    Either our own catalogue model for the country passed its backtest, or the
    country's own authority publishes the hazard and our model only supplies the
    events. The United States is the second case: its catalogue model expected
    27.5 earthquakes of magnitude 5.5 around 296 American cities and 10
    happened, so its level cannot price a policy, and the USGS publishes the
    level itself.
    """
    passed = {code for code, m in models().items() if m.passed}
    assert priced_countries() == frozenset(passed)
    on_authority = EARTHQUAKE.published_territory()
    assert EARTHQUAKE.territory == frozenset({"TR"}) | passed | on_authority
    # A country with neither is not sold, whatever else is true of it.
    for code in ("GR", "IT", "ID", "PH"):
        assert code not in passed
        assert code not in on_authority
        assert code not in EARTHQUAKE.territory, f"{code} has no figure and must not be sold"


def test_a_country_on_its_own_authority_is_sold_only_where_that_reaches() -> None:
    """The country being open does not open every address in it."""
    assert "US" in EARTHQUAKE.territory
    # New York: the USGS publishes a curve at Brooklyn, a few kilometres away.
    near = EARTHQUAKE.validate_subject({"latitude": 40.7128, "longitude": -74.0060,
                                        "radius_km": 50.0, "index": "shaking"})
    assert EARTHQUAKE.risk_country(near) == "US"
    grid = EARTHQUAKE.grid_model(near)
    assert grid is not None and grid.code == "US" and not grid.passed

    # Open country, and nothing published within sixty kilometres of this field.
    with pytest.raises(ValueError, match="no tested earthquake model reaches this address"):
        EARTHQUAKE.validate_subject({"latitude": 45.6770, "longitude": -111.0429,
                                     "radius_km": 50.0})

    # And a country whose model failed and whose authority publishes nothing we
    # hold is not told it is open. Athens: Greece is in neither list.
    assert "GR" not in EARTHQUAKE.territory
    with pytest.raises(ValueError, match="cover is written only where one does"):
        EARTHQUAKE.validate_subject({"latitude": 37.98, "longitude": 23.73, "radius_km": 50.0})


def test_turkey_stays_on_the_fault_model() -> None:
    kadikoy = EARTHQUAKE.validate_subject({"location": "IST-KADIKOY", "radius_km": 50.0})
    assert EARTHQUAKE.grid_model(kadikoy) is None
    assert EARTHQUAKE.risk_country(kadikoy) == "TR"
    assert model_for(40.99, 29.03) is None


@pytest.mark.parametrize("subject, country", [(TOKYO, "JP"), (SANTIAGO, "CL")])
def test_a_point_in_a_passed_country_is_priced_by_its_model(subject, country) -> None:
    validated = EARTHQUAKE.validate_subject(dict(subject))
    grid = EARTHQUAKE.grid_model(validated)
    assert grid is not None and grid.code == country
    assert EARTHQUAKE.risk_country(validated) == country
    p = EARTHQUAKE.exceedance(validated, 365.25)
    assert 0 < p(7.0) < p(6.0) < p(5.5) < 1


@pytest.mark.parametrize("where", [(37.98, 23.73), (41.9, 12.5), (39.1, 26.3), (-6.2, 106.8), (51.5, -0.1)])
def test_a_point_without_a_passed_model_is_refused(where) -> None:
    with pytest.raises(ValueError, match="no tested earthquake model"):
        EARTHQUAKE.validate_subject({"latitude": where[0], "longitude": where[1], "radius_km": 50.0})


def test_a_wider_circle_never_prices_lower() -> None:
    grid = models()["JP"]
    rates = [grid.rate_within(35.68, 139.69, r, 5.5) for r in (25.0, 50.0, 100.0)]
    assert rates[0] < rates[1] < rates[2]


def test_the_curve_is_truncated_at_the_maximum() -> None:
    grid = models()["JP"]
    assert grid.share_at_or_above(grid.reference) == 1.0
    assert grid.share_at_or_above(grid.max_magnitude) == 0.0
    assert 0 < grid.share_at_or_above(7.0) < grid.share_at_or_above(6.0) < 1


def test_the_simulation_agrees_with_the_price() -> None:
    """The capital model settles the same frequency the premium assumes."""
    curve = EARTHQUAKE.default_curve()
    draws = WorldDraws.draw(trials=8000, years=1.0, seed=11)
    exposure = Exposure("t1", "earthquake", dict(TOKYO), curve, 1000.0, 365.25)
    losses = settle(exposure, draws)
    observed = sum(1 for x in losses if x > 0) / len(losses)
    modelled = EARTHQUAKE.exceedance(exposure.subject, 365.25)(5.5)
    error = math.sqrt(modelled * (1 - modelled) / len(losses))
    assert abs(observed - modelled) < 4 * error + 0.01


def test_neighbours_pay_on_the_same_earthquake() -> None:
    curve = EARTHQUAKE.default_curve()
    draws = WorldDraws.draw(trials=4000, years=1.0, seed=3)
    a = settle(Exposure("a", "earthquake", dict(TOKYO), curve, 1000.0, 365.25), draws)
    b = settle(Exposure("b", "earthquake", {**TOKYO, "latitude": 35.70}, curve, 1000.0, 365.25), draws)
    far = settle(Exposure("c", "earthquake", {"latitude": 43.06, "longitude": 141.35, "radius_km": 50.0},
                          curve, 1000.0, 365.25), draws)
    both = sum(1 for x, y in zip(a, b) if x > 0 and y > 0)
    assert both > 0.8 * sum(1 for x in a if x > 0)
    with_far = sum(1 for x, y in zip(a, far) if x > 0 and y > 0)
    assert with_far < 0.2 * sum(1 for x in a if x > 0)


def test_a_policy_does_not_change_anothers_world() -> None:
    curve = EARTHQUAKE.default_curve()
    first = WorldDraws.draw(trials=2000, years=1.0, seed=5)
    alone = settle(Exposure("a", "earthquake", dict(TOKYO), curve, 1000.0, 365.25), first)
    second = WorldDraws.draw(trials=2000, years=1.0, seed=5)
    settle(Exposure("z", "earthquake", dict(SANTIAGO), curve, 1000.0, 365.25), second)
    again = settle(Exposure("a", "earthquake", dict(TOKYO), curve, 1000.0, 365.25), second)
    assert alone == again


def test_place_search_reaches_every_passed_country() -> None:
    for query, country in (("Tokyo", "JP"), ("Santiago", "CL"), ("Wellington", "NZ"),
                           ("Taipei", "TW"), ("Guadalajara", "MX"), ("Kadıköy", "TR"), ("kadikoy", "TR")):
        hits = search_world(query, 5)
        assert any(h["country"] == country and h["priced"] for h in hits), query


def test_place_search_says_when_a_country_is_not_priced() -> None:
    athens = search_world("Athens", 3)
    assert athens and athens[0]["country"] == "GR" and athens[0]["priced"] is False


def test_a_searched_place_is_inside_its_model() -> None:
    tokyo = search_world("Tokyo", 1)[0]
    grid = model_for(tokyo["latitude"], tokyo["longitude"])
    assert grid is not None and grid.code == "JP"
    assert haversine_km(tokyo["latitude"], tokyo["longitude"], 35.68, 139.69) < 5


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(trials=1500))


def test_the_hazard_endpoint_gives_the_page_what_it_prices_with(client) -> None:
    reply = client.get("/api/hazard", params={"latitude": 35.68, "longitude": 139.69}).json()
    assert reply["model"] == "JP" and reply["country"] == "JP"
    grid = reply["grid"]
    assert set(grid["radii"]) == {"25", "50", "100"}
    rate = grid["radii"]["50"]["rate_reference"]
    b, top, ref = grid["b_value"], grid["max_magnitude"], grid["reference_magnitude"]
    share = (10 ** (-b * (5.5 - ref)) - 10 ** (-b * (top - ref))) / (1 - 10 ** (-b * (top - ref)))
    page = 1 - math.exp(-rate * share)
    protocol = EARTHQUAKE.exceedance(EARTHQUAKE.validate_subject(dict(TOKYO)), 365.25)(5.5)
    assert abs(page - protocol) < 1e-6


def test_the_hazard_endpoint_refuses_where_nothing_is_priced(client) -> None:
    reply = client.get("/api/hazard", params={"latitude": 37.98, "longitude": 23.73})
    assert reply.status_code == 400
    assert "no tested earthquake model" in reply.json()["detail"]


def test_model_cards_list_the_failures_too(client) -> None:
    listing = client.get("/api/models").json()
    by_code = {row["country"]: row for row in listing["models"]}
    assert by_code["JP"]["passed"] is True
    assert by_code["GR"]["passed"] is False and by_code["GR"]["failed"]
    assert by_code["TR"]["priced_by"] == "fault model"
    card = client.get("/api/models/jp").json()
    assert card["validation"]["count"]["forecast"] > 0
    assert card["sources"]
    assert client.get("/api/models/zz").status_code == 404


def test_a_tokyo_quote_comes_from_the_japanese_model(client) -> None:
    reply = client.post("/api/quote", json={
        "peril": "earthquake", "subject": dict(TOKYO), "limit": 10_000, "term_days": 365,
    })
    assert reply.status_code == 200, reply.text
    body = reply.json()
    # At the magnitude this subject's own curve starts paying at, which is no
    # longer 5.5: a subject that does not say what year the building went up
    # is priced as the oldest one rather than the newest, so the first step
    # sits lower.
    subject = EARTHQUAKE.validate_subject(dict(TOKYO))
    starts_at = EARTHQUAKE.curve_for(subject).attachment
    modelled = EARTHQUAKE.exceedance(subject, 365)(starts_at)
    assert abs(body["trigger_probability"] - modelled) < 0.02
    assert body["expected_loss"] > 0


def test_global_place_search_endpoint(client) -> None:
    reply = client.get("/api/places", params={"query": "osaka"}).json()
    assert reply["places"][0]["country"] == "JP"
    assert "GeoNames" in reply["attribution"]
    turkish = client.get("/api/places").json()
    assert turkish["places"] and all(p["country"] == "TR" for p in turkish["places"])


def test_just_off_the_coast_is_measured_to_the_coast_not_to_its_corners() -> None:
    """A simplified outline has long edges, and a city can sit beside one.

    Niigata, a city of eight hundred thousand that this product offers, fell
    outside Japan: the nearest corner of the simplified polygon was further than
    the coastal tolerance even though the edge itself was a kilometre away. The
    model then had no rates for it, a fallback answered instead, and the figure
    that came out was intensity VII once in eleven thousand years in a city an
    earthquake destroyed in 1964.
    """
    from clause.hazard.model import _to_segment_km

    jp, us = models()["JP"], models()["US"]
    assert jp.contains(37.9226, 139.0412), "Niigata"
    assert us.contains(25.9018, -97.4975), "Brownsville"

    # And measuring to the edge has not swallowed anybody's neighbour.
    for latitude, longitude in ((37.5665, 126.9780), (43.1155, 131.8855),
                                (31.2304, 121.4737), (25.0330, 121.5654)):
        assert not jp.contains(latitude, longitude)
    for latitude, longitude in ((25.6866, -100.3161), (49.2827, -123.1207),
                                (23.1136, -82.3666)):
        assert not us.contains(latitude, longitude)
    tr = models()["TR"]
    for latitude, longitude in ((39.1, 26.3), (35.1856, 33.3823), (36.2021, 37.1343)):
        assert not tr.contains(latitude, longitude), (latitude, longitude)

    # The distance itself: a point beside the middle of a long edge is close to
    # the edge and far from either end of it.
    assert _to_segment_km(0.0, 0.0, 0.0, -5.0, 0.0, 5.0) == 0.0
    assert _to_segment_km(0.1, 0.0, 0.0, -5.0, 0.0, 5.0) == pytest.approx(11.1, abs=0.2)
    # Past the end of the edge it is the distance to the end.
    assert _to_segment_km(0.0, 6.0, 0.0, -5.0, 0.0, 5.0) == pytest.approx(111.2, abs=1.0)


def test_an_address_the_two_models_cannot_agree_on_is_not_priced() -> None:
    """A price from the smaller of two figures a hundred apart is not cover."""
    from clause.perils import shaking as sh

    assert sh.MOST_DISAGREEMENT == 2.0
    subject = {"latitude": 34.6937, "longitude": 135.5023}
    assert not sh.beyond_reconciling(subject)          # Osaka: the map is exact
    # Where nothing is published there is nothing to disagree with.
    assert not sh.beyond_reconciling({"latitude": 40.99, "longitude": 29.03})


def test_a_region_is_not_a_country() -> None:
    """Two fields that were one, and the United States is where they parted.

    A region is the extent a catalogue can be fitted over as a unit: one b
    value, one completeness magnitude, one largest event. Over its own box
    Alaska gives 0.829, 4.7 and 8.7; the lower forty eight gives 0.745, 4.7 and
    7.8, with a third of Alaska's rate of magnitude five. Fitted together, each
    would be described by the other, which is why Alaska and Hawaii were left
    out of the American box in the first place.

    Whose law writes the policy is a different question, and its answer for
    Anchorage is the same as for Brooklyn.
    """
    from clause.hazard.regions import REGIONS

    assert REGIONS["AK"].country == "US" and REGIONS["HI"].country == "US"
    # Every other region is a whole country and says so by saying nothing.
    for code, region in REGIONS.items():
        if code in ("AK", "HI"):
            continue
        assert region.country == code, code

    # And the shipped model files carry both, so the runtime never has to guess.
    have = models()
    assert {"US", "AK", "HI"} <= set(have), sorted(have)
    assert have["AK"].country == "US" and have["AK"].code == "AK"
    assert have["US"].country == "US" and have["US"].code == "US"


def test_the_country_a_buyer_is_in_is_never_a_region_code() -> None:
    """The licensing question, which is the one this split could get wrong.

    risk_country decides whose licence may write the policy and which register
    the buyer appears in. Answering "AK" would ask for a licence in a country
    that does not exist, and the buyer in Anchorage would be told no company is
    active where they live.
    """
    from clause.hazard.regions import REGIONS

    peril = EARTHQUAKE
    for name, latitude, longitude in (("Anchorage", 61.2181, -149.9003),
                                      ("Honolulu", 21.3069, -157.8583),
                                      ("Los Angeles", 34.0522, -118.2437),
                                      ("New York", 40.7128, -74.0060)):
        said = peril.risk_country({"latitude": latitude, "longitude": longitude,
                                   "radius_km": 50.0, "index": "shaking"})
        assert said == "US", f"{name} is in {said!r}"

    # Nor does the list of countries cover ever name one.
    countries = {r.country for r in REGIONS.values()}
    assert not (priced_countries() - countries), priced_countries()
    assert "AK" not in priced_countries() and "HI" not in priced_countries()


def test_a_region_that_passes_its_backtest_opens_its_country(monkeypatch) -> None:
    """The rule, exercised rather than waited for.

    Neither Alaska nor Hawaii passes its backtest today, so the list of
    countries cover is written in cannot tell a country from a region by
    looking at what ships. It will the day one of them does, and by then the
    list is what a buyer reads to find out whether their own country is open.
    """
    import clause.hazard.model as hm

    class Passing:
        code, country, passed = "AK", "US", True

    class Failing:
        code, country, passed = "HI", "US", False

    monkeypatch.setattr(hm, "models", lambda: {"AK": Passing(), "HI": Failing()})
    assert hm.priced_countries() == frozenset({"US"})


def test_alaska_is_priced_by_alaska_and_california_by_the_lower_forty_eight() -> None:
    """One country, three grids, and each address asked of the one that knows it.

    Before this, our own model answered Anchorage, Fairbanks, Juneau, Honolulu
    and Hilo with the same number: the global background floor, once in 11,119
    years at intensity VII. Not a measurement, a default, at an address four
    hundred kilometres from the largest earthquake ever recorded in North
    America.
    """
    peril = EARTHQUAKE
    anchorage = {"latitude": 61.2181, "longitude": -149.9003, "radius_km": 50.0}
    hilo = {"latitude": 19.7299, "longitude": -155.0907, "radius_km": 50.0}
    los_angeles = {"latitude": 34.0522, "longitude": -118.2437, "radius_km": 50.0}

    assert peril.grid_model(anchorage).code == "AK"
    assert peril.grid_model(hilo).code == "HI"
    assert peril.grid_model(los_angeles).code == "US"

    # And the floor is gone: three different rates where there was one.
    from clause.perils import shaking as sh
    rates = {name: sh.raw_rate_at_least(where, 7.0)
             for name, where in (("Anchorage", anchorage), ("Hilo", hilo),
                                 ("Los Angeles", los_angeles))}
    assert len(set(round(r, 12) for r in rates.values())) == 3, rates
    # Anchorage is the most exposed of the three, which is why this was worth doing.
    assert rates["Anchorage"] > rates["Los Angeles"] > 0
