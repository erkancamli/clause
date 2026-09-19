"""Addresses, in the shape Rialo shows them.

A Rialo account is a 32 byte public key shown in base58, the way the
playground shows its custodial keypair (HddrYho…pCJV). This protocol's own
addresses are derived from a device key rather than being that key, but they
are shown in the same shape so that an address here reads like one there:
32 bytes, base58, 43 or 44 characters. Addresses written earlier in the
0x form are still recognised, so nothing already on a book stops working.
"""

from __future__ import annotations

import hashlib

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = ALPHABET[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * pad + out


def b58decode(text: str) -> bytes:
    number = 0
    for ch in text:
        index = ALPHABET.find(ch)
        if index < 0:
            raise ValueError("not base58")
        number = number * 58 + index
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + raw


def from_material(material: bytes) -> str:
    """The address for some key material: 32 bytes of blake2b, in base58."""
    return b58encode(hashlib.blake2b(material, digest_size=32).digest())


def is_address(value: object) -> bool:
    """A base58 32 byte address, or the older 0x form."""
    if not isinstance(value, str):
        return False
    if len(value) == 42 and value.startswith("0x"):
        return all(c in "0123456789abcdefABCDEF" for c in value[2:])
    if 32 <= len(value) <= 44:
        try:
            return len(b58decode(value)) == 32
        except ValueError:
            return False
    return False


def canonical(value: str) -> str:
    """The form an address is keyed by: hex lower cased, base58 as it is."""
    return value.lower() if value.startswith("0x") else value
