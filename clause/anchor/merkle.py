"""A Merkle tree over the book, and the proof that one policy is in it.

Each policy is one leaf: the hash of its id, its holder, its status, its
limit, its dates and the hash of its terms, laid out exactly as the
contract's ``verify`` would see them (ABI encoded, then Keccak-256). Pairs
are hashed in sorted order, the OpenZeppelin convention, so a proof is a
bare list of sibling hashes with no left/right flags, and the same dozen
lines verify it in Solidity, in Python and in a browser.

Leaves are sorted before the tree is built, so the root depends on the
book and nothing else: two servers with the same book agree on the root.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..protocol.evm import keccak256
from .signing import abi_encode

STATUS_CODES = {"active": 1, "paid": 2, "lapsed": 3, "expired": 4, "cancelled": 5}
LEAF_TYPES = ("bytes32", "bytes32", "uint8", "uint256", "uint64", "uint64", "bytes32")


def text_hash(text: str) -> str:
    return "0x" + keccak256(text.encode()).hex()


def leaf_fields(policy: Any) -> dict[str, Any]:
    """What goes into a policy's leaf, in the clear, so a person can
    recompute it."""
    token = (policy.metadata or {}).get("token") or {}
    terms = token.get("terms_hash") or "0x" + "00" * 32
    status = policy.status.value if hasattr(policy.status, "value") else str(policy.status)
    return {
        "policy_id": policy.policy_id,
        "policy_hash": text_hash(policy.policy_id),
        "holder_hash": text_hash(policy.holder),
        "status": status,
        "status_code": STATUS_CODES.get(status, 0),
        "limit_cents": int(round(float(policy.limit) * 100)),
        "starts_at": int(policy.starts_at),
        "ends_at": int(policy.ends_at),
        "terms_hash": terms,
    }


def leaf_of(fields: dict[str, Any]) -> str:
    encoded = abi_encode(LEAF_TYPES, [fields["policy_hash"], fields["holder_hash"], fields["status_code"],
                                      fields["limit_cents"], fields["starts_at"], fields["ends_at"],
                                      fields["terms_hash"]])
    return "0x" + keccak256(encoded).hex()


def _pair(a: bytes, b: bytes) -> bytes:
    return keccak256(a + b) if a <= b else keccak256(b + a)


def _raw(h: str) -> bytes:
    return bytes.fromhex(h[2:] if h.startswith("0x") else h)


def build(leaves: Iterable[str]) -> list[list[bytes]]:
    """The tree, level by level from the sorted leaves up to the root, kept
    so proofs come from a lookup rather than a rebuild."""
    level = sorted(_raw(l) for l in leaves)
    levels = [level]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(_pair(level[i], level[i + 1]))
            else:
                nxt.append(level[i])   # an odd leaf is carried up as it is
        level = nxt
        levels.append(level)
    return levels


def root_of_tree(levels: list[list[bytes]]) -> str:
    if not levels or not levels[0]:
        return "0x" + "00" * 32
    return "0x" + levels[-1][0].hex()


def proof_from_tree(levels: list[list[bytes]], leaf: str) -> list[str] | None:
    """The sibling hashes from this leaf to the root; None if it is not
    in the tree."""
    if not levels or not levels[0]:
        return None
    target = _raw(leaf)
    bottom = levels[0]
    import bisect
    index = bisect.bisect_left(bottom, target)
    if index >= len(bottom) or bottom[index] != target:
        return None
    path: list[str] = []
    for level in levels[:-1]:
        sibling = index ^ 1
        if sibling < len(level):
            path.append("0x" + level[sibling].hex())
        index //= 2
    return path


def root_of(leaves: Iterable[str]) -> str:
    return root_of_tree(build(leaves))


def proof_of(leaves: Iterable[str], leaf: str) -> list[str] | None:
    return proof_from_tree(build(leaves), leaf)


def verify(root: str, proof: Iterable[str], leaf: str) -> bool:
    node = _raw(leaf)
    for sibling in proof:
        node = _pair(node, _raw(sibling))
    return node == _raw(root)
