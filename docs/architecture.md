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
| `clause/chain/world.py` | Rialo shaped chain, Edge readings, settlement |
| `clause/rpc/client.py` | The published Rialo RPC |
| `clause/api/app.py` | HTTP surface and the event stream |

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
| GET | `/api/pool`, `/api/pool/risk` | Capital, exposure, solvency |
| GET | `/api/pool/ledger` | Every movement, replayable |
| POST | `/api/pool/deposit`, `/withdraw` | Liquidity provision |
| GET | `/api/chain`, `/api/chain/readings` | Blocks, armed predicates, readings |
| POST | `/api/chain/inject` | Attest a reading, for demonstration |
| POST | `/api/chain/silence` | Take a source offline, for demonstration |
| GET | `/api/stream` | Server sent events: blocks, settlements, quotes |
| GET | `/api/health` | Liveness |

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
