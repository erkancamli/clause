"""Letting a company in: the operator's checklist, recorded item by item,
and activation refused until the required items are confirmed."""

from __future__ import annotations

import base64
import time

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol import vetting
from test_kyb import TOKEN, registration, sign_in


def app_for(tmp_path):
    return create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                      settings=Settings(operator_token=TOKEN), store_path=tmp_path / "book.sqlite")


def pdf(text: str) -> str:
    return base64.b64encode(("%PDF-1.4 " + text).encode()).decode()


def test_a_turkish_carrier_gets_the_turkish_checklist_and_cannot_be_activated_unchecked(tmp_path) -> None:
    with TestClient(app_for(tmp_path)) as client:
        body = registration()
        body["domicile"] = "TR"
        body["mersis"] = "0123456789012345"
        body["tax_number"] = "1234567890"
        body["evidence"] = [{"kind": "licence_certificate", "filename": "ruhsat.pdf",
                             "content_type": "application/pdf", "data": pdf("ruhsat")}]
        reply = client.post("/api/carriers", json=body)
        assert reply.status_code == 200, reply.text
        carrier = reply.json()["carrier"]
        cid = carrier["carrier_id"]
        assert carrier["mersis"] == "0123456789012345" and carrier["tax_number"] == "1234567890"
        auth = {"authorization": f"Bearer {sign_in(client)}"}

        listed = client.get(f"/api/carriers/{cid}/vetting", headers=auth)
        assert listed.status_code == 200, listed.text
        items = {i["key"]: i for i in listed.json()["items"]}
        assert "membership" in items and items["membership"]["required"]
        assert any("Yangın ve Doğal Afetler" in b for b in items["licence"]["branches"])
        assert any("mersis" in l["url"] for l in items["entity"]["where"])
        assert any("sanctionsmap" in l["url"] for l in items["sanctions"]["where"])
        assert items["licence"]["documents"][0]["filename"] == "ruhsat.pdf"
        assert not listed.json()["can_activate"] and "licence" in listed.json()["missing"]

        # Activation is refused while anything required is unconfirmed, and says what.
        refused = client.post(f"/api/carriers/{cid}/activate", json={"note": "looks fine"}, headers=auth)
        assert refused.status_code == 422 and "confirm each required check" in refused.text
        assert "Türkiye Sigorta Birliği" in refused.text

        # The reviewer works the list: where they looked, what they saw.
        for key in ("entity", "domain", "licence", "signatory", "sanctions", "enforcement", "membership"):
            done = client.post(f"/api/carriers/{cid}/vetting", headers=auth,
                               json={"key": key, "ok": True, "source": f"https://register.example/{key}",
                                     "note": "seen on the register"})
            assert done.status_code == 200, done.text
        state = client.get(f"/api/carriers/{cid}/vetting", headers=auth).json()
        assert state["can_activate"] and state["missing"] == []
        assert state["items"][0]["state"]["by"] and state["items"][0]["state"]["source"].endswith("/entity")
        # An unknown item is refused.
        assert client.post(f"/api/carriers/{cid}/vetting", headers=auth, json={"key": "vibes", "ok": True}).status_code == 422

        activated = client.post(f"/api/carriers/{cid}/activate", json={"note": "all seven confirmed"}, headers=auth)
        assert activated.status_code == 200, activated.text
        row = activated.json()["carrier"]
        assert row["status"] == "active"
        # The next review is a year out, and the review carries the checklist as it stood.
        assert row["review_due_at"] > time.time() + 360 * 86400
        assert row["reviews"][-1]["checks"]["membership"]["ok"] is True

        # The company sees its own checklist, a stranger sees nothing.
        assert client.get(f"/api/carriers/{cid}/vetting").status_code == 401


def test_a_failed_item_and_a_set_aside_item_are_recorded_and_the_company_can_add_documents(tmp_path) -> None:
    with TestClient(app_for(tmp_path)) as client:
        body = registration()
        body["domicile"] = "DE"
        reply = client.post("/api/carriers", json=body)
        cid = reply.json()["carrier"]["carrier_id"]
        auth = {"authorization": f"Bearer {sign_in(client)}"}
        items = {i["key"]: i for i in client.get(f"/api/carriers/{cid}/vetting", headers=auth).json()["items"]}
        assert "membership" not in items
        assert any("bafin" in l["url"] for l in items["licence"]["where"])
        failed = client.post(f"/api/carriers/{cid}/vetting", headers=auth,
                             json={"key": "sanctions", "ok": False, "source": "sanctionsmap.eu", "note": "a director listed"})
        assert failed.status_code == 200
        aside = client.post(f"/api/carriers/{cid}/vetting", headers=auth,
                            json={"key": "solvency", "ok": None, "note": "not needed for a reinsurer-backed book"})
        assert aside.status_code == 200
        state = client.get(f"/api/carriers/{cid}/vetting", headers=auth).json()
        by_key = {i["key"]: i for i in state["items"]}
        assert by_key["sanctions"]["state"]["ok"] is False and not by_key["sanctions"]["done"]
        assert by_key["solvency"]["state"]["ok"] is None and by_key["solvency"]["settled"]
        assert "sanctions" in state["missing"]


def test_the_company_adds_documents_later_and_sees_what_is_owed(tmp_path) -> None:
    from test_api_security import Device, session_for
    with TestClient(app_for(tmp_path)) as client:
        device = Device()
        address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
        body = registration()
        body["domicile"] = "TR"
        challenge = client.post("/api/auth/challenge", json={
            "address": address, "purpose": "register",
            "terms": {"name": body["name"], "role": body["role"], "domicile": "TR"}}).json()
        body.update({"address": address, "nonce": challenge["nonce"], "signature": device.sign(challenge["message"])})
        reply = client.post("/api/carriers", json=body)
        assert reply.status_code == 200, reply.text
        cid = reply.json()["carrier"]["carrier_id"]
        mine = {"authorization": f"Bearer {session_for(client, device, address)}"}
        seen = client.get(f"/api/carriers/{cid}/vetting", headers=mine)
        assert seen.status_code == 200 and seen.json()["viewer"] == "company"
        added = client.post(f"/api/company/{cid}/evidence", headers=mine, json={"evidence": [
            {"kind": "membership_proof", "filename": "tsb.pdf", "content_type": "application/pdf", "data": pdf("tsb")},
            {"kind": "signature_circular", "filename": "imza.pdf", "content_type": "application/pdf", "data": pdf("imza")},
        ]})
        assert added.status_code == 200, added.text
        docs = added.json()["carrier"]["evidence"]
        assert [d["n"] for d in docs] == [0, 1] and docs[0]["kind"] == "membership_proof"
        items = {i["key"]: i for i in added.json()["items"]}
        assert items["membership"]["documents"][0]["filename"] == "tsb.pdf"
        assert items["signatory"]["documents"][0]["filename"] == "imza.pdf"
        # A stranger's account cannot add documents to it.
        other = Device()
        other_addr = client.post("/api/auth/register", json={"public_key": other.public}).json()["address"]
        assert client.post(f"/api/company/{cid}/evidence", json={"evidence": [
            {"kind": "other", "filename": "x.pdf", "content_type": "application/pdf", "data": pdf("x")}]},
            headers={"authorization": f"Bearer {session_for(client, other, other_addr)}"}).status_code == 404


def test_a_turkish_identifier_has_to_have_the_right_shape(tmp_path) -> None:
    with TestClient(app_for(tmp_path)) as client:
        body = registration(); body["domicile"] = "TR"; body["mersis"] = "12345"
        assert client.post("/api/carriers", json=body).status_code == 422
        body = registration(); body["domicile"] = "TR"; body["tax_number"] = "12"
        assert client.post("/api/carriers", json=body).status_code == 422


def test_what_is_due_again() -> None:
    class L:
        def __init__(self, ref, days):
            self.reference = ref; self.expires_at = time.time() + days * 86400
        def live(self, *, now=None): return self.expires_at > (now or time.time())
        def expiring(self, *, now=None): return self.live(now=now) and self.expires_at - (now or time.time()) < 60 * 86400

    class C:
        licences = (L("A", 20), L("B", 400), L("C", -5))
        review_due_at = time.time() + 10 * 86400
    d = vetting.due(C())
    assert d["review_due_soon"] and not d["review_overdue"]
    assert d["licences_expiring"] == ["A"] and d["licences_lapsed"] == ["C"]
