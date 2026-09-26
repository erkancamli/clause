# Architecture

How a policy becomes a predicate, and how a predicate becomes a payment.

---

## The shape of the thing

```
  buyer                     Clause                        Rialo
  -----                     ------                        -----

  subject  ------------->  peril model
                             |
                             v
                          exceedance function
                             |
                             v
  limit, term  --------->  payout curve  --->  expected share
                             |
                             v
                          pricing engine  <---  simulated book (20k years)
                             |
                             v
                          quote: EL + risk load + expenses
                             |
  accept  ------------->  pool.write()  ---> solvency, concentration, capital
                             |
                             v
                          policy + predicate
                             |
                             +----------------------->  register predicate
                                                          with dependency keys
                                                              |
                                        Edge attestation ---> |
                                                              v
                                                        validators re-evaluate
                                                        only the woken keys
                                                              |
                                                              v
  payment  <--------------  settle()  <-----------------  transaction enqueued
```

Nothing sits between the last two steps. There is no keeper, no relayer, no
claims process, and no moment at which anyone decides whether to pay.

What does sit before `settle()` is re-evaluation: the compliance ruling on
the registry as it now stands, the eligibility of the holder, and the
operator's policy pipeline (a denylisted address, a refused destination).
Each runs again in the block that would pay, and a refusal there unwinds the
policy on the terms of a source that never published: the premium comes
back, the payout does not go out.

---

## Modules

| Module | Responsibility |
| --- | --- |
| `clause/mathx.py` | Special functions, written out rather than imported |
| `clause/predicate.py` | Predicate grammar, dependency extraction, evaluation |
| `clause/perils/base.py` | Payout curves, data sources, the `Peril` interface |
| `clause/perils/{quake,weather,flight,vehicle,storm}.py` | One exceedance function each |
| `clause/hazard/daily_extremes.py` | The offline build for daily rain and wind extremes, and their test |
| `clause/pricing/simulation.py` | The simulated world and policy settlement in it |
| `clause/pricing/engine.py` | Capital, marginal allocation, the quote |
| `clause/protocol/policy.py` | Policy record and lifecycle states |
| `clause/protocol/pool.py` | Capital, underwriting rules, the ledger |
| `clause/protocol/pipeline.py` | The operator's policy: denylist and moratoria, first to deny stops it |
| `clause/protocol/documents.py` | Reading keys, and the documents sealed to them: envelope, record, deletion on decision |
| `clause/protocol/vetting.py` | The operator's checklist for letting a company in: items by domicile and role, registers to read, documents by kind, the record per item, activation gated on it, review due a year on |
| `clause/protocol/fees.py` | The platform's fee (1% of premium, out of the company's fronting fee, returned with refunds) and monthly statements |
| `clause/protocol/desk.py` | The company's book worked: search, filters, renewals due, exposure by province, CSV |
| `clause/protocol/bordereaux.py` | The risk, claims and reconciliation bordereaux per carrier and month, read off the book, the settlements and the fee ledger; CSV |
| `clause/protocol/complaints.py` | Complaints as threads on the policy with the company's clock, the ombudsman route by country, and the application file assembled from the record |
| `clause/protocol/rulebook.py` | The calculation agent's rulebook per peril: sources and fallbacks, final data and freeze, criteria, objection window, successor and archive rules; section 10 of every contract |
| `clause/anchor/service.py` | The public chain beside this one: intents (mint, burn, settle, root) recorded as things happen, sent as signed transactions when a key is set, receipts read back; proofs of a policy's place in the book |
| `clause/anchor/merkle.py` | The book as a Merkle tree: one leaf per policy, sorted pairs, proofs the contract's `verify` accepts |
| `clause/anchor/signing.py` | Keccak, secp256k1 with RFC 6979 nonces, RLP, the ABI, EIP-1559 transactions: signing without a wallet library |
| `clause/anchor/rpc.py` | The few JSON-RPC calls a signer needs, over httpx |
| `contracts/` | `ClausePolicy.sol` (ERC-721 + ERC-5192, locked, burn on cancel) and `ClauseBook.sol` (roots by epoch, settlement events, `verify`); compiled artifacts in `clause/anchor/artifacts.json` |
| `clause/chain/world.py` | Rialo shaped chain, Edge readings, settlement |
| `clause/rpc/client.py` | The published Rialo RPC |
| `clause/api/app.py` | HTTP surface and the event stream |
| `clause/api/repeat.py` | What a signed request was answered with, kept for a quarter of an hour, so a purchase whose reply went missing can be asked for again and asking again buys nothing more |

The dependency direction is strict: perils know nothing about pricing, pricing
knows nothing about the pool, the pool knows nothing about the chain. A fourth
peril is one file implementing one interface, and nothing else changes.

---

## The predicate is the policy

When a policy is written, the peril renders it as a predicate expression.

Earthquake:

```
edge("api.seismic.example/v1/max-magnitude?lat=40.99&lon=29.03&radius_km=50").max_magnitude >= 5.5
```

Drought:

```
edge("api.meteo.example/v1/station/TR-KONYA/cumulative").window_closed >= 1
  and edge("api.meteo.example/v1/station/TR-KONYA/cumulative").rainfall_mm <= 94.4
```

Flight delay:

```
edge("api.flightstatus.example/v1/TK1979/2026-10-04").arrival_delay_minutes >= 120
```

`dependencies()` extracts the keys the expression reads, for example
`edge:api.meteo.example/v1/station/TR-KONYA/cumulative`. Those keys are what the
predicate is registered against, and they are the reason the protocol scales.

---

## The narrowing step

A validator does not evaluate every predicate every block. It holds an inverted
index from dependency key to armed predicate, and each block it:

1. collects the set of keys that changed,
2. unions the predicates registered against those keys,
3. evaluates only those,
4. enqueues the transactions attached to the ones that turned true.

`Chain._evaluate` does the same thing and counts its work, and there is a test
asserting the count stays far below one evaluation per policy per block. This
is what makes the cost of watching a book independent of its size, and it is
the property the whole economic argument rests on: under conventional
parametric cover, administration cost sets a floor under the smallest viable
policy, and that floor is what has kept smallholder agriculture uninsured.

---

## What the company sees, and nobody else

A home or a vehicle is applied for with its address, and the company that
issues the policy confirms it is the applicant's: a title deed, a lease, a
registration. Those papers never reach the protocol in the open. The
applicant's browser seals each one to the reading key of the party that will
decide (the company's own account, or the operator where a stand in company
is decided for), with an ephemeral P-256 key, HKDF and AES-256-GCM, the
application id bound in as additional data. The protocol stores the
ciphertext beside the book and a record it can read: what was sent, how
large, and who opened it when, which the applicant sees. The reading key is
made non extractable in the deciding party's browser and never leaves it;
the operator cannot open a document sealed to a company, and the database
alone opens nothing. On the decision, withdrawal or lapse, the ciphertext is
deleted and the record stays. The envelope is written out in
`clause/protocol/documents.py`, so another client can make or open one.

---

## Letting a company in

A registration is a claim. Two checks run on their own (the LEI record at
GLEIF, and a proof file on the company's own domain); the rest is a person
reading registers the protocol cannot read for them, and
`clause/protocol/vetting.py` gives that work a shape. Each company gets a
checklist by domicile and role: the legal entity, control of the domain,
the licence and the classes it must name (Türkiye: the branch for each
peril, and membership of the insurers' association), the signatory's
authority, sanctions screening, live enforcement, and two recommended
items (solvency, a data processing agreement). Every item says what to
confirm and links the register to read; the company's documents sit
beside the item they support, by kind, and are never proof on their own.
The operator records each item with where they looked and what they saw;
activation is refused until every required item is confirmed, and the
review records the checklist as it stood. A year on the checks are due
again, and the operator's page says so, along with licences about to
lapse. The company sees the same list on its own page, so it knows what
it still owes and can add the documents asked for.

---

## What the platform is paid

The buyer pays the pool's premium and, on top, the issuing company's
fronting fee; the price on the screen is the pool's price and nothing is
added for the platform. The platform takes one per cent of the premium out
of the company's fee the moment the fee is paid, never more than the fee
itself, in proportion when the fee arrives in instalments; a fee that goes
back to the buyer (a mistake undone within the hour, a cooling off period)
takes the platform's share back with it, from the platform's own account.
Every movement is an entry in `clause/protocol/fees.py`, and a company's
month of entries is its statement, the same statement the operator sees
for every company, with CSV for the accountant.

---

## Settlement

`attest(reference, field, value)` writes an Edge reading and adds its key to
`_pending_touches`. The next block includes that key in its touched set, the
predicates registered against it are evaluated, and the ones that turned true
settle **in that same block**. There is a test asserting settlement latency is
zero blocks.

When an event wakes several policies at once, they settle together in one
block. That is not an implementation detail, it is the event the capital model
priced: `test_one_event_settles_every_policy_inside_its_circle` asserts three
policies inside the same radius all settle in a single block, for a single
event, with no claim filed.

A policy leaves the active state exactly one way of four:

| State | Meaning |
| --- | --- |
| `PAID` | The predicate turned true; the band was paid |
| `LAPSED` | The term ended without a trigger |
| `EXPIRED` | The source went quiet past its deadline; premium refunded |
| `CANCELLED` | Unwound before the term began |

Every transition writes a ledger entry, and `pool.check_ledger()` replays the
whole book from entries and asserts the balance reconciles.

---

## The simulated chain

`clause/chain/world.py` runs a Rialo shaped chain locally: fifty millisecond
blocks, a block height, retained blocks, Edge readings per source, an armed
predicate index, and a settlement log.

It carries an accelerated world clock, `world_acceleration = 40,000`, so one
block advances the world about 0.023 days and a one year policy term takes
roughly 16,000 blocks, which is minutes rather than a year. That acceleration
is the only reason the protocol can be demonstrated at all: its entire argument
is about what happens over a term.

The world it generates is independent of the world pricing simulates. That
independence is deliberate and is what makes the coherence test in
`docs/method.md` section 7 meaningful. Two models built from the same draws
would agree by construction and prove nothing.

### What a devnet deployment would change

`clause/rpc/client.py` already speaks the published Rialo RPC:
`get_subscription`, `get_triggered_transactions`, `get_workflow_lineage`, with
a candidate spelling map that falls back only on method not found.

Moving to devnet replaces `Chain` with that client and nothing else:

- `register()` becomes a subscription registering the same predicate string,
- `attest()` disappears, since Edge readings come from real validators,
- `produce_block()` disappears, since blocks arrive,
- settlement becomes the transaction Rialo enqueues rather than one the
  simulator runs.

Pricing, the pool, the ledger and the interface are untouched, because none of
them import from `clause.chain`.

---

## The HTTP surface

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/perils` | Perils, their subjects and default structures |
| GET | `/api/hazard` | The hazard table for a subject |
| GET | `/api/vehicle`, `/api/storm` | A place's own extreme rain and wind levels |
| POST | `/api/quote` | Price a policy, with the reasoning |
| POST | `/api/policies` | Bind cover, subject to the pool's rules |
| GET | `/api/policies` | The book |
| GET | `/api/policy` | The policy pipeline: its rules, and every live moratorium |
| POST | `/api/policy/check` | The decision a stage would take, without acting |
| GET, POST | `/api/operator/policy`, `/deny`, `/pause`, `/{id}/lift` | The operator's book of refusals |
| POST | `/api/auth/reading-key`, `/api/operator/reading-key` | The public half of a browser's reading key, so documents can be sealed to it |
| GET | `/api/applications/recipient` | Who could open documents sent with an application to a company, and the key to seal them to |
| POST, GET, DELETE | `/api/applications/{id}/documents[/{doc}]` | Send sealed documents; the deciding party fetches the envelope, which is recorded; the applicant takes one back |
| GET, POST | `/api/carriers/{id}/vetting` | The checklist for one company; the operator records an item (confirmed, failed, set aside) with where they looked and what they saw |
| GET | `/api/company/bordereaux`, `/api/operator/bordereaux` | `kind=risk|claims|reconciliation`, `month`, `format=csv`: the three bordereaux for a carrier, or every carrier for the operator |
| POST | `/api/policies/{id}/complaints` | The holder raises a complaint; the company's time to answer starts |
| GET, POST | `/api/complaints`, `/api/complaints/{id}/messages`, `/close`, `/escalate`, `/package` | The thread, the answer, the close, the escalation to the ombudsman and its file (JSON or text) |
| GET | `/api/company/complaints`, `/api/operator/complaints` | The company's complaints with the clock; every complaint for the operator |
| GET | `/api/rulebook` | The calculation rules, peril by peril, as printed in every contract |
| GET | `/api/policies/{id}/contract?download=1` | The holder's own copy of the accepted contract; the day it is first taken is noted for the withdrawal clock |
| GET | `/api/anchor` | The public chain's state: mode, contracts, signer, last root, recent intents with transactions |
| GET | `/api/policies/{id}/anchor` | One policy on the public chain: its intents and its Merkle proof against the last anchored root |
| POST | `/api/operator/anchor/run` | One anchor cycle now: a root if the book moved, then whatever is pending, sent |
| POST | `/api/company/{id}/evidence` | The company adds documents after registering, by kind |
| GET | `/api/company/statements`, `/api/operator/statements` | A company's month of fee movements and what it was left with; every company's, and the platform's totals, for the operator; CSV |
| GET | `/api/company/policies`, `/api/operator/policies` | The book worked: search, status, peril, province, due within N days, sort, paging, CSV |
| GET | `/api/pool`, `/api/pool/risk` | Capital, exposure, solvency |
| GET | `/api/pool/ledger` | Every movement, replayable |
| POST | `/api/pool/deposit`, `/withdraw` | Liquidity provision |
| GET | `/api/chain`, `/api/chain/readings` | Blocks, armed predicates, readings |
| POST | `/api/chain/inject` | Attest a reading, for demonstration |
| POST | `/api/chain/silence` | Take a source offline, for demonstration |
| GET | `/api/stream` | Server sent events: blocks, settlements, quotes |
| GET | `/api/health` | Liveness |

Every answer under `/api` carries `Cache-Control: no-store`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy:
strict-origin-when-cross-origin`, a `Permissions-Policy` that turns the
device APIs off, `X-Frame-Options: DENY` and a `Content-Security-Policy` of
`default-src 'none'; frame-ancestors 'none'`. nginx says the same in front;
the application says it itself so a deployment without nginx is no less
careful.

### Keeping the book

The book is checkpointed to SQLite every five seconds and after every request
that changed it. A document is written only when its text differs from the
last write, and a log only from where it left off, so what is already on disk
costs nothing to keep. What it did cost was finding that out: every document
was encoded on every cycle to compare it. The encoder now works out a class's
shape once, and a log is encoded only past the entries already written.

The demonstration is what made the book large: a simulated chain writes
policies by the thousand and they used to be kept for ever. Settled ones past
`CLAUSE_DEMO_KEEP` (2000 by default, 0 to keep everything) are forgotten along
with their settlements; the chain keeps the counts and latencies they
contributed, so every figure it publishes is unchanged. A policy a person
bought is never touched. Three things exempt one outright: a record saying it
is not the demonstration's, a partner behind it, or the contract its holder
accepted stored on it, which only the application path writes. What is left is
the demonstration's if it is marked, if its holder is an address the
demonstration derived, or if nobody can reach it, meaning no device key is
registered for its holder, no account signed in as it and no wallet is linked
to it. That last test catches the policies written before the addresses
changed shape, which carry neither the marker nor a recognisable address.

### Rate limits

Two layers. nginx, per client address: 20 pricing requests a minute
(`/api/quote`, `/api/offers`, `/api/contract`, a partner's quote; burst 5),
3 purchases in a burst on the same zone, 240 reads a minute (burst 40), and
12 open connections. The application, per caller (the session's address
where there is one, otherwise the client address as nginx passes it), per
class of work, in a fixed window; a refusal is `429` with the wait in the
body and in `Retry-After`:

| Work | Limit |
| --- | --- |
| `quote` (a price, the offers, the contract text) | 20 to 30 a minute |
| `buy` (a policy, a rider's purchase) | 10 a minute |
| `policy` (reading one's own cover, its contract, its complaints) | 60 a minute |
| `auth` (a challenge, a session, a reading key, a profile link) | 20 to 60 a minute |
| `geocode` | 40 a minute |
| `rider` | 12 a minute |
| `faucet` | 10 an hour |
| `carrier` (registering, re-checking a register) | 5 in five minutes |
| `operator` (a guessed operator token) | 8 in fifteen minutes |

The limiter is in memory and per process, which is the right size for one
server; behind several workers the real limit is nginx's.

The interface is three static files and holds no state of its own. Everything
it shows comes from the stream or from a fetch, so two browsers watching the
same protocol see the same thing.

---

## Running unattended

The server starts a background task that writes a random policy every eight
seconds and records every refusal with its reason. The pool is seeded with
capital sized so the concentration limit actually binds during a demonstration
rather than sitting unreached, and one station is silenced at startup so the
expiry path is visible without waiting for it to occur naturally.

The point of that is that the interesting states of an insurance protocol are
the ones it reaches under load, and a demonstration that only ever shows the
happy path has not shown the protocol.
