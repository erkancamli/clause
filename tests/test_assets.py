"""The things a person owns, written down once for the next purchase."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol.assets import AssetError, Assets
from test_api_security import Device, session_for


def test_a_home_needs_its_size_and_address_and_a_field_needs_neither() -> None:
    book = Assets()
    with pytest.raises(AssetError, match="street and the city"):
        book.save("a", {"kind": "home", "label": "the flat", "size": {"area_m2": 90, "built": 2010}})
    home = book.save("a", {"kind": "home", "label": "the flat", "size": {"area_m2": 90, "built": 2010, "building": "flat"},
                           "address": {"street": "Specimen Sokak", "number": "3", "city": "İstanbul"},
                           "latitude": 41.0, "longitude": 29.0, "place": "Kadıköy, İstanbul", "country": "TR"})
    assert home.size == {"kind": "home", "building": "flat", "area_m2": 90.0, "built": 2010}
    with pytest.raises(AssetError, match="year built"):
        book.save("a", {"kind": "home", "label": "old flat", "size": {"area_m2": 90, "built": "soon"}, "address": {"street": "s", "city": "c"}})
    field = book.save("a", {"kind": "field", "label": "the wheat", "size": {"crop": "wheat", "area_ha": 12}})
    assert field.address is None
    car = book.save("a", {"kind": "vehicle", "label": "white Corolla", "size": {"model_year": 2016, "plate": "34 ABC 123"},
                          "address": {"street": "Specimen Caddesi", "city": "İstanbul"}})
    assert car.size["plate"] == "34 ABC 123"
    assert [a.kind for a in book.mine("a")] == ["home", "vehicle", "field"]
    # Updating keeps the id; another account cannot touch it.
    again = book.save("a", {"asset_id": car.asset_id, "kind": "vehicle", "label": "the Corolla", "size": {"model_year": 2016},
                            "address": {"street": "Specimen Caddesi", "city": "İstanbul"}})
    assert again.asset_id == car.asset_id and again.label == "the Corolla" and again.updated_at
    with pytest.raises(AssetError, match="no such"):
        book.save("b", {"asset_id": car.asset_id, "kind": "vehicle", "label": "mine now", "size": {"model_year": 2016},
                        "address": {"street": "s", "city": "c"}})
    with pytest.raises(AssetError, match="no such"):
        book.remove("b", car.asset_id)
    book.remove("a", car.asset_id)
    assert len(book.mine("a")) == 2


def test_assets_are_kept_behind_the_session_and_returned_to_their_owner() -> None:
    app = create_app(trials=200, run_chain=False, seed_book=False, settings=Settings(faucet=True))
    with TestClient(app) as client:
        device = Device()
        address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        assert client.get("/api/assets").status_code == 401
        made = client.post("/api/assets", headers=auth, json={
            "kind": "home", "label": "the flat in Kadıköy", "size": {"area_m2": 90, "built": 2010, "building": "flat"},
            "address": {"street": "Specimen Sokak", "number": "3", "flat": "4", "postcode": "34710", "city": "İstanbul"},
            "latitude": 40.98, "longitude": 29.03, "place": "Kadıköy, İstanbul", "country": "TR"})
        assert made.status_code == 200, made.text
        mine = client.get("/api/assets", headers=auth).json()["assets"]
        assert len(mine) == 1 and mine[0]["address"]["street"] == "Specimen Sokak"
        other = Device()
        other_address = client.post("/api/auth/register", json={"public_key": other.public}).json()["address"]
        other_auth = {"authorization": f"Bearer {session_for(client, other, other_address)}"}
        assert client.get("/api/assets", headers=other_auth).json()["assets"] == []
        assert client.post(f"/api/assets/{mine[0]['asset_id']}/remove", headers=other_auth).status_code == 404
        assert client.post(f"/api/assets/{mine[0]['asset_id']}/remove", headers=auth).json()["assets"] == []
