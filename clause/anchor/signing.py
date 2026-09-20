"""Signing Ethereum transactions without a wallet library.

The protocol already carries Keccak-256 and secp256k1 point arithmetic to
check a linked wallet's signature (``clause.protocol.evm``). Signing is the
same arithmetic the other way round, with a deterministic nonce (RFC 6979)
so that the same transaction always produces the same signature and a
weak random source can never leak the key. On top of that sit the three
encodings a transaction needs: RLP for the transaction itself, the ABI
for the call it carries, and the two transaction shapes, the legacy one
(kept because the EIP-155 example is a test vector) and the EIP-1559 one
every transaction actually uses.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Sequence

from ..protocol.evm import _G, _N, _add, _mul, address_of, keccak256

# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


def private_key_of(text: str) -> int:
    """A 32 byte hex private key, with or without 0x, as an integer."""
    hex_ = text.strip()
    if hex_.startswith(("0x", "0X")):
        hex_ = hex_[2:]
    if len(hex_) != 64:
        raise ValueError("a private key is 32 bytes of hex")
    key = int(hex_, 16)
    if not 0 < key < _N:
        raise ValueError("the private key is out of range")
    return key


def public_key(private: int) -> bytes:
    point = _mul(private, _G)
    assert point is not None
    return point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big")


def address_of_key(private: int) -> str:
    return checksum(address_of(public_key(private)))


def checksum(address: str) -> str:
    """EIP-55 mixed case, so an explorer or a person can spot a typo."""
    plain = address.lower().replace("0x", "")
    digest = keccak256(plain.encode()).hex()
    return "0x" + "".join(c.upper() if int(digest[i], 16) >= 8 else c for i, c in enumerate(plain))


# ---------------------------------------------------------------------------
# ECDSA over secp256k1 with RFC 6979 nonces
# ---------------------------------------------------------------------------


def _rfc6979_k(private: int, digest: bytes) -> int:
    x = private.to_bytes(32, "big")
    h = (int.from_bytes(digest, "big") % _N).to_bytes(32, "big")
    v = b"\x01" * 32
    k = b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        candidate = int.from_bytes(v, "big")
        if 0 < candidate < _N:
            return candidate
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def sign_digest(digest: bytes, private: int) -> tuple[int, int, int]:
    """(r, s, recovery id) over a 32 byte digest, with the low s form that
    Ethereum requires."""
    if len(digest) != 32:
        raise ValueError("sign a 32 byte digest")
    e = int.from_bytes(digest, "big")
    while True:
        k = _rfc6979_k(private, digest)
        point = _mul(k, _G)
        assert point is not None
        r = point[0] % _N
        if r == 0:
            digest = keccak256(digest)  # practically unreachable
            continue
        s = pow(k, -1, _N) * (e + r * private) % _N
        if s == 0:
            digest = keccak256(digest)
            continue
        recovery = point[1] & 1
        if s > _N // 2:
            s = _N - s
            recovery ^= 1
        return r, s, recovery


# ---------------------------------------------------------------------------
# RLP
# ---------------------------------------------------------------------------


def _int_bytes(value: int) -> bytes:
    if value < 0:
        raise ValueError("RLP has no negative integers")
    return b"" if value == 0 else value.to_bytes((value.bit_length() + 7) // 8, "big")


def _length(prefix: int, n: int) -> bytes:
    if n < 56:
        return bytes([prefix + n])
    size = _int_bytes(n)
    return bytes([prefix + 55 + len(size)]) + size


def rlp(item: Any) -> bytes:
    if isinstance(item, int):
        item = _int_bytes(item)
    if isinstance(item, (bytes, bytearray)):
        item = bytes(item)
        if len(item) == 1 and item[0] < 0x80:
            return item
        return _length(0x80, len(item)) + item
    if isinstance(item, (list, tuple)):
        body = b"".join(rlp(i) for i in item)
        return _length(0xC0, len(body)) + body
    raise TypeError(f"cannot RLP encode {type(item).__name__}")


def rlp_decode(data: bytes) -> Any:
    """The inverse, enough to read a transaction back in a test."""
    item, rest = _decode_one(bytes(data))
    if rest:
        raise ValueError("trailing bytes")
    return item


def _decode_one(data: bytes) -> tuple[Any, bytes]:
    if not data:
        raise ValueError("empty")
    first = data[0]
    if first < 0x80:
        return data[:1], data[1:]
    if first < 0xB8:
        n = first - 0x80
        return data[1:1 + n], data[1 + n:]
    if first < 0xC0:
        size = first - 0xB7
        n = int.from_bytes(data[1:1 + size], "big")
        return data[1 + size:1 + size + n], data[1 + size + n:]
    if first < 0xF8:
        n = first - 0xC0
        body, rest = data[1:1 + n], data[1 + n:]
    else:
        size = first - 0xF7
        n = int.from_bytes(data[1:1 + size], "big")
        body, rest = data[1 + size:1 + size + n], data[1 + size + n:]
    items = []
    while body:
        item, body = _decode_one(body)
        items.append(item)
    return items, rest


# ---------------------------------------------------------------------------
# The ABI: the call a transaction carries
# ---------------------------------------------------------------------------


def selector(signature: str) -> bytes:
    return keccak256(signature.encode())[:4]


def _word(value: int) -> bytes:
    if not 0 <= value < (1 << 256):
        raise ValueError("does not fit in a word")
    return value.to_bytes(32, "big")


def to_bytes32(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        raw = value
    else:
        text = value[2:] if value.startswith(("0x", "0X")) else value
        raw = bytes.fromhex(text)
    if len(raw) != 32:
        raise ValueError("bytes32 is 32 bytes")
    return raw


def to_address(value: str) -> bytes:
    text = value[2:] if value.startswith(("0x", "0X")) else value
    raw = bytes.fromhex(text) if text else b""
    if len(raw) != 20:
        raise ValueError("an address is 20 bytes")
    return raw


def abi_encode(types: Sequence[str], values: Sequence[Any]) -> bytes:
    """Static and dynamic arguments, head and tail, as the ABI lays them out."""
    if len(types) != len(values):
        raise ValueError("types and values differ in length")
    heads: list[bytes] = []
    tails: list[bytes] = []
    head_size = 32 * len(types)
    for kind, value in zip(types, values):
        if kind in ("string", "bytes"):
            raw = value.encode() if isinstance(value, str) else bytes(value)
            padded = raw + b"\x00" * (-len(raw) % 32)
            heads.append(None)  # type: ignore[arg-type]
            tails.append(_word(len(raw)) + padded)
        elif kind == "bytes32[]":
            items = [to_bytes32(v) for v in value]
            heads.append(None)  # type: ignore[arg-type]
            tails.append(_word(len(items)) + b"".join(items))
        elif kind.startswith("uint"):
            heads.append(_word(int(value)))
            tails.append(b"")
        elif kind == "address":
            heads.append(b"\x00" * 12 + to_address(value))
            tails.append(b"")
        elif kind == "bytes32":
            heads.append(to_bytes32(value))
            tails.append(b"")
        elif kind == "bool":
            heads.append(_word(1 if value else 0))
            tails.append(b"")
        else:
            raise ValueError(f"unsupported ABI type {kind}")
    out = b""
    offset = head_size
    fixed: list[bytes] = []
    for head, tail in zip(heads, tails):
        if head is None:
            fixed.append(_word(offset))
            offset += len(tail)
        else:
            fixed.append(head)
    out = b"".join(fixed) + b"".join(tails)
    return out


def encode_call(signature: str, values: Sequence[Any]) -> bytes:
    """``mint(address,string,bytes32,bytes32)`` and its arguments, as calldata."""
    inside = signature[signature.index("(") + 1:signature.rindex(")")]
    types = [t.strip() for t in inside.split(",") if t.strip()]
    return selector(signature) + abi_encode(types, values)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def legacy_signing_hash(*, nonce: int, gas_price: int, gas: int, to: bytes, value: int,
                        data: bytes, chain_id: int) -> bytes:
    return keccak256(rlp([nonce, gas_price, gas, to, value, data, chain_id, 0, 0]))


def sign_legacy(private: int, *, nonce: int, gas_price: int, gas: int, to: bytes, value: int,
                data: bytes, chain_id: int) -> bytes:
    digest = legacy_signing_hash(nonce=nonce, gas_price=gas_price, gas=gas, to=to, value=value,
                                 data=data, chain_id=chain_id)
    r, s, recovery = sign_digest(digest, private)
    return rlp([nonce, gas_price, gas, to, value, data, chain_id * 2 + 35 + recovery, r, s])


def sign_1559(private: int, *, chain_id: int, nonce: int, max_priority_fee: int, max_fee: int,
              gas: int, to: bytes, value: int, data: bytes) -> bytes:
    """A type 2 transaction, signed: what ``eth_sendRawTransaction`` takes."""
    fields: list[Any] = [chain_id, nonce, max_priority_fee, max_fee, gas, to, value, data, []]
    digest = keccak256(b"\x02" + rlp(fields))
    r, s, recovery = sign_digest(digest, private)
    return b"\x02" + rlp(fields + [recovery, r, s])


def tx_hash(raw: bytes) -> str:
    return "0x" + keccak256(raw).hex()


def contract_address(sender: str, nonce: int) -> str:
    """Where a contract deployed by this sender at this nonce lands."""
    return checksum("0x" + keccak256(rlp([to_address(sender), nonce]))[-20:].hex())


def sender_of_1559(raw: bytes) -> str | None:
    """The signer of a raw type 2 transaction; a test's way to check one."""
    from ..protocol.evm import recover
    if not raw or raw[0] != 2:
        return None
    fields = rlp_decode(raw[1:])
    body, sig = fields[:9], fields[9:]
    digest = keccak256(b"\x02" + rlp(body))
    recovery = int.from_bytes(sig[0], "big") if sig[0] else 0
    r = int.from_bytes(sig[1], "big")
    s = int.from_bytes(sig[2], "big")
    key = recover(digest, r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([recovery]))
    return checksum(address_of(key)) if key else None
