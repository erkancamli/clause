"""The company's desk: its book found, filtered, due for renewal, by
province, and as a file. Nothing new is stored; what a policy already
carries is read the way an underwriter reads it."""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol import desk
from test_api_security import Device, buy_body, buy_terms, session_for
from test_commerce import RIDER_KEY, TOKEN, register, rider_buy, sign_mandate

KADIKOY = {"latitude": 40.99, "longitude": 29.03, "radius_km": 50, "place": "İstanbul, Kadıköy", "built": 2005}


def buy_quake(client, device, address, limit):
    interest = {"what": "a flat in Kadıköy", "country": "TR", "inside_trigger_area": True,
                "value_at_risk": 300_000, "size": {"kind": "home", "building": "flat", "area_m2": 100, "built": 2005}}
    terms = buy_terms(peril="earthquake", subject=KADIKOY, limit=float(limit), value_at_risk=300_000.0, size=interest["size"])
    challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "buy", "terms": terms}).json()
    reply = client.post("/api/policies", json=buy_body(address, challenge["nonce"], device.sign(challenge["message"]),
                                                       client=client, peril="earthquake", subject=KADIKOY,
                                                       limit=limit, interest=interest))
    assert reply.status_code == 200, reply.text
    return reply.json()["policy"]

OP = {"x-operator-token": TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CLAUSE_RIDER_PURCHASE_KEY_SHA256", hashlib.sha256(RIDER_KEY.encode()).hexdigest())
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, specimens=True))
    with TestClient(app) as c:
        yield c


class Subject:
    def __init__(self, **kw): self.subject = kw


def test_the_province_is_read_from_where_the_cover_stands() -> None:
    assert desk.province_of(Subject(latitude=40.99, longitude=29.03)) == "İstanbul"      # Kadıköy, a district
    assert desk.province_of(Subject(latitude=40.15, longitude=26.41)) == "Çanakkale"
    assert desk.province_of(Subject(station="TR-KONYA", distance_km=6, hectares=50)) == "Konya"
    assert desk.province_of(Subject(route="TK-IST-LHR")) == ""
    assert desk.province_of(Subject(latitude=35.68, longitude=139.69)) == ""            # Tokyo: no Turkish province


def test_the_desk_finds_filters_groups_and_exports(client) -> None:
    device, address = register(client)
    bought = [buy_quake(client, device, address, 20_000), buy_quake(client, device, address, 30_000)]
    rider_buy(client, sign_mandate(client, device, address).json()["token"])   # a flight, with no province
    carrier_id = bought[0]["metadata"]["carrier"]
    assert carrier_id
    op = {"authorization": f"Bearer {client.post('/api/operator/session', json={'reviewer': 'Ayşe'}, headers=OP).json()['token']}"}

    everything = client.get("/api/operator/policies", headers=op).json()
    assert everything["summary"]["policies"] >= 2 and everything["total"] == everything["summary"]["policies"]
    quake = next(r for r in everything["policies"] if r["policy_id"] == bought[0]["policy_id"])
    assert quake["province"] == "İstanbul" and quake["carrier"] and quake["days_left"] > 300
    assert all(g["policies"] and g["in_force"] > 0 for g in everything["by_province"])
    # Found by its number, by its place, and not by nonsense.
    one = bought[0]["policy_id"]
    assert [r["policy_id"] for r in client.get("/api/operator/policies", params={"q": one[-6:]}, headers=op).json()["policies"]] == [one]
    assert client.get("/api/operator/policies", params={"q": "istanbul"}, headers=op).json()["total"] >= 2
    assert client.get("/api/operator/policies", params={"q": "zzz-nothing"}, headers=op).json()["total"] == 0
    # By status, by carrier, by province, sorted, paged.
    paid = client.get("/api/operator/policies", params={"status": "paid"}, headers=op).json()["policies"]
    assert all(r["status"] == "paid" for r in paid)
    assert client.get("/api/operator/policies", params={"carrier_id": carrier_id, "status": "open"}, headers=op).json()["total"] >= 2
    assert client.get("/api/operator/policies", params={"province": "İstanbul"}, headers=op).json()["total"] >= 2
    page = client.get("/api/operator/policies", params={"sort": "limit", "order": "asc", "limit": 1, "offset": 1}, headers=op).json()
    assert len(page["policies"]) == 1 and page["offset"] == 1
    # A year's cover is not due for renewal yet; within 400 days it is.
    soon = client.get("/api/operator/policies", params={"due_within": 30}, headers=op).json()["policies"]
    assert all(0 <= r["days_left"] <= 30 for r in soon) and not any(r["policy_id"] == one for r in soon)
    assert any(r["policy_id"] == one for r in client.get("/api/operator/policies", params={"due_within": 400}, headers=op).json()["policies"])
    assert everything["summary"]["renewals_due"] == len(soon)
    # CSV, with the header the accountant expects.
    text = client.get("/api/operator/policies", params={"format": "csv"}, headers=op).text
    assert text.splitlines()[0].startswith("policy_id,peril,subject,province") and one in text

    # The company sees its own book, with the address it was given; a stranger sees nothing.
    desk_device, desk_addr = register(client)
    auth = {"authorization": f"Bearer {session_for(client, desk_device, desk_addr)}"}
    assert client.get("/api/company/policies", params={"carrier_id": carrier_id}, headers=auth).status_code == 404
    assert client.post("/api/company/specimen", json={"carrier_id": carrier_id}, headers=auth).status_code == 200
    mine = client.get("/api/company/policies", params={"carrier_id": carrier_id}, headers=auth).json()
    assert mine["total"] >= 2 and all(r["carrier_id"] == carrier_id for r in mine["policies"])
    assert "address" in mine["policies"][0]
    assert client.get("/api/company/policies", params={"carrier_id": carrier_id, "format": "csv"}, headers=auth).status_code == 200


def test_renewals_due_are_the_open_policies_ending_soon() -> None:
    import time
    now = time.time()

    class P:
        def __init__(self, pid, ends, status="active", limit=100.0):
            from clause.perils import EARTHQUAKE
            from clause.protocol.policy import PolicyStatus
            self.policy_id = pid; self.peril_key = "earthquake"; self.peril = EARTHQUAKE
            self.subject = {"latitude": 40.99, "longitude": 29.03, "radius_km": 50, "place": "Kadıköy"}
            self.limit = limit; self.premium = 10.0; self.payout = 0.0
            self.status = PolicyStatus(status); self.bought_at = now - 100; self.starts_at = now - 100
            self.ends_at = ends; self.holder = "holder-address-xyz"; self.metadata = {"carrier": "c1"}
        @property
        def is_open(self): return self.status.value == "active"

    rows = desk.select([P("A", now + 5 * 86400), P("B", now + 60 * 86400), P("C", now + 2 * 86400, status="lapsed")])
    due = [r["policy_id"] for r in rows if r["renewal_due"]]
    assert due == ["A"]
    assert desk.summary(rows) == {"policies": 3, "open": 2, "in_force": 200.0, "renewals_due": 1,
                                  "renewals_in_force": 100.0, "provinces": 1}
    assert desk.by_province(rows)[0] == {"province": "İstanbul", "policies": 2, "in_force": 200.0, "premiums": 20.0,
                                         "perils": {"earthquake": 2}}
    assert [r["policy_id"] for r in desk.select([P("A", now + 5 * 86400), P("B", now + 60 * 86400)], sort="ends_at", descending=False)] == ["A", "B"]
