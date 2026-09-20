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
_MASK = (1 << 64) - 1
_ROTC = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
         [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
# rho and pi in one pass, chi in one pass: the lane indices worked out once,
# so the permutation is straight line code rather than nested loops. Twice
# as fast as the loops, which matters when a book of ten thousand policies
# is hashed into a tree.
_PI = [(x + 5 * y, y + 5 * ((2 * x + 3 * y) % 5), _ROTC[x][y]) for x in range(5) for y in range(5)]
_CHI = [(i, (i % 5 + 1) % 5 + 5 * (i // 5), (i % 5 + 2) % 5 + 5 * (i // 5)) for i in range(25)]


def _keccak_f(s: list[int]) -> None:
    M = _MASK
    for rc in _RC:
        c0 = s[0] ^ s[5] ^ s[10] ^ s[15] ^ s[20]
        c1 = s[1] ^ s[6] ^ s[11] ^ s[16] ^ s[21]
        c2 = s[2] ^ s[7] ^ s[12] ^ s[17] ^ s[22]
        c3 = s[3] ^ s[8] ^ s[13] ^ s[18] ^ s[23]
        c4 = s[4] ^ s[9] ^ s[14] ^ s[19] ^ s[24]
        d0 = c4 ^ (((c1 << 1) | (c1 >> 63)) & M)
        d1 = c0 ^ (((c2 << 1) | (c2 >> 63)) & M)
        d2 = c1 ^ (((c3 << 1) | (c3 >> 63)) & M)
        d3 = c2 ^ (((c4 << 1) | (c4 >> 63)) & M)
        d4 = c3 ^ (((c0 << 1) | (c0 >> 63)) & M)
        for i in range(0, 25, 5):
            s[i] ^= d0
            s[i + 1] ^= d1
            s[i + 2] ^= d2
            s[i + 3] ^= d3
            s[i + 4] ^= d4
        b = [0] * 25
        for src, dst, r in _PI:
            v = s[src]
            b[dst] = ((v << r) | (v >> (64 - r))) & M if r else v
        for i, j, k in _CHI:
            s[i] = b[i] ^ ((~b[j]) & b[k])
        s[0] ^= rc


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
