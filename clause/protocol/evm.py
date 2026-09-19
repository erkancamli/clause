"""Just enough of Ethereum to check a wallet's signature over a message.

A person links a MetaMask style wallet by signing a short text with it
(``personal_sign``). Checking that signature needs two things Ethereum does
its own way: Keccak-256, which is not the SHA-3 in hashlib (the padding
differs), and recovery of the signing public key from a secp256k1 signature,
which the cryptography package does not offer. Both are small, both are
here, and both are pure Python: a few hundred signatures a day is nothing.

Nothing here signs. The protocol never holds a wallet's key.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Keccak-256
# ---------------------------------------------------------------------------

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [
    [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56], [27, 20, 39, 8, 14],
]
_MASK = (1 << 64) - 1


def _rol(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _MASK if n else x


def _keccak_f(state: list[int]) -> None:
    for rc in _RC:
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= d[x]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(state[x + 5 * y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y])
        state[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate:
        padded.append(0)
    padded[-1] |= 0x80
    state = [0] * 25
    for offset in range(0, len(padded), rate):
        block = padded[offset:offset + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _keccak_f(state)
    out = b"".join(s.to_bytes(8, "little") for s in state[:4])
    return out[:32]


# ---------------------------------------------------------------------------
# secp256k1 recovery
# ---------------------------------------------------------------------------

_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
      0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _add(a: tuple[int, int] | None, b: tuple[int, int] | None) -> tuple[int, int] | None:
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0]:
        if (a[1] + b[1]) % _P == 0:
            return None
        lam = (3 * a[0] * a[0]) * pow(2 * a[1], -1, _P) % _P
    else:
        lam = (b[1] - a[1]) * pow(b[0] - a[0], -1, _P) % _P
    x = (lam * lam - a[0] - b[0]) % _P
    return x, (lam * (a[0] - x) - a[1]) % _P


def _mul(k: int, point: tuple[int, int]) -> tuple[int, int] | None:
    out: tuple[int, int] | None = None
    while k:
        if k & 1:
            out = _add(out, point)
        point = _add(point, point)  # type: ignore[assignment]
        k >>= 1
    return out


def recover(digest: bytes, signature: bytes) -> bytes | None:
    """The uncompressed public key (64 bytes, no prefix) that signed this
    32 byte digest, from a 65 byte r||s||v signature; None if it is not one."""
    if len(digest) != 32 or len(signature) != 65:
        return None
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:64], "big")
    v = signature[64]
    if v >= 27:
        v -= 27
    if v not in (0, 1) or not (0 < r < _N and 0 < s < _N):
        return None
    x = r
    alpha = (pow(x, 3, _P) + 7) % _P
    y = pow(alpha, (_P + 1) // 4, _P)
    if y * y % _P != alpha:
        return None
    if (y & 1) != v:
        y = _P - y
    e = int.from_bytes(digest, "big") % _N
    r_inv = pow(r, -1, _N)
    point = _add(_mul(s * r_inv % _N, (x, y)), _mul((-e * r_inv) % _N, _G))
    if point is None:
        return None
    return point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big")


def personal_digest(message: bytes) -> bytes:
    """What ``personal_sign`` actually signs: the message behind the EIP-191
    prefix, hashed."""
    return keccak256(b"\x19Ethereum Signed Message:\n" + str(len(message)).encode() + message)


def address_of(public_key: bytes) -> str:
    return "0x" + keccak256(public_key)[-20:].hex()


def signer_of(message: bytes, signature_hex: str) -> str | None:
    """The address that signed this message with ``personal_sign``, or None."""
    text = signature_hex[2:] if signature_hex.startswith("0x") else signature_hex
    try:
        signature = bytes.fromhex(text)
    except ValueError:
        return None
    key = recover(personal_digest(message), signature)
    return address_of(key) if key else None
