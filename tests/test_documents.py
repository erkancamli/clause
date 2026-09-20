"""Documents for the company's checks: sealed in the applicant's browser,
opened only by the party that decides, and gone once it has decided.

The page does the sealing with WebCrypto; this file does the same thing
with the cryptography library, both as the applicant and as the company, so
the envelope written in clause.protocol.documents is shown to open with the
key it names and with no other.
"""

from __future__ import annotations

import base64
import hashlib
import os

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol.documents import INFO, Documents, DocumentError
from clause.store import Store
from test_api_security import Device, session_for
from test_applications import HOME, apply, applicant

TOKEN = "operator-token-for-tests"
OP = {"x-operator-token": TOKEN}


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Reader:
    """A browser's reading key: made there, never exported."""

    def __init__(self) -> None:
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.public = b64u(self.private.public_key().public_bytes(
            __import__("cryptography").hazmat.primitives.serialization.Encoding.X962,
            __import__("cryptography").hazmat.primitives.serialization.PublicFormat.UncompressedPoint))

    def open(self, envelope: dict) -> bytes:
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64u(envelope["ephemeral"]))
        secret = self.private.exchange(ec.ECDH(), peer)
        key = HKDF(hashes.SHA256(), 32, unb64u(envelope["salt"]), INFO).derive(secret)
        return AESGCM(key).decrypt(unb64u(envelope["iv"]), unb64u(envelope["data"]),
                                   envelope["additional_data"].encode())


def seal(recipient_key: str, app_id: str, data: bytes, *, filename: str, content_type: str) -> dict:
    """What the applicant's page does with each file, step for step."""
    from cryptography.hazmat.primitives import serialization
    ephemeral = ec.generate_private_key(ec.SECP256R1())
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64u(recipient_key))
    secret = ephemeral.exchange(ec.ECDH(), peer)
    salt, iv = os.urandom(16), os.urandom(12)
    key = HKDF(hashes.SHA256(), 32, salt, INFO).derive(secret)
    sealed = AESGCM(key).encrypt(iv, data, app_id.encode())
    point = ephemeral.public_key().public_bytes(serialization.Encoding.X962,
                                                serialization.PublicFormat.UncompressedPoint)
    return {"filename": filename, "content_type": content_type, "bytes": len(data),
            "ephemeral": b64u(point), "salt": b64u(salt), "iv": b64u(iv), "data": b64u(sealed)}


DEED = b"%PDF-1.4 a title deed, in the name of the applicant " * 40


@pytest.fixture
def client(tmp_path):
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, specimens=True))
    with TestClient(app) as c:
        yield c


def bearer(client, device, address) -> dict:
    return {"authorization": f"Bearer {session_for(client, device, address)}"}


def pending_application(client):
    device, address = applicant(client)
    quote = client.post("/api/quote", json={"peril": "earthquake",
        "subject": {"location": "IST-KADIKOY", "radius_km": 50}, "limit": 50_000, "term_days": 365}).json()
    made = apply(client, device, address, quote_id=quote["lock"]["id"], max_premium=quote["lock"]["premium"])
    assert made.status_code == 200, made.text
    return device, address, made.json()["application"]


def operator_session(client) -> dict:
    token = client.post("/api/operator/session", json={"reviewer": "Ayşe"}, headers=OP).json()["token"]
    return {"authorization": f"Bearer {token}"}


def test_a_document_is_sealed_to_the_operator_who_decides_for_a_stand_in(client) -> None:
    device, address, app = pending_application(client)
    # Nobody to seal to yet: the stand in has no desk holder and the operator no key.
    who = client.get("/api/applications/recipient", params={"carrier_id": app["carrier_id"]}).json()
    assert who["recipient"] is None and who["reading_key"] is None
    refused = client.post(f"/api/applications/{app['app_id']}/documents", headers=bearer(client, device, address),
                          json={"documents": [seal(Reader().public, app["app_id"], DEED, filename="deed.pdf",
                                                    content_type="application/pdf")]})
    assert refused.status_code == 409 and "reading key" in refused.text

    reader = Reader()
    op = operator_session(client)
    assert client.post("/api/operator/reading-key", json={"public_key": reader.public}, headers=op).status_code == 200
    who = client.get("/api/applications/recipient", params={"carrier_id": app["carrier_id"]}).json()
    assert who["recipient"] == "operator" and who["reading_key"] == reader.public

    sent = client.post(f"/api/applications/{app['app_id']}/documents", headers=bearer(client, device, address),
                       json={"documents": [
                           seal(who["reading_key"], app["app_id"], DEED, filename="deed.pdf", content_type="application/pdf"),
                           seal(who["reading_key"], app["app_id"], b"\x89PNG fake", filename="id.png", content_type="image/png"),
                       ]})
    assert sent.status_code == 200, sent.text
    docs = sent.json()["documents"]
    assert [d["filename"] for d in docs] == ["deed.pdf", "id.png"]
    assert all(d["recipient"] == "operator" and d["available"] and d["opened"] == [] for d in docs)
    # The protocol holds ciphertext: the deed is not in the state directory in the open.
    root = client.app.state.documents.root
    stored = [p for p in (root / "documents" / app["app_id"]).iterdir()] if root else []
    assert all(b"title deed" not in p.read_bytes() for p in stored)

    # The applicant sees what was sent, and that nobody has opened it.
    mine = client.get("/api/applications", headers=bearer(client, device, address)).json()["applications"][0]
    assert [d["filename"] for d in mine["documents"]] == ["deed.pdf", "id.png"]
    # A stranger cannot open it; the applicant's own session cannot either.
    stranger = Device()
    other = client.post("/api/auth/register", json={"public_key": stranger.public}).json()["address"]
    assert client.get(f"/api/applications/{app['app_id']}/documents/{docs[0]['doc_id']}",
                      headers=bearer(client, stranger, other)).status_code == 401
    assert client.get(f"/api/applications/{app['app_id']}/documents/{docs[0]['doc_id']}",
                      headers=bearer(client, device, address)).status_code == 401
    # The operator opens it in the browser that holds the key.
    envelope = client.get(f"/api/applications/{app['app_id']}/documents/{docs[0]['doc_id']}", headers=op)
    assert envelope.status_code == 200, envelope.text
    assert reader.open(envelope.json()) == DEED
    # And with another browser's key it does not open.
    with pytest.raises(Exception):
        Reader().open(envelope.json())
    # The opening is on the record the applicant sees.
    mine = client.get("/api/applications", headers=bearer(client, device, address)).json()["applications"][0]
    assert mine["documents"][0]["opened"][0]["by"] == "Ayşe"
    assert mine["documents"][1]["opened"] == []

    # Decided: the ciphertext goes, the record stays.
    decided = client.post(f"/api/review/applications/{app['app_id']}", headers=op,
                          json={"decision": "approve", "checked": app["checks"], "note": "deed seen"})
    assert decided.status_code == 200, decided.text
    after = decided.json()["application"]["documents"]
    assert all(not d["available"] and d["purged_at"] for d in after)
    assert client.get(f"/api/applications/{app['app_id']}/documents/{docs[0]['doc_id']}", headers=op).status_code == 410
    if root:
        assert not any((root / "documents" / app["app_id"]).iterdir())


def test_a_company_at_its_own_desk_reads_what_is_sealed_to_it(client) -> None:
    device, address, app = pending_application(client)
    # Someone takes the stand in's desk and registers a reading key: documents go to them, not the operator.
    reader = Reader()
    op = operator_session(client)
    client.post("/api/operator/reading-key", json={"public_key": Reader().public}, headers=op)
    desk_device = Device()
    desk = client.post("/api/auth/register", json={"public_key": desk_device.public}).json()["address"]
    auth = bearer(client, desk_device, desk)
    assert client.post("/api/company/specimen", json={"carrier_id": app["carrier_id"]}, headers=auth).status_code == 200
    assert client.post("/api/auth/reading-key", json={"public_key": reader.public}, headers=auth).status_code == 200
    who = client.get("/api/applications/recipient", params={"carrier_id": app["carrier_id"]}).json()
    assert who["recipient"] == "company" and who["reading_key"] == reader.public

    sent = client.post(f"/api/applications/{app['app_id']}/documents", headers=bearer(client, device, address),
                       json={"documents": [seal(reader.public, app["app_id"], DEED, filename="lease.pdf",
                                                 content_type="application/pdf")]})
    assert sent.status_code == 200, sent.text
    doc = sent.json()["documents"][0]
    listed = client.get("/api/review/applications", headers=auth).json()["applications"]
    assert listed[0]["documents"][0]["doc_id"] == doc["doc_id"]
    envelope = client.get(f"/api/applications/{app['app_id']}/documents/{doc['doc_id']}", headers=auth).json()
    assert reader.open(envelope) == DEED
    # The applicant can take it back while the application is open.
    gone = client.delete(f"/api/applications/{app['app_id']}/documents/{doc['doc_id']}",
                         headers=bearer(client, device, address))
    assert gone.status_code == 200 and gone.json()["application"]["documents"] == []
    assert client.get(f"/api/applications/{app['app_id']}/documents/{doc['doc_id']}", headers=auth).status_code == 404


def test_what_the_envelope_refuses() -> None:
    docs = Documents(None)
    with pytest.raises(DocumentError, match="65 bytes"):
        docs.register_key("a", b64u(b"\x04" + b"\x01" * 10))
    with pytest.raises(DocumentError, match="on P-256"):
        docs.register_key("a", b64u(b"\x04" + b"\x01" * 64))
    reader = Reader()
    docs.register_key("a", reader.public)
    good = seal(reader.public, "APP-1", DEED, filename="deed.pdf", content_type="application/pdf")
    for bad, why in (
        ({**good, "content_type": "text/plain"}, "PDF, PNG or JPEG"),
        ({**good, "salt": b64u(b"\x00" * 8)}, "16 bytes"),
        ({**good, "iv": b64u(b"\x00" * 16)}, "12 bytes"),
        ({**good, "bytes": len(DEED) * 3}, "does not fit"),
        ({**good, "data": "***"}, "base64url"),
    ):
        with pytest.raises(DocumentError, match=why):
            docs.add(app_id="APP-1", holder="h", items=[bad], recipient="company", recipient_key=reader.public)
    docs.add(app_id="APP-1", holder="h", items=[good] * 4, recipient="company", recipient_key=reader.public)
    with pytest.raises(DocumentError, match="at most 4"):
        docs.add(app_id="APP-1", holder="h", items=[good], recipient="company", recipient_key=reader.public)


def test_keys_and_records_survive_a_restart_and_the_bytes_stay_on_disk(tmp_path, monkeypatch) -> None:
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("CLAUSE_STATE_DIR", str(state))
    reader = Reader()
    settings = Settings(faucet=True, operator_token=TOKEN, specimens=True)
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True, settings=settings)
    with TestClient(app) as c:
        device, address, application = pending_application(c)
        op = operator_session(c)
        c.post("/api/operator/reading-key", json={"public_key": reader.public}, headers=op)
        sent = c.post(f"/api/applications/{application['app_id']}/documents", headers=bearer(c, device, address),
                      json={"documents": [seal(reader.public, application["app_id"], DEED, filename="deed.pdf",
                                                content_type="application/pdf")]})
        assert sent.status_code == 200, sent.text
        doc = sent.json()["documents"][0]
    # Leaving the client stops the keeper, which writes the book.
    store = Store(state / "clause.sqlite")
    assert store.docs("reading_key") == {"operator": reader.public}
    assert list(store.docs("document")) == [doc["doc_id"]]
    store.close()
    again = create_app(trials=400, seed=11, run_chain=False, seed_book=True, settings=settings)
    with TestClient(again) as c:
        who = c.get("/api/applications/recipient", params={"carrier_id": application["carrier_id"]}).json()
        assert who["reading_key"] == reader.public
        op = operator_session(c)
        envelope = c.get(f"/api/applications/{application['app_id']}/documents/{doc['doc_id']}", headers=op)
        assert envelope.status_code == 200, envelope.text
        assert reader.open(envelope.json()) == DEED
