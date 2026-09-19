"""Knowing a company is the company it says it is.

The automatic checks are run against a fake internet here, so the tests say
what each answer means rather than whether GLEIF is up.
"""

from __future__ import annotations

import base64
import json
import time

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol import kyb
from test_operator import TOKEN, registration, sign_in

YEAR = 365 * 86400.0


def gleif(name: str, *, status: str = "ACTIVE", registration: str = "ISSUED", country: str = "TR"):
    return json.dumps({"data": {"attributes": {
        "entity": {"legalName": {"name": name}, "status": status, "legalAddress": {"country": country}},
        "registration": {"status": registration},
    }}}).encode()


def internet(pages: dict[str, tuple[int, bytes]]):
    def fetch(url: str, *, timeout: float = 10.0, limit: int = 200_000):
        return pages.get(url, (404, b""))
    return fetch


def test_an_lei_anchors_the_legal_name() -> None:
    lei = "5493001KJTIIGC8Y1R12"
    net = internet({kyb.GLEIF + lei: (200, gleif("Örnek Sigorta Anonim Şirketi"))})
    good = kyb.check_lei(lei, "Örnek Sigorta A.Ş.", fetch=net)
    assert good["ok"] and good["legal_name"].startswith("Örnek") and good["name_match"] >= 0.5
    other = kyb.check_lei(lei, "Completely Different Assurance plc", fetch=net)
    assert not other["ok"] and other["name_match"] < 0.5
    assert not kyb.check_lei("", "Anyone", fetch=net)["given"]
    assert "well formed" in kyb.check_lei("NOT-AN-LEI", "Anyone", fetch=net)["summary"]
    assert "no such LEI" in kyb.check_lei("5493001KJTIIGC8Y1R99", "Anyone", fetch=net)["summary"]


def test_a_lapsed_lei_does_not_pass() -> None:
    lei = "5493001KJTIIGC8Y1R12"
    net = internet({kyb.GLEIF + lei: (200, gleif("Örnek Sigorta", registration="LAPSED"))})
    assert not kyb.check_lei(lei, "Örnek Sigorta", fetch=net)["ok"]


def test_the_proof_file_shows_control_of_the_domain() -> None:
    address = "0xabc123"
    url = "https://ornek-sigorta.example" + kyb.WELL_KNOWN
    assert kyb.check_domain("ornek-sigorta.example", address,
                            fetch=internet({url: (200, b"clause-insurer=0xABC123\n")}))["ok"]
    assert kyb.check_domain("https://ornek-sigorta.example/", address,
                            fetch=internet({url: (200, b"0xabc123")}))["ok"]
    missing = kyb.check_domain("ornek-sigorta.example", address, fetch=internet({}))
    assert not missing["ok"] and "not there yet" in missing["summary"]
    wrong = kyb.check_domain("ornek-sigorta.example", address,
                             fetch=internet({url: (200, b"clause-insurer=0xsomeoneelse")}))
    assert not wrong["ok"]
    assert not kyb.check_domain("not a domain", address, fetch=internet({}))["ok"]
    assert not kyb.check_domain("ornek-sigorta.example", None, fetch=internet({}))["ok"]


def test_every_country_gets_a_register_to_check_and_the_uk_gets_its_query() -> None:
    gb = kyb.register_links("GB", reference="123456")
    assert any("register.fca.org.uk" in l["url"] and "123456" in l["url"] for l in gb)
    tr = kyb.register_links("TR")
    assert any("seddk.gov.tr" in l["url"] for l in tr)
    de = kyb.register_links("DE", lei="5493001KJTIIGC8Y1R12")
    assert any("eiopa" in l["url"] for l in de) and any("gleif" in l["url"] for l in de)
    assert kyb.register_links("ZZ")     # somewhere to start, always


def test_evidence_is_kept_by_hash_and_only_documents_are_accepted(tmp_path) -> None:
    pdf = base64.b64encode(b"%PDF-1.4 specimen").decode()
    kept = kyb.store_evidence(tmp_path, "co", [
        {"kind": "licence_certificate", "filename": "licence.pdf", "content_type": "application/pdf", "data": pdf}])
    assert kept[0]["sha256"] and (tmp_path / "evidence" / "co" / "0.pdf").read_bytes().startswith(b"%PDF")
    for bad in (
        {"content_type": "text/html", "data": pdf},
        {"content_type": "application/pdf", "data": base64.b64encode(b"<html>").decode()},
        {"content_type": "application/pdf", "data": "not base64!!"},
    ):
        try:
            kyb.store_evidence(tmp_path, "co", [bad])
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_a_registration_is_checked_and_the_reviewer_sees_what_was_found(monkeypatch, tmp_path) -> None:
    lei = "5493001KJTIIGC8Y1R12"
    pages = {kyb.GLEIF + lei: (200, gleif("Specimen Carrier D", country="JP"))}
    monkeypatch.setattr(kyb, "_get", internet(pages))
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(operator_token=TOKEN), store_path=tmp_path / "book.sqlite")
    with TestClient(app) as client:
        body = registration()
        body["lei"] = lei
        body["domain"] = "specimen-d.example"
        body["evidence"] = [{"kind": "licence_certificate", "filename": "licence.pdf",
                             "content_type": "application/pdf",
                             "data": base64.b64encode(b"%PDF-1.4 specimen licence").decode()}]
        reply = client.post("/api/carriers", json=body)
        assert reply.status_code == 200, reply.text
        carrier_id = reply.json()["carrier"]["carrier_id"]
        assert reply.json()["proof_file"]["url"].endswith(kyb.WELL_KNOWN)

        auth = {"authorization": f"Bearer {sign_in(client)}"}
        for _ in range(50):
            row = next(c for c in client.get("/api/operator/carriers", headers=auth).json()["companies"]
                       if c["carrier_id"] == carrier_id)
            if row.get("verification"):
                break
            time.sleep(0.05)
        v = row["verification"]
        assert v["lei"]["ok"] and v["lei"]["legal_name"] == "Specimen Carrier D"
        # Not signed by an address (the site always signs), so the domain
        # proof has nothing to compare with, and says so.
        assert not v["domain"]["ok"] and "not signed" in v["domain"]["summary"]
        assert any("fsa.go.jp" in l["url"] for l in v["registers"])
        assert row["evidence"][0]["kind"] == "licence_certificate" and "stored" not in row["evidence"][0]

        # The reviewer opens the document, a stranger cannot.
        doc = client.get(f"/api/carriers/{carrier_id}/evidence/0", headers=auth)
        assert doc.status_code == 200 and doc.content.startswith(b"%PDF")
        assert client.get(f"/api/carriers/{carrier_id}/evidence/0").status_code == 401

        # The company puts its proof file up and asks for the checks again.
        pages["https://specimen-d.example" + kyb.WELL_KNOWN] = (200, b"clause-insurer=0xnobody")
        assert client.post(f"/api/carriers/{carrier_id}/verify", headers=auth).status_code == 429
        # The public list shows the LEI and nothing of the checks.
        public = next(c for c in client.get("/api/carriers").json()["companies"] if c["carrier_id"] == carrier_id)
        assert public["lei"] == lei and "verification" not in public and "evidence" not in public

        # Activation records what the reviewer confirmed.
        done = client.post(f"/api/carriers/{carrier_id}/activate", headers=auth,
                           json={"note": "FSA list checked", "checked": ["licence", "lei"]}).json()["carrier"]
        assert "[confirmed: lei, licence]" in done["reviews"][-1]["note"]
