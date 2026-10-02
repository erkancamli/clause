"""A public chain beside the protocol's own.

The protocol's chain is the record: every policy, reading and settlement
lives there and the proof page reads it. What a public chain adds is a
witness nobody here controls. This package writes three things to one:
each policy token, minted to its holder and burned when the policy is
cancelled; each settlement, as an event; and, on a timer, the root of a
Merkle tree over the whole book, so that any policy's place in the book
on that day can be proven from a handful of hashes against a root the
chain holds.

The first chain is Base Sepolia. The code speaks plain JSON-RPC and signs
its own transactions, so it needs no wallet library and no node of its
own, only an RPC endpoint and a funded key; with neither, it still builds
the roots and records what it would have sent, so the proof page works and
the day the key arrives nothing is missing.
"""

from .service import Anchor, AnchorConfig, AnchorError, AnchorIntent

__all__ = ["Anchor", "AnchorConfig", "AnchorError", "AnchorIntent"]
