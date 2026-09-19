"""What else an account is known by: wallets on other chains, and an X account.

An account here is a key on a device, joined through Privy to an e-mail or a
passkey. That is enough to buy cover. It is not enough to say "the Solana
wallet I pay from is mine" or "this is me on X", and both are useful: a
deposit from a linked wallet is matched without a memo, a payout to it needs
no second look, and a company's profile with its X account on it is easier
to trust than a bare address.

A wallet is linked by proving it, not by naming it. The person signs a short
text with the wallet itself (Phantom's ``signMessage``, MetaMask's
``personal_sign``) and, separately, the device key signs the request, so the
link is between an account somebody holds and a wallet somebody holds, both
proved at the same moment. The text names the account, the wallet and a
nonce that lives five minutes, so a signature captured here cannot link the
wallet to another account later. A Rialo address is the one exception:
until Rialo wallets can sign a message in a browser it is written down as
stated, and shown as such.

An X account is linked through Privy, which runs the OAuth dance, and proved
by Privy's identity token: a signed statement of the accounts Privy has
verified for this user, checked here against the same keys as a sign in.
The protocol keeps the handle and Privy's subject for it, nothing else.
"""

from __future__ import annotations

import base64
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from .payouts import clean_evm_address, clean_rialo_address, mask_rialo

KINDS = ("rialo", "solana", "evm", "x")
MAX_PER_ACCOUNT = 8
NONCE_SECONDS = 300.0


class LinkError(ValueError):
    """A link this module refuses. Safe to show."""


@dataclass(slots=True)
class Link:
    link_id: str
    account: str
    kind: str
    address: str                # the wallet address, or the X handle
    verified: bool
    proof: str                  # signature | stated | privy
    created_at: float
    subject: str = ""           # Privy's subject for an X account

    def to_dict(self) -> dict[str, Any]:
        return {"link_id": self.link_id, "kind": self.kind, "address": self.address,
                "short": mask_rialo(self.address) if self.kind != "x" else "@" + self.address,
                "verified": self.verified, "proof": self.proof, "created_at": self.created_at}


def link_text(account: str, kind: str, address: str, nonce: str) -> str:
    """What the wallet signs. Plain words, so a wallet shows the person
    exactly what they are agreeing to."""
    return (f"Clause (clause.insure)\n\nLink this {kind} wallet to my account.\n\n"
            f"Wallet: {address}\nAccount: {account}\nNonce: {nonce}\n\n"
            "This signature moves no funds and costs nothing.")


def _b58decode(text: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for ch in text:
        number = number * 58 + alphabet.index(ch)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + raw


def _signature_bytes(value: str) -> bytes:
    text = str(value or "").strip()
    try:
        if all(ch in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for ch in text) and len(text) > 60:
            return _b58decode(text)
        return base64.b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, IndexError) as error:
        raise LinkError("that is not a signature") from error


def verify_solana(message: str, address: str, signature: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        key = Ed25519PublicKey.from_public_bytes(_b58decode(address))
        key.verify(_signature_bytes(signature), message.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_evm(message: str, address: str, signature: str) -> bool:
    from .evm import signer_of

    signer = signer_of(message.encode("utf-8"), str(signature or ""))
    return signer is not None and signer.lower() == address.lower()


class Links:
    def __init__(self) -> None:
        self.links: dict[str, Link] = {}
        self.lock = threading.RLock()
        self._pending: dict[str, tuple[str, str, str, float]] = {}   # nonce -> account, kind, address, expires

    # -- wallets -----------------------------------------------------------

    def _clean(self, kind: str, address: str) -> str:
        if kind in ("rialo", "solana"):
            return clean_rialo_address(address)
        if kind == "evm":
            return clean_evm_address(address).lower()
        raise LinkError("a Rialo, Solana or Ethereum wallet")

    def start(self, account: str, kind: str, address: str, *, now: float | None = None) -> dict[str, Any]:
        """The text to sign with the wallet, and the nonce that binds it."""
        if kind not in ("solana", "evm"):
            raise LinkError("a Solana or Ethereum wallet signs; a Rialo address is written down")
        address = self._clean(kind, address)
        now = time.time() if now is None else now
        with self.lock:
            self._prune(now)
            if len(self._pending) > 2048:
                raise LinkError("too many links waiting; try again in a minute")
            nonce = secrets.token_urlsafe(18)
            self._pending[nonce] = (account, kind, address, now + NONCE_SECONDS)
        return {"nonce": nonce, "message": link_text(account, kind, address, nonce), "expires_at": now + NONCE_SECONDS}

    def _prune(self, now: float) -> None:
        for nonce in [n for n, p in self._pending.items() if p[3] < now]:
            self._pending.pop(nonce, None)

    def add(self, account: str, kind: str, address: str, *, nonce: str = "", signature: str = "",
            now: float | None = None) -> Link:
        """Link a wallet: with its signature over the text from start() for
        Solana and Ethereum, as stated for Rialo."""
        now = time.time() if now is None else now
        address = self._clean(kind, address)
        verified, proof = False, "stated"
        if kind in ("solana", "evm"):
            with self.lock:
                self._prune(now)
                pending = self._pending.pop(nonce, None)
            if pending is None or pending[0] != account or pending[1] != kind or pending[2] != address:
                raise LinkError("ask for the text to sign first; it lasts five minutes")
            message = link_text(account, kind, address, nonce)
            ok = verify_solana(message, address, signature) if kind == "solana" else verify_evm(message, address, signature)
            if not ok:
                raise LinkError("the wallet's signature does not verify for that address")
            verified, proof = True, "signature"
        with self.lock:
            mine = [l for l in self.links.values() if l.account == account]
            if len(mine) >= MAX_PER_ACCOUNT:
                raise LinkError(f"at most {MAX_PER_ACCOUNT} links on one account; remove one")
            for other in self.links.values():
                if other.kind == kind and other.address == address:
                    if other.account == account:
                        if verified and not other.verified:
                            other.verified, other.proof, other.created_at = True, proof, now
                        return other
                    raise LinkError("that wallet is already linked to another account")
            link = Link(link_id="LNK-" + secrets.token_hex(4).upper(), account=account, kind=kind,
                        address=address, verified=verified, proof=proof, created_at=now)
            self.links[link.link_id] = link
        return link

    # -- X -----------------------------------------------------------------

    def add_x(self, account: str, username: str, subject: str, *, now: float | None = None) -> Link:
        now = time.time() if now is None else now
        handle = str(username or "").strip().lstrip("@")
        if not (1 <= len(handle) <= 15) or not all(ch.isalnum() or ch == "_" for ch in handle):
            raise LinkError("that is not an X handle")
        with self.lock:
            for other in list(self.links.values()):
                if other.kind == "x" and other.subject == subject and other.account != account:
                    raise LinkError("that X account is already linked to another account")
                if other.kind == "x" and other.account == account:
                    other.address, other.subject, other.created_at = handle, subject, now
                    return other
            link = Link(link_id="LNK-" + secrets.token_hex(4).upper(), account=account, kind="x",
                        address=handle, verified=True, proof="privy", created_at=now, subject=subject)
            self.links[link.link_id] = link
        return link

    # -- reading and removing ----------------------------------------------

    def mine(self, account: str) -> list[Link]:
        return sorted((l for l in self.links.values() if l.account == account), key=lambda l: l.created_at)

    def wallets_of(self, account: str, kind: str) -> list[str]:
        return [l.address for l in self.links.values() if l.account == account and l.kind == kind]

    def account_of(self, kind: str, address: str) -> str | None:
        """Which account a wallet belongs to, for matching a deposit."""
        wanted = address.lower() if kind == "evm" else address
        for link in self.links.values():
            if link.kind == kind and link.address == wanted:
                return link.account
        return None

    def remove(self, account: str, link_id: str) -> Link:
        with self.lock:
            link = self.links.get(link_id)
            if link is None or link.account != account:
                raise LinkError("no such link")
            del self.links[link_id]
        return link

    def public(self, account: str) -> dict[str, Any]:
        """What anyone may see of an account's links: the X handle, and that
        wallets are linked, never which."""
        mine = self.mine(account)
        x = next((l.address for l in mine if l.kind == "x"), None)
        return {"x": x, "wallets": sum(1 for l in mine if l.kind != "x" and l.verified)}
