# The public chain beside the protocol's own

The protocol's chain is the record: every policy, reading and settlement
lives there, and the Proof page reads it. A public chain adds a witness
that nobody running the protocol controls. The first one is Base Sepolia;
the code is plain EVM and would run on Base itself with a chain id.

## What goes to the chain

| When | What | Where |
|---|---|---|
| A policy is issued | `mint(to, policyId, holderHash, termsHash)`: a token to the holder's linked Ethereum wallet, or to the signer's address held for them | `ClausePolicy` |
| A policy is cancelled | `burn(policyId, reason)` | `ClausePolicy` |
| The chain settles a policy | `settle(policyId, status, payoutCents, readingHash, when)`: an event | `ClauseBook` |
| The book changed since the last root (checked every `CLAUSE_ANCHOR_EVERY` seconds) | `anchor(root, leafCount, epoch)` | `ClauseBook` |

Each of these is an *intent* in the book the moment it happens, with its
transaction hash and block once sent and mined. A restart loses nothing;
a node that is down is tried again next cycle; a call that would revert
(`eth_estimateGas` says so) is marked failed and never paid for.

The token cannot move: every ERC-721 transfer and approval reverts, and
`locked(tokenId)` is true (ERC-5192, interface `0xb45a3c0e`), so a wallet
knows before it tries. The token id is `uint256(keccak256(policyId))`;
`tokenURI` is the protocol's own metadata for the policy
(`<base URI><policyId>/token`), which carries the certificate image.

## Whose wallet

A buyer who has linked an Ethereum wallet on their profile (the wallet
signs a short text; `clause/protocol/links.py`) gets the token minted to
that wallet. Everyone else's is minted to the signer's address and held
for them; the token dialog says so. A buyer who links a wallet later can
ask for the token there (`POST /api/policies/{id}/anchor/claim`): a mint
not yet sent is pointed at the wallet; one already on the chain is burned
and minted again to the wallet, the mint held back until the burn is
mined, because an ERC-5192 token cannot be transferred and the contract
would refuse a second mint of the same id while the first exists.

## The Merkle root

One leaf per policy with a token:

```
leaf = keccak256(abi.encode(
    keccak256(policyId), keccak256(holder), uint8 status,
    uint256 limitCents, uint64 startsAt, uint64 endsAt, bytes32 termsHash))
```

with status 1 active, 2 paid, 3 lapsed, 4 expired, 5 cancelled. Leaves are
sorted, pairs are hashed in sorted order, an odd leaf is carried up as it
is. A proof is the list of sibling hashes; `verify(root, proof, leaf)` on
the book contract, the Python in `clause/anchor/merkle.py` and the
Keccak in the site's own script all compute the same walk. The epoch is
the protocol's Unix time when the tree was built and only rises.

`GET /api/policies/{id}/anchor` returns the leaf's fields in the clear,
the leaf, the siblings, the root and the anchoring transaction. The Proof
page shows them and has a button that recomputes everything in the
browser, so a person checks the protocol's claim without trusting the
protocol's server.

## Without a key

With no key configured the service runs in *record* mode: roots are built,
intents are recorded as `pending`, and the pages say so. Nothing is lost:
the day a key and the contract addresses are set, the pending intents go
out in order, oldest first, so a burn never overtakes its mint.

Policies the demonstration writes for itself (the opening book and the
buyers that keep arriving) are in the root, since the root is the book as
it is, but get no token, burn or settlement of their own: the public chain
is for cover people bought.

Open policies from before anchoring existed are queued at startup (the
backfill); cover that had already ended is in the root but not minted
after the fact. Tokens burned before then were never on the chain, so
nothing is burned for them; settlements are told from the day anchoring
starts. In a book from before the demonstration's policies were marked,
a policy with nobody behind its holder (no device key, no Privy account,
no linked wallet, not bound by a partner) is taken as the demonstration's.

## Going live

1. Make a fresh key for the signer and fund it with a little Base Sepolia
   ETH from a faucet. The whole first year costs a fraction of one test
   ETH.
2. Deploy the two contracts from it:

   ```
   CLAUSE_ANCHOR_KEY=0x… python scripts/deploy_anchor.py \
       --rpc https://sepolia.base.org --chain-id 84532 \
       --base-uri https://api.clause.insure/api/policies/
   ```

   It prints the four environment lines.
3. Set them on the service and restart:

   ```
   CLAUSE_ANCHOR_CHAIN_ID=84532
   CLAUSE_ANCHOR_RPC=https://sepolia.base.org
   CLAUSE_ANCHOR_POLICY=0x…
   CLAUSE_ANCHOR_BOOK=0x…
   CLAUSE_ANCHOR_KEY=0x…
   CLAUSE_ANCHOR_EVERY=600      # seconds between cycles; optional
   ```

4. `GET /api/anchor` shows `"mode": "live"`, the signer, its balance and
   the last root with its transaction; `POST /api/operator/anchor/run`
   runs a cycle now.

The key should be a hot key with the issuer role only. It can mint, burn,
settle and anchor; it cannot change the issuer. Pass `--owner`, or set
`CLAUSE_ANCHOR_OWNER`, so the deployment hands the owner role to a key
that stays offline in the same run: owner can change the issuer, and
these contracts have no timelock, no guardian and nothing upgradeable, so
a stolen issuer can be replaced and a stolen owner cannot. Keep only a few
weeks of gas on the signer, and rotate it by calling `setIssuer` from the
owner and changing the variable. `/api/anchor` reports the balance so a
low one is seen before it stops sending, and the owner of each contract so
a deployment that was never handed over does not look like one that was.

## What is deployed

Nothing in the code records an address, so the deployment that is running
is written down here. Both are public and anyone can read them.

| | |
|---|---|
| chain | Base Sepolia, id 84532 |
| `ClausePolicy` | [`0x663B145F03B4C76df664730C4D57E66639Aa4197`](https://sepolia.basescan.org/address/0x663B145F03B4C76df664730C4D57E66639Aa4197) |
| `ClauseBook` | [`0xd7250ab229358ae42a43BdC021F447225e6D2BEB`](https://sepolia.basescan.org/address/0xd7250ab229358ae42a43BdC021F447225e6D2BEB) |
| issuer, and today also owner | [`0x03Cda5776FD8868dFb69Aaa4f9626590eA1586B2`](https://sepolia.basescan.org/address/0x03Cda5776FD8868dFb69Aaa4f9626590eA1586B2) |
| the address the owner role is to be handed to | [`0x45A9282bdDBa6755Df15E70a5C3617fF5e7283b4`](https://sepolia.basescan.org/address/0x45A9282bdDBa6755Df15E70a5C3617fF5e7283b4) |

The last row is where owner is going, not where it is. It was checked
before being written down: the mixed-case checksum holds, so it is not a
mistyped address; there is no contract code at it, so a plain key can send
`setIssuer` when the issuer has to be rotated; and it has sent no
transaction and holds nothing on this chain, which is what a key kept
offline looks like from the outside. What the chain cannot show is that
anybody holds the key. Sign something with it before handing over, because
owner is the one role nothing can recover.

This pair was deployed before the handover existed, so `owner()` on both
still answers the signing key, which `/api/anchor` says plainly. Moving it
is one call per contract from that key, which `scripts/hand_over_owner.py`
makes:

    CLAUSE_ANCHOR_KEY=0x… python3 scripts/hand_over_owner.py \
        --policy 0x663B145F03B4C76df664730C4D57E66639Aa4197 \
        --book   0xd7250ab229358ae42a43BdC021F447225e6D2BEB \
        --owner  0x45A9282bdDBa6755Df15E70a5C3617fF5e7283b4 \
        --dry-run

It reads the owner of each contract first and sends nothing with
`--dry-run`; without it, it sends `setOwner` to each and prints the
transactions. Nothing else changes: the issuer stays where it is, no token
is touched, and every policy already on the chain stays as it is. Afterwards
set `CLAUSE_ANCHOR_OWNER` on the service, so `/api/anchor` can say the owner
is where it should be rather than only what it is.

## What it is not

It is not the settlement layer: nothing pays out from these contracts and
no premium touches them. It is a public, timestamped, independently
verifiable copy of what the protocol says its book is, which is what a
buyer, a company or a regulator needs to check the protocol against
itself.
