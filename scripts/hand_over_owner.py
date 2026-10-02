#!/usr/bin/env python3
"""Hand the owner role of the two deployed contracts to a key kept offline.

    CLAUSE_ANCHOR_KEY=0x... python scripts/hand_over_owner.py \\
        --owner 0xTheKeyYouKeepOffline

For a pair that is already deployed. A deployment made since --owner existed
does this in the same run; this is the same two calls for the pair that went
out before it, and for any deployment where the warning at the end of
scripts/deploy_anchor.py was left unanswered.

Owner and issuer are not the same size. Issuer mints, burns and settles, and
it is hot by nature: it lives in the environment of a public web process.
Owner can change the issuer, and these contracts have no timelock, no
guardian and nothing upgradeable, so a stolen issuer can be replaced and a
stolen owner cannot. Nothing else changes: the issuer stays where it is, no
token is touched, and every policy already on the chain stays exactly as it
is. The new owner can call setIssuer; the old one no longer can.

The key is read from the environment, never from an argument, so it does not
land in a shell history. The addresses come from the environment too, or
from --policy and --book.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from clause.anchor.rpc import Rpc, RpcError  # noqa: E402
from clause.anchor.service import CHAINS  # noqa: E402
from clause.anchor.signing import (address_of_key, checksum, encode_call,  # noqa: E402
                                   private_key_of, sign_1559, to_address)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--owner", default=os.environ.get("CLAUSE_ANCHOR_OWNER", "").strip(),
                        help="the address that should own both contracts, which must not be "
                             "the signing key. Defaults to CLAUSE_ANCHOR_OWNER.")
    parser.add_argument("--policy", default=os.environ.get("CLAUSE_ANCHOR_POLICY", "").strip())
    parser.add_argument("--book", default=os.environ.get("CLAUSE_ANCHOR_BOOK", "").strip())
    parser.add_argument("--rpc", default=os.environ.get("CLAUSE_ANCHOR_RPC", "").strip())
    parser.add_argument("--chain-id", type=int,
                        default=int(os.environ.get("CLAUSE_ANCHOR_CHAIN_ID", "84532")))
    parser.add_argument("--dry-run", action="store_true",
                        help="read the owners and print the calldata; send nothing")
    args = parser.parse_args()

    key_text = os.environ.get("CLAUSE_ANCHOR_KEY", "").strip()
    if not key_text:
        print("set CLAUSE_ANCHOR_KEY in the environment", file=sys.stderr)
        return 2
    try:
        key = private_key_of(key_text)
    except ValueError as error:
        print(f"CLAUSE_ANCHOR_KEY: {error}", file=sys.stderr)
        return 2
    sender = address_of_key(key)
    if not args.owner:
        print("give --owner, or set CLAUSE_ANCHOR_OWNER: an address you keep "
              "offline, not this signing key", file=sys.stderr)
        return 2
    wanted = checksum(args.owner)
    if wanted.lower() == sender.lower():
        print("the owner given is the signing key itself, which is the thing "
              "handing it over is for", file=sys.stderr)
        return 2
    contracts = [(name, address) for name, address in
                 (("ClausePolicy", args.policy), ("ClauseBook", args.book)) if address]
    if not contracts:
        print("give --policy and --book, or set CLAUSE_ANCHOR_POLICY and "
              "CLAUSE_ANCHOR_BOOK; docs/anchor.md records the deployed pair",
              file=sys.stderr)
        return 2

    rpc_url = args.rpc or CHAINS.get(args.chain_id, {}).get("rpc", "")
    if not rpc_url:
        print("no public RPC known for this chain; pass --rpc", file=sys.stderr)
        return 2
    rpc = Rpc(rpc_url)
    data = encode_call("setOwner(address)", [wanted])
    print(f"signer {sender} on chain {args.chain_id}")
    print(f"calldata setOwner({wanted}) = 0x{data.hex()}")
    try:
        nonce = rpc.nonce(sender)
        for name, address in contracts:
            out = rpc.eth_call(to=address, data=encode_call("owner()", []))
            now = checksum("0x" + out[-20:].hex()) if len(out) >= 32 else None
            print(f"{name} {address}: owner is {now}")
            if now is not None and now.lower() == wanted.lower():
                print(f"  already handed over; nothing to send")
                continue
            if now is not None and now.lower() != sender.lower():
                print(f"  this key is not the owner, so it cannot hand it over",
                      file=sys.stderr)
                return 1
            if args.dry_run:
                print("  --dry-run: not sent")
                continue
            max_fee, tip = rpc.fees()
            raw = sign_1559(key, chain_id=args.chain_id, nonce=nonce,
                            max_priority_fee=tip, max_fee=max_fee, gas=80_000,
                            to=to_address(address), value=0, data=data)
            print(f"  setOwner tx {rpc.send_raw(raw)}")
            nonce += 1
    except RpcError as error:
        print(f"could not talk to the node at {rpc_url}: {error}", file=sys.stderr)
        return 1
    if not args.dry_run:
        print()
        print(f"# set this on the service so its page can say what it expects:")
        print(f"CLAUSE_ANCHOR_OWNER={wanted}")
        print("# and read /api/anchor: signer_is_owner should be false, with both")
        print("# contracts answering the new owner. A transaction takes a few")
        print("# seconds to confirm, so ask again if it still says the old one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
