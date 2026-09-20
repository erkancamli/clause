"""Documents an applicant hands the company that will decide, and nobody else.

A home or a vehicle is applied for with its address, and the company that
issues the policy confirms it is the applicant's: a title deed, a lease, a
vehicle registration. Those papers name people, addresses and money, and a
protocol that stored them in the open would be a place to steal them from.

So they never reach the protocol in the open. The applicant's browser
encrypts each document to the one party that will decide the application,
and the protocol keeps the ciphertext, which it cannot read, and a record of
what was sent and who opened it, which it can. The key that opens a document
sits in the deciding party's browser, was never exported, and was never
here. Consent is the act of sending: a document is readable by the company
the applicant chose, and by no one else, including the operator of this
service and anyone who takes the database.

The envelope, so another page or a script can make or open one:

    recipient   the deciding party's reading key: an uncompressed P-256
                point, 65 bytes, base64url, registered by that party's own
                browser (a company's account, or the operator's session)
    ephemeral   a fresh P-256 key pair per document; the public point is
                sent, the private half is thrown away
    secret      ECDH(ephemeral private, recipient) -> 32 bytes
    key         HKDF-SHA256(secret, salt = 16 random bytes,
                            info = "clause application document v1") -> 32 bytes
    ciphertext  AES-256-GCM(key, iv = 12 random bytes,
                            additional data = the application id, UTF-8)

The application id in the additional data ties a ciphertext to the
application it was sent for; moved to another one, it will not open.

When the application is decided, withdrawn or lapses, the ciphertext is
deleted: the company has seen what it needed, and a document nobody can
decide on any more has no reason to stay. The record of what was sent and
who opened it stays, as the rest of the decision does.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec

MAX_PER_APPLICATION = 4
MAX_CIPHERTEXT_BYTES = 4_000_000
TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
INFO = b"clause application document v1"
OPERATOR = "operator"


class DocumentError(ValueError):
    """A document or a key this module refuses. Safe to show."""


def _b64url_decode(text: str, *, name: str, length: int | None = None) -> bytes:
    text = str(text)
    try:
        raw = base64.b64decode(text.replace("-", "+").replace("_", "/") + "=" * (-len(text) % 4),
                               validate=True)
    except (ValueError, TypeError) as error:
        raise DocumentError(f"{name} is not base64url") from error
    if length is not None and len(raw) != length:
        raise DocumentError(f"{name} is {length} bytes, not {len(raw)}")
    return raw


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def check_reading_key(public_key: str) -> str:
    """A P-256 point that is actually on the curve, returned canonically."""
    raw = _b64url_decode(public_key, name="the reading key", length=65)
    if raw[0] != 4:
        raise DocumentError("the reading key is an uncompressed P-256 point")
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
    except ValueError as error:
        raise DocumentError("the reading key is not a point on P-256") from error
    return _b64url(raw)


def key_fingerprint(public_key: str) -> str:
    return hashlib.sha256(_b64url_decode(public_key, name="the reading key")).hexdigest()[:16]


@dataclass(slots=True)
class Document:
    doc_id: str
    app_id: str
    holder: str
    filename: str
    content_type: str
    bytes: int                      # of the document itself, as the page said
    ciphertext_bytes: int
    sha256: str                     # of the ciphertext, the thing actually held
    ephemeral: str
    salt: str
    iv: str
    recipient: str                  # "company" or "operator"
    recipient_key: str              # fingerprint of the reading key it was sealed to
    uploaded_at: float
    stored: str = ""                # path under the state directory, until purged
    opened: list[dict[str, Any]] = field(default_factory=list)
    purged_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id, "app_id": self.app_id, "filename": self.filename,
            "content_type": self.content_type, "bytes": self.bytes,
            "recipient": self.recipient, "recipient_key": self.recipient_key,
            "sha256": self.sha256, "uploaded_at": self.uploaded_at,
            "opened": [dict(o) for o in self.opened],
            "available": bool(self.stored) and self.purged_at is None,
            "purged_at": self.purged_at,
        }

    def envelope(self, ciphertext: bytes) -> dict[str, Any]:
        return {**self.to_dict(), "ephemeral": self.ephemeral, "salt": self.salt, "iv": self.iv,
                "info": INFO.decode("ascii"), "additional_data": self.app_id,
                "data": _b64url(ciphertext)}


class Documents:
    """The reading keys and the sealed documents, with their bytes on disk."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else None
        self.keys: dict[str, str] = {}          # address (or "operator") -> reading key
        self.records: dict[str, Document] = {}
        self._blobs: dict[str, bytes] = {}      # without a state directory (tests)
        self.lock = threading.RLock()

    # -- keys ---------------------------------------------------------------

    def register_key(self, address: str, public_key: str) -> str:
        key = check_reading_key(public_key)
        with self.lock:
            self.keys[address] = key
        return key

    def key_of(self, address: str | None) -> str | None:
        return self.keys.get(address or "")

    def recipient_for(self, carrier: Any) -> tuple[str, str] | None:
        """(kind, reading key) of whoever will decide for this company.

        The company's own account when it registered a reading key; the
        operator, who decides for a stand in, when that one did; otherwise
        nobody, and the applicant is told the company will ask by other means.
        """
        if carrier is None:
            return None
        own = self.key_of(getattr(carrier, "address", None))
        if own:
            return "company", own
        if getattr(carrier, "specimen", False):
            operator = self.key_of(OPERATOR)
            if operator:
                return "operator", operator
        return None

    # -- documents ------------------------------------------------------------

    def for_application(self, app_id: str) -> list[Document]:
        return sorted((d for d in self.records.values() if d.app_id == app_id),
                      key=lambda d: d.uploaded_at)

    def add(self, *, app_id: str, holder: str, items: list[dict[str, Any]],
            recipient: str, recipient_key: str) -> list[Document]:
        if not items:
            raise DocumentError("send at least one document")
        with self.lock:
            have = len(self.for_application(app_id))
            if have + len(items) > MAX_PER_APPLICATION:
                raise DocumentError(f"at most {MAX_PER_APPLICATION} documents for one application")
            out = []
            for item in items:
                content_type = str(item.get("content_type", ""))
                ext = TYPES.get(content_type)
                if ext is None:
                    raise DocumentError("a document is a PDF, PNG or JPEG")
                data = _b64url_decode(item.get("data", ""), name="the document")
                if not data or len(data) > MAX_CIPHERTEXT_BYTES:
                    raise DocumentError(f"each document is at most {MAX_CIPHERTEXT_BYTES // 1_000_000} MB")
                ephemeral = check_reading_key(str(item.get("ephemeral", "")))
                salt = _b64url(_b64url_decode(item.get("salt", ""), name="the salt", length=16))
                iv = _b64url(_b64url_decode(item.get("iv", ""), name="the iv", length=12))
                declared = int(item.get("bytes", 0) or 0)
                if not 0 < declared <= len(data):
                    raise DocumentError("the document's size does not fit its ciphertext")
                doc = Document(
                    doc_id="DOC-" + secrets.token_hex(6).upper(), app_id=app_id, holder=holder,
                    filename=str(item.get("filename", ""))[:120] or f"document{ext}",
                    content_type=content_type, bytes=declared, ciphertext_bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(), ephemeral=ephemeral, salt=salt, iv=iv,
                    recipient=recipient, recipient_key=key_fingerprint(recipient_key),
                    uploaded_at=time.time())
                self._keep(doc, data)
                self.records[doc.doc_id] = doc
                out.append(doc)
            return out

    def _keep(self, doc: Document, data: bytes) -> None:
        if self.root is None:
            self._blobs[doc.doc_id] = data
            doc.stored = f"memory:{doc.doc_id}"
            return
        folder = self.root / "documents" / doc.app_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{doc.doc_id}.bin"
        path.write_bytes(data)
        doc.stored = str(path.relative_to(self.root))

    def ciphertext(self, doc: Document) -> bytes:
        if not doc.stored or doc.purged_at is not None:
            raise DocumentError("that document is no longer held; the application was decided")
        if doc.stored.startswith("memory:"):
            data = self._blobs.get(doc.doc_id)
        else:
            path = (self.root or Path(".")) / doc.stored
            data = path.read_bytes() if path.exists() else None
        if data is None:
            raise DocumentError("that document's bytes are missing from the state directory")
        return data

    def require(self, app_id: str, doc_id: str) -> Document:
        doc = self.records.get(doc_id)
        if doc is None or doc.app_id != app_id:
            raise DocumentError("no such document on that application")
        return doc

    def mark_opened(self, doc: Document, by: str, now: float | None = None) -> None:
        with self.lock:
            doc.opened.append({"by": by[:80], "at": time.time() if now is None else now})
            del doc.opened[:-20]

    def remove(self, doc: Document) -> None:
        with self.lock:
            self._drop(doc)
            self.records.pop(doc.doc_id, None)

    def purge(self, app_id: str, now: float | None = None) -> int:
        """Delete the ciphertext of every document on an application; keep the record."""
        count = 0
        with self.lock:
            for doc in self.for_application(app_id):
                if doc.purged_at is None:
                    self._drop(doc)
                    doc.purged_at = time.time() if now is None else now
                    count += 1
        return count

    def _drop(self, doc: Document) -> None:
        if doc.stored.startswith("memory:"):
            self._blobs.pop(doc.doc_id, None)
        elif doc.stored and self.root is not None:
            path = self.root / doc.stored
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        doc.stored = ""
