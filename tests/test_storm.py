"""Storm cover on extreme wind at the address.

The model file is built offline from NASA POWER (``python -m
clause.hazard.wind_build``), the way the rain model is. Where it has been
built, the first test reads it and asserts it passed its test. Everywhere
else the mechanics still have to hold: the curve at each place, the price and
the capital model agreeing, the chain settling on a wind reading, the
application path for a home. So the rest of this file runs on a synthetic
model, written for the test and pointed at, and marked as such; nothing in it
is a claim about Türkiye's wind.
"""

from __future__ import annotations

import json

import pytest

from conftest import cover_has_started
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.perils import STORM, storm
from clause.perils.places import PLACES
from clause.pricing.simulation import Exposure, WorldDraws, settle
from clause.protocol import PolicyStatus
from test_api_security import Device, buy_body, buy_terms, session_for

CANAKKALE = {"latitude": 40.15, "longitude": 26.41}
KONYA = {"latitude": 37.87, "longitude": 32.49}
TOKEN = "operator-token-for-tests"
REAL = storm.MODEL


def synthetic_model() -> dict:
    """A wind model of the right shape: windier on the coasts, calmer inland.
    Deterministic in the place, and marked so nobody mistakes it."""
    places = []
    for place in PLACES:
        if place.kind != "province":
            continue
        coast = min(abs(place.longitude - 26.0), abs(place.latitude - 41.5), abs(place.latitude - 36.5))
        mu = 78.0 - 4.0 * min(coast, 3.0)
        beta = 9.0 + 0.5 * (hash(place.name) % 5)
        places.append({"name": place.name, "latitude": place.latitude, "longitude": place.longitude,
                       "gumbel": {"mu": round(mu, 3), "beta": round(beta, 3)},
                       "record_years": 45, "fit_years": 30, "largest_kmh": round(mu + 3.5 * beta, 1)})
    return {"code": "TR", "kind": "wind_extreme", "unit": "km/h", "synthetic": True,
            "validation": {"passed": True, "failed": [], "fitted_until": 2010, "tested_from": 2011,
                           "changes_after_first_run": []},
            "places": places}


@pytest.fixture
def wind(tmp_path, monkeypatch):
    """The committed model where it exists; a synthetic one otherwise."""
    if not REAL.exists():
        path = tmp_path / "wind_TR.json"
        path.write_text(json.dumps(synthetic_model()), encoding="utf-8")
        monkeypatch.setattr(storm, "MODEL", path)
    storm.model.cache_clear()
    yield storm.model()
    storm.model.cache_clear()


@pytest.fixture
def no_wind(tmp_path, monkeypatch):
    monkeypatch.setattr(storm, "MODEL", tmp_path / "missing.json")
    storm.model.cache_clear()
    yield
    storm.model.cache_clear()


@pytest.mark.skipif(not REAL.exists(), reason="the wind model has not been built here")
def test_the_committed_wind_model_passed_its_test() -> None:
    storm.model.cache_clear()
    v = storm.model()["validation"]
    assert v["passed"] and v["tested_from"] == v["fitted_until"] + 1
    assert storm.model()["unit"] == "km/h"
    assert all(p["fit_years"] >= 30 for p in storm.model()["places"])
    assert STORM.territory == frozenset({"TR"})


def test_without_a_model_nothing_can_be_priced_anywhere(no_wind) -> None:
    assert STORM.territory == frozenset()
    with pytest.raises(ValueError, match="60 km"):
        STORM.validate_subject(dict(CANAKKALE))
    app = create_app(trials=200, seed=3, run_chain=False, seed_book=False,
                     settings=Settings(faucet=True, operator_token=TOKEN))
    with TestClient(app) as client:
        assert client.get("/api/storm", params=CANAKKALE).status_code == 503
        assert client.get("/api/compliance").json()["priceable"]["storm"] == []


def test_each_place_pays_on_what_is_extreme_there(wind) -> None:
    coast = STORM.curve_for(STORM.validate_subject(dict(CANAKKALE)))
    inland = STORM.curve_for(STORM.validate_subject(dict(KONYA)))
    assert coast.attachment > inland.attachment
    for curve in (coast, inland):
        levels = [b.level for b in curve.breakpoints]
        assert levels == sorted(levels) and [b.share for b in curve.breakpoints] == [0.25, 0.60, 1.00]


def test_the_trigger_is_about_a_one_in_twenty_five_year_day(wind) -> None:
    subject = STORM.validate_subject(dict(CANAKKALE))
    p = STORM.exceedance(subject, 365.25)(STORM.curve_for(subject).attachment)
    assert p == pytest.approx(0.04, abs=0.003)
    assert STORM.exceedance(subject, 182.625)(STORM.curve_for(subject).attachment) < p


def test_outside_the_tested_places_is_refused(wind) -> None:
    with pytest.raises(ValueError, match="60 km"):
        STORM.validate_subject({"latitude": 35.68, "longitude": 139.69})
    assert STORM.risk_country(dict(CANAKKALE)) == "TR"


def test_the_capital_model_agrees_with_the_price(wind) -> None:
    subject = STORM.validate_subject(dict(KONYA))
    exposure = Exposure("s", "storm", subject, STORM.curve_for(subject), 1000.0, 365.25)
    losses = settle(exposure, WorldDraws.draw(trials=20000, years=1.0, seed=9))
    observed = sum(1 for x in losses if x > 0) / len(losses)
    assert observed == pytest.approx(0.04, abs=0.006)


def test_two_homes_under_one_front_settle_together(wind) -> None:
    """The shared factor: the day that takes roofs in one province takes them
    in the next. Losses at two places correlate; they are not independent."""
    draws = WorldDraws.draw(trials=6000, years=1.0, seed=5)
    a = STORM.validate_subject(dict(CANAKKALE))
    b = STORM.validate_subject({"latitude": 39.65, "longitude": 27.89})   # Balıkesir
    la = settle(Exposure("a", "storm", a, STORM.curve_for(a), 1.0, 365.25), draws)
    lb = settle(Exposure("b", "storm", b, STORM.curve_for(b), 1.0, 365.25), draws)
    both = sum(1 for x, y in zip(la, lb) if x > 0 and y > 0) / len(la)
    pa = sum(1 for x in la if x > 0) / len(la)
    pb = sum(1 for y in lb if y > 0) / len(lb)
    assert both > 1.5 * pa * pb


def test_the_basis_risk_names_what_is_not_covered(wind) -> None:
    for word in ("hail", "lightning", "snow", "flood", "gust"):
        assert word in STORM.basis_risk
    assert STORM.predicate(STORM.validate_subject(dict(CANAKKALE)), STORM.curve_for(STORM.validate_subject(dict(CANAKKALE))), "x").startswith(
        'edge("api.wind.example/v1/daily-max?lat=40.15&lon=26.41").wind_24h_kmh >= ')


def test_a_storm_policy_settles_on_the_wind_reading_and_the_price_holds_in_the_book(wind) -> None:
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN))
    with TestClient(app) as client:
        levels = client.get("/api/storm", params=CANAKKALE).json()
        assert [l["years"] for l in levels["levels"]] == [25, 50, 100]
        subject = {**CANAKKALE, "place": "Çanakkale"}
        quoted = client.post("/api/quote", json={"peril": "storm", "subject": subject, "limit": 60_000, "term_days": 365})
        assert quoted.status_code == 200, quoted.text
        assert quoted.json()["can_write"] and quoted.json()["structure"][0].endswith("km/h, pays 25% of the limit")
        assert 0.02 < quoted.json()["trigger_probability"] < 0.08
        device = Device()
        address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
        interest = {"what": "a house in Çanakkale", "country": "TR", "inside_trigger_area": True,
                    "value_at_risk": 300_000, "size": {"kind": "home", "building": "house", "area_m2": 140}}
        terms = buy_terms(peril="storm", subject=subject, limit=60_000.0, value_at_risk=300_000.0,
                          size=interest["size"])
        challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "buy", "terms": terms}).json()
        bought = client.post("/api/policies", json=buy_body(
            address, challenge["nonce"], device.sign(challenge["message"]), client=client,
            peril="storm", subject=subject, limit=60_000, interest=interest))
        assert bought.status_code == 200, bought.text
        policy = bought.json()["policy"]
        assert policy["peril"] == "storm" and "wind read at Çanakkale" in policy["subject_text"]
        assert bought.json()["compliance"]["carrier"] is not None
        chain, pool = app.state.chain, app.state.pool
        found = pool.policies[policy["policy_id"]]
        attachment = STORM.curve_for(found.subject).attachment
        cover_has_started(found)
        # A windy day short of the trigger pays nothing; one at it pays the first band.
        chain.attest(found.data_reference, "wind_24h_kmh", round(attachment - 1.0, 1))
        for _ in range(3):
            chain.produce_block()
        assert pool.policies[policy["policy_id"]].status is PolicyStatus.ACTIVE
        chain.attest(found.data_reference, "wind_24h_kmh", round(attachment + 0.5, 1))
        for _ in range(chain.confirm_blocks(found) + 3):
            chain.produce_block()
        found = pool.policies[policy["policy_id"]]
        assert found.status is PolicyStatus.PAID and found.payout == pytest.approx(15_000.0)
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        mine = client.get("/api/policies", headers=auth).json()
        assert any(p["policy_id"] == policy["policy_id"] and p["status"] == "paid" for p in mine["items"])


def test_a_home_against_storm_is_applied_for_with_its_address(wind) -> None:
    """Storm is cover on a home, so it takes the application path a home
    takes: the address is required and the company decides."""
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, direct_buy=False))
    with TestClient(app) as client:
        device = Device()
        address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
        subject = {**KONYA, "place": "Konya"}
        interest = {"what": "a house in Konya", "country": "TR", "inside_trigger_area": True,
                    "value_at_risk": 200_000, "size": {"kind": "home", "building": "house", "area_m2": 120}}
        terms = buy_terms(peril="storm", subject=subject, limit=40_000.0, value_at_risk=200_000.0, size=interest["size"])
        def signed(extra_terms: dict | None = None, **overrides):
            # Every signature is spent by the call it authorises, refused or not.
            challenge = client.post("/api/auth/challenge", json={
                "address": address, "purpose": "buy", "terms": {**terms, **(extra_terms or {})}}).json()
            return buy_body(address, challenge["nonce"], device.sign(challenge["message"]),
                            **{"peril": "storm", "subject": subject, "limit": 40_000, "interest": interest, **overrides})

        assert client.post("/api/policies", json=signed()).status_code == 409
        applied = client.post("/api/applications", json=signed())
        assert applied.status_code == 422 and "address" in applied.text
        home = {**interest, "address": {"street": "Mevlana Cd.", "number": "3", "city": "Konya"}}
        contract = client.post("/api/contract", json={"peril": "storm", "subject": subject, "limit": 40_000,
                                                       "term_days": 365, "interest": home, "settlement": "fiat"})
        assert contract.status_code == 200, contract.text
        text = contract.json()["text"]
        assert "Storm, on extreme wind at the address" in text and "hail, lightning, snow load and flood" in text
        with_address = signed({"contract_hash": contract.json()["hash"]}, interest=home,
                              contract_hash=contract.json()["hash"])
        applied = client.post("/api/applications", json=with_address)
        assert applied.status_code == 200, applied.text
        assert "ownership" in applied.json()["application"]["checks"]
