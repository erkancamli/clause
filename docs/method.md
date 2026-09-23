# Method

How Clause arrives at a price, and why each step is there.

This document is the reasoning behind the numbers. Everything in it is
implemented in `clause/perils/`, `clause/pricing/` and `clause/protocol/`, and
every constant named here appears in the code under the same name.

---

## 1. The premium

A premium has three parts.

```
premium = expected loss + risk load + expense load
```

**Expected loss** is the average payout over the term, from the peril's own
hazard model. It is what the policy costs in the long run if nothing else
mattered.

**Risk load** is the cost of the capital the policy forces the pool to hold. It
is the part a naive protocol gets wrong, and section 4 is about it.

**Expense load** is the cost of running the protocol, taken as
`EXPENSE_RATIO = 0.08` of expected loss.

The quote carries all three separately, because a buyer who can see that most
of their premium is risk load can act on it: move the radius, move the
attachment, buy in a different region. A single number tells them nothing.

---

## 2. Structure, kept apart from hazard

Every policy is an index, a payout curve and a term.

The **payout curve** maps an index value to a share of the limit. A step curve
pays a fixed share once a threshold is crossed. A ramp curve pays
proportionally between breakpoints. A curve runs upward (earthquake: pays as
magnitude rises) or downward (drought: pays as rainfall falls).

Given the curve and an exceedance function `S(x) = P(index at or beyond x)`,
the expected share of limit is a layer decomposition:

```
E[share] = sum over segments of (share step) x S(breakpoint)
```

which is exact for step curves, and for ramp curves is applied to the segment
ends with the ramp integrated between them. This is in
`PayoutCurve.expected_share` and is the only place structure and hazard meet.
Every peril supplies an exceedance function and nothing else. Adding a fourth
peril means writing one function.

---

## 3. The hazard models

### Earthquake

The index is the largest magnitude recorded inside a radius of the insured
address during the term.

Magnitudes follow Gutenberg and Richter, `log10 N(>= M) = a - bM`. That
describes diffuse background seismicity well and a mapped fault badly: large
events on a fault recur more often than an extrapolation from its small events
predicts, because the fault ruptures at a size set by its geometry. An early
version of this model priced pure Gutenberg and Richter and produced a return
period for an Istanbul M7 of 592 years against a published figure near 75. That
is not a small error; it is an underpriced book.

The model now carries both terms:

- **Background**, truncated at `BACKGROUND_MAXIMUM = 6.6`, scaled from a
  reference circle of `REFERENCE_RADIUS_KM = 50` by area, since diffuse
  seismicity is spread through the region.
- **Characteristic**, a separate Poisson rate for the fault's own large event,
  concentrated within `_CHARACTERISTIC_HALF_WIDTH = 0.25` magnitude units of
  the fault's characteristic magnitude.

They scale differently with the policy radius, and that is the point. Doubling
the radius roughly quadruples background exposure but adds the fault term only
if the fault comes inside the circle. The radius is a real choice the buyer
makes, and the hazard table attached to every quote shows its effect.

Occurrence is Poisson, so with rate `lambda` over the term,
`P(at least one) = 1 - exp(-lambda)`.

For a 50 km circle around Kadıköy over one year the model gives:

| Magnitude | Probability | Return period |
| --- | --- | --- |
| M5.0 | 16.2% | 6 years |
| M5.5 | 6.1% | 16 years |
| M6.0 | 2.5% | 40 years |
| M6.5 | 1.25% | 80 years |
| M7.0 | 1.02% | 98 years |

The M7 figure is the one to check against published work, and it now sits in
the right neighbourhood.

### Drought

The index is cumulative rainfall at a named station across a growing season.

Seasonal rainfall totals are conventionally fitted as a gamma distribution:
non negative, right skewed, and published by meteorological services in exactly
this form. Two numbers per station and season pin it down by method of moments:

```
shape = 1 / cv^2          scale = normal / shape
```

The policy pays as the total falls, so the exceedance function is a lower tail
probability and the curve runs downward. The default structure attaches at 80%
of normal, pays half at 60%, and pays in full at 40%.

A detail that turns out to be the whole contract: the predicate requires the
measurement window to have closed.

```
edge(source).window_closed >= 1 and edge(source).rainfall_mm <= attachment
```

Without that clause the policy pays in the first week of a dry spring, because
rainfall to date is below a seasonal threshold every year by construction. That
is not drought cover, it is a bet on the weather so far. There is a test for
this, and there is a test for it because the first implementation had the bug.

### Flight delay

The index is arrival delay in minutes, with a cancellation settled at
`CANCELLATION_MINUTES = 1440` so one curve covers both without a second
contract.

On time performance statistics give, per route and carrier, the cancellation
share, the share arriving more than fifteen minutes late, and the median delay
among late arrivals. Conditional on being late, delay length is heavy tailed
and is fitted lognormal with `_LOG_SIGMA = 0.86`, calibrated so the ratio of
the ninetieth percentile to the median sits near three, which is what published
arrival distributions show.

### Daily extremes: vehicle flood, and storm

Two covers pay on the largest day of a term: the car cover on rain, the
storm cover on wind, each where the thing insured is kept. Both are built
the same way, offline, from NASA POWER's daily series (MERRA-2: PRECTOTCORR
for rain, WS10M_MAX for wind, the latter in km/h) at the nearest of Türkiye's
81 provincial centres: the largest value in each calendar year, and a Gumbel
distribution fitted to those maxima by probability weighted moments. The
exceedance over a term of `t` years is `1 - (1 - p)^t` with `p` the annual
exceedance, and the steps of the curve are the place's own return levels, so
a wet coast and a dry plateau, an exposed cape and a sheltered valley, each
pay on what is extreme where they are. The car cover steps at 1 in 10, 25
and 50 years. The storm cover steps one level rarer, at 1 in 25, 50 and 100:
a 1 in 10 year wind day is one most homes see within a decade and one that
takes tiles rather than roofs, and paying a quarter of the rebuild cost on
it made the cover cost about twice what an Istanbul earthquake policy does
(expected loss 4.7% of the limit against 2.4%) for a loss that is a fraction
of it. At 25/50/100 the expected loss is 2.1% of the limit. The 1 in 100
level is an extrapolation of a thirty year fit, one step beyond the levels
the build tests, and the basis risk says so.

The test is fixed before the first run and identical for both: fitted on
1981 to 2010, tested on 2011 onward; the count of test years above each
place's 1 in 5 year level is judged against what the fit implies, with the
year to year dispersion measured on the fitting years, because one storm
raises several neighbouring provinces in the same year and the 81 places are
not independent. A model that fails its test is written with its failure and
the peril refuses to price anywhere; where no file has been built at all,
the same. The rain model's file records the two changes made after its
first run; the wind model is built by `python -m clause.hazard.wind_build`
on a machine with network access.

In the capital model the same regional factor makes the day that floods one
province flood the next (`RAIN_EXTREME_CORRELATION = 0.35`), and the front
that takes roofs in one province take them in the next
(`WIND_EXTREME_CORRELATION = 0.45`, higher because a front is wider than a
downpour). What the reanalysis figure is, and is not, is stated in each
peril's basis risk: an area average, lower than a gauge; the strongest hour's
mean, lower than a gust.

---

## 4. Capital, and why the same policy has two prices

This is the part that makes the protocol an insurer rather than a betting book.

### The solvency standard

The pool holds enough capital to survive the average of its worst half percent
of years. Formally, tail value at risk at `SOLVENCY_LEVEL = 0.995`: the mean
loss across the worst 0.5% of simulated years, not the loss at the 99.5th
percentile itself. A value at risk cannot see past the point it measures, and a
book with one dominant catastrophe has a tail that matters beyond it.

### Simulating the book

Capital is sized by Monte Carlo over `DEFAULT_TRIALS = 20,000` simulated years.
Each trial draws a world, not a set of independent policy outcomes:

- fault ruptures per seismic zone, shared by every policy near that fault,
- background events per location,
- regional rainfall through a Gaussian copula, so neighbouring stations have a
  dry year together,
- carrier level operational shocks.

Policies then settle against that world. The correlation is in the world, which
is the only place it can be, and it is what separates a real capital figure
from a sum of independent variances.

### Marginal capital

The book's capital requirement is simulated once and cached. Pricing a new
policy adds its loss vector to the cached book vector, trial by trial, using
the same draws. The difference in tail value at risk is the marginal capital.

```
risk load = marginal capital x COST_OF_CAPITAL x (term / 365.25)
```

Common random numbers matter here. The candidate and the book are settled
against the identical world, so the difference is signal rather than the
difference of two noisy estimates.

### What that produces

Against a book already holding eight Istanbul earthquake policies, the same
250,000 limit, same 50 km radius, same one year term:

| Where | Premium | Rate on line | Marginal capital |
| --- | --- | --- | --- |
| Istanbul, ninth policy | 35,669 | 14.27% | 244,165 |
| Ankara, same book | 444 | 0.18% | 0 |

Eighty times the price for a risk whose expected loss differs by a factor of
fourteen. The extra factor is concentration, and a protocol charging expected
loss plus a fixed margin would have quoted these within a factor of fourteen of
each other and been wrong about the ninth Istanbul policy in the direction that
ends pools.

The quote also reports a diversification verdict, comparing marginal capital to
what the policy would require standing alone. Below one it diversifies the
book; above one it concentrates it.

---

## 5. The pool's three rules

**Solvency.** No policy may be written that would leave capital below the
book's requirement, held at `CAPITAL_BUFFER = 1.15` so the book does not sit
exactly on its limit.

**Concentration.** No single modelled catastrophe may consume more than
`CONCENTRATION_LIMIT = 0.35` of pool capital, whatever the aggregate figure
says. A pool can be solvent on average and one earthquake away from nothing.

**Locked capital.** A provider may withdraw only what is not standing behind
live policies. Capital that can leave the moment it is needed was never capital.

Every refusal is recorded with its reason and shown in the interface. A pool
that never says no is not managing anything.

---

## 6. Basis risk, stated plainly

Parametric cover pays on an index, not on a loss. The two can disagree, and
that gap is basis risk. It is the honest weakness of every parametric product
and it does not go away by being onchain.

What Clause does about it:

- The index and its source are named on the policy, with publisher, field,
  resolution and settlement deadline.
- The hazard table travels with the quote, so the buyer sees what they are and
  are not covered for before they pay.
- The radius, attachment and curve are the buyer's choices, which is the only
  real lever on basis risk.

What it does not do is pretend the gap is closed.

### When the source goes quiet

Every parametric design has to answer this and most leave it undefined. Each
data source carries a `settlement_deadline_days`. If the term ends and the
source has not published by the deadline, the policy expires and the premium is
returned in full. Not a payout, not a lapse: the contract could not be
evaluated, so it is unwound. The pool's ledger records it as a refund.

---

## 7. The check that keeps the two models honest

The protocol carries two models of the world: the one it prices against and the
one the chain settles against. If they drift apart, every premium is wrong in
the same direction, and no test of either model alone would notice.

`test_the_chain_settles_at_the_frequency_the_price_assumes` runs seventy full
policy terms on the chain and compares the observed settlement rate with the
priced probability.

| Peril | Chain settled | Price assumed |
| --- | --- | --- |
| Earthquake, Kadıköy M5.5, one year | 10.0% | 6.1% |
| Drought, Konya season | 30.0% | 35.0% |

Seventy runs of a one in sixteen event is a noisy estimate, so the test bound
is three standard errors of the count itself rather than a tolerance chosen to
fit. Drift large enough to matter to a premium clears that bound; sampling
noise does not.

---

## 8. What is calibrated and what is illustrative

The **methods** are real: the distributions, the capital standard, the marginal
allocation, the layer decomposition, the copula, the characteristic earthquake
term.

The **parameters** are illustrative. Station normals, route statistics and zone
seismicity are plausible figures of the right shape, not a hazard assessment. A
live deployment fits them from the national seismic catalogue, the
meteorological service's published normals, and the regulator's on time
performance filings. The code is structured so that is a data change and
nothing else.

Nothing here should be used to price real risk without that work.

## 9. The sum insured, and the four numbers every country publishes

Everything above is about how often a thing happens and what that costs. This
section is about the other half of a parametric policy: the ceiling. Cover is
capped at what the insured thing is worth, and that cap is what makes this
insurance rather than a wager.

The ceiling is worked out, not taken on trust. A home is its floor area times
a rebuild cost per square metre, adjusted for the building's age. A field is
its area times what a hectare earns in a normal season. A trip is what the
trip cost. A car is its market value, bounded by what a car of that age can be
worth.

The hard part is the per unit figure, and the hard part of *that* is that
every country publishes four different numbers for the same thing.

| kind | what it is |
|---|---|
| `rebuild` | what it costs to build the thing again. What we want. |
| `insurance` | a scheme's own sum insured per square metre. Official, current, usually below rebuild cost on purpose. |
| `market` | a builder's or a valuer's quote. Real money, no authority. |
| `permit` | the base for a building permit fee or a property tax. |

A `permit` figure looks the most official of the four and is always the most
wrong, because it was never meant to value anything — it was meant to set a
fee. Italy's *costo di costruzione* is €505.90/m² against a real rebuild cost
near €1,800, and descends from a 1994 Lombardy figure merely re-indexed each
year. Chile's MINVU unit cost table is five to eight times below what a house
costs to build. The Philippine PSA figure is what applicants *declare* to a
building officer, divided by floor area, and puts a single house at
US$113/m². All three are genuine government publications. None of them is a
rebuild cost. The protocol records them by name and refuses to price from one,
so that nobody adds them back later thinking they were overlooked.

Two more properties of official data shape the model.

**Statistics offices publish indices, not levels.** ISTAT, ELSTAT, TÜİK and
INEGI all say how fast building costs are rising; none of them says what
building costs. An index cannot set a sum insured. It can carry a level
forward from the day it was published to today, which is what the escalation
step does — Türkiye's Ministry schedule is a 1 January figure and Turkish
building costs rise by more than a quarter a year, so by September it is a
fifth short. A figure is never carried forward more than three years: past
that the table needs revisiting, not compounding.

**A national figure is not a local one, and almost nobody publishes the
difference.** Only Indonesia (the BPS *Indeks Kemahalan Konstruksi*, 38
provinces and 514 districts), Japan (building starts statistics by
prefecture) and Taiwan (its own insurance table's city grid) publish what
building costs in each region; New Zealand's consent statistics allow one to
be computed. The spread is larger than intuition suggests: Indonesia's Papuan
highlands are 2.17× Jakarta. Everywhere else the protocol says out loud that
no regional figure exists rather than inventing a multiplier — Türkiye
publishes one national schedule, TÜİK's index has no regional breakdown, and
DASK's per square metre value is the same in Rize as in Adana.

The same discipline applies to a field. A season's revenue is a yield times a
producer price, and both belong to a year — so the exchange rate belongs to
that year too. A Turkish hectare of maize earned 105,353 lira in the 2025
season, which was US$2,662 at that year's rate; read at today's rate the same
lira would say US$2,157, and the farmer would be a fifth under-covered for no
reason but arithmetic done on the wrong day. Where a country grows a crop but
nobody publishes a price for it — Italian barley, Italian sunflower — that
crop cannot be covered there, and the refusal names the crops that can be.

Where the choice was open, the anchor is the best evidenced rebuild cost, then
an official scheme's own insurance value, then market evidence. For Türkiye
that means the Ministry's *Yapı Yaklaşık Birim Maliyetleri* (class III-B,
21,050 TL/m², 1 January 2026) rather than DASK's 11,737 TL/m². The two differ
by a factor of about 2.2 and the difference is structural, not an error: DASK's
figure is a deliberately capped statutory minimum, the Ministry's is a full
construction cost including contractor overhead and profit. Whichever is used,
the policy says which — every quote carries the figure, its publisher, its
date and its kind, so a buyer who asks why the ceiling is what it is gets an
answer from the record rather than from us.

These figures are indicative and are in the protocol's unit of account. An
issuing insurer replaces them with its own schedule.
