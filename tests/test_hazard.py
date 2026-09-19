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


def test_only_passed_models_are_sold() -> None:
    passed = {code for code, m in models().items() if m.passed}
    assert priced_countries() == frozenset(passed)
    assert EARTHQUAKE.territory == frozenset({"TR"}) | passed
    for code in ("GR", "IT", "ID", "PH"):
        assert code not in EARTHQUAKE.territory, f"{code} failed its backtest and must not be sold"


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
    modelled = EARTHQUAKE.exceedance(EARTHQUAKE.validate_subject(dict(TOKYO)), 365)(5.5)
    assert abs(body["trigger_probability"] - modelled) < 0.02
    assert body["expected_loss"] > 0


def test_global_place_search_endpoint(client) -> None:
    reply = client.get("/api/places", params={"query": "osaka"}).json()
    assert reply["places"][0]["country"] == "JP"
    assert "GeoNames" in reply["attribution"]
    turkish = client.get("/api/places").json()
    assert turkish["places"] and all(p["country"] == "TR" for p in turkish["places"])
