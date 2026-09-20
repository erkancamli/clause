#!/usr/bin/env python3
"""Deploy the two anchor contracts to Base Sepolia (or another EVM chain),
from a funded key, and print the environment lines the service needs.

    CLAUSE_ANCHOR_KEY=0x... python scripts/deploy_anchor.py \\
        --rpc https://sepolia.base.org --chain-id 84532 \\
        --base-uri https://api.clause.insure/api/policies/

The key is read from the environment, never from an argument, so it does
not land in a shell history. It becomes owner and issuer of both contracts;
move the owner role to a safer key afterwards with ``setOwner`` on each.
Gas on Base Sepolia is a fraction of a cent; the two deployments together
need well under 0.01 test ETH, which a faucet gives.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from clause.anchor.rpc import Rpc, RpcError  # noqa: E402
from clause.anchor.service import CHAINS, deploy  # noqa: E402
from clause.anchor.signing import address_of_key, private_key_of  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rpc", default="", help="JSON-RPC endpoint; defaults to the chain's public one")
    parser.add_argument("--chain-id", type=int, default=84532)
    parser.add_argument("--base-uri", default="", help="prefix for tokenURI, e.g. https://api.clause.insure/api/policies/")
    parser.add_argument("--address", action="store_true", help="print the signer's address and stop; no node is contacted")
    args = parser.parse_args()
    key = os.environ.get("CLAUSE_ANCHOR_KEY", "").strip()
    if not key:
        print("set CLAUSE_ANCHOR_KEY in the environment", file=sys.stderr)
        return 2
    try:
        signer = address_of_key(private_key_of(key))
    except ValueError as error:
        print(f"CLAUSE_ANCHOR_KEY: {error}", file=sys.stderr)
        return 2
    if args.address:
        print(signer)
        return 0
    rpc_url = args.rpc or CHAINS.get(args.chain_id, {}).get("rpc", "")
    if not rpc_url:
        print("no public RPC known for this chain; pass --rpc", file=sys.stderr)
        return 2
    rpc = Rpc(rpc_url)
    try:
        balance = rpc.balance(signer) / 1e18
        print(f"signer {signer} on chain {args.chain_id}, balance {balance:.6f} ETH")
        if balance <= 0:
            print("the signer has no gas; fund it from a faucet first, then run this again", file=sys.stderr)
            return 1
        out = deploy(rpc, key, chain_id=args.chain_id, base_uri=args.base_uri)
    except RpcError as error:
        print(f"could not talk to the node at {rpc_url}: {error}", file=sys.stderr)
        return 1
    print()
    print("# add to the service's environment:")
    print(f"CLAUSE_ANCHOR_CHAIN_ID={args.chain_id}")
    print(f"CLAUSE_ANCHOR_RPC={rpc_url}")
    print(f"CLAUSE_ANCHOR_POLICY={out['ClausePolicy']}")
    print(f"CLAUSE_ANCHOR_BOOK={out['ClauseBook']}")
    print("CLAUSE_ANCHOR_KEY=<the same key>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
