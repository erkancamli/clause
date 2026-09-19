"""Cover is capped by what the thing is worth, and what it is worth comes from
its size. A 100 m² garden cannot buy a 100 hectare farm's cover."""

from __future__ import annotations

import pytest

from clause.protocol.valuation import ValuationError, value_of
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_api_security import buy_body, buy_terms, client, buyer  # noqa: F401


def test_a_bigger_field_carries_more_cover() -> None:
    small = value_of({"kind": "field", "crop": "wheat", "area_ha": 0.01})   # 100 m²
    large = value_of({"kind": "field", "crop": "wheat", "area_ha": 10})     # 100,000 m²
    assert large.value == pytest.approx(small.value * 1000)
    assert small.value < 10


def test_a_home_is_valued_by_floor_area_and_country() -> None:
    istanbul = value_of({"kind": "home", "building": "flat", "area_m2": 100}, country="TR")
    tokyo = value_of({"kind": "home", "building": "flat", "area_m2": 100}, country="JP")
    assert tokyo.value > istanbul.value > 0
    assert "100 m²" in istanbul.basis


@pytest.mark.parametrize("size", [
    {"kind": "home", "building": "castle", "area_m2": 100},
    {"kind": "home", "building": "flat", "area_m2": 5},
    {"kind": "field", "crop": "wheat", "area_ha": 0},
    {"kind": "field", "crop": "gold", "area_ha": 1},
    {"kind": "boat"},
])
def test_a_description_that_gives_no_value_is_refused(size) -> None:
    with pytest.raises(ValuationError):
        value_of(size, country="TR")


def test_no_schedule_means_no_home_cover() -> None:
    with pytest.raises(ValuationError, match="no rebuild cost schedule"):
        value_of({"kind": "home", "building": "flat", "area_m2": 100}, country="GR")


def test_the_protocol_refuses_cover_above_what_the_size_supports(client, buyer) -> None:
    """The buyer claims a large value but describes a small flat: the size wins."""
    device, address = buyer
    size = {"kind": "home", "building": "flat", "area_m2": 40.0}          # 21,000
    terms = buy_terms(limit=50_000.0, value_at_risk=90_000.0, size=size)
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms}).json()
    body = buy_body(address, challenge["nonce"], device.sign(challenge["message"]), client=client)
    body["interest"]["size"] = size
    reply = client.post("/api/policies", json=body)
    assert reply.status_code == 451
    assert "21,000" in reply.text


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
