# The calculation agent's rulebook

A parametric policy pays on a number. Everything that could go wrong with
it goes wrong before the event, in the questions nobody wrote down: which
source, which one when that one is silent, which of the agency's three
revisions is final, what a reading has to pass to be believed, how long the
policyholder has to say the number is wrong, and what happens when the
publisher shuts down. A catastrophe bond answers these in a calculation
agent agreement. Here they are answered in `clause/protocol/rulebook.py`,
peril by peril, and the same words go into section 10 of every contract
and onto the site's Calculation rules page (`#/rules`, `GET /api/rulebook`).

For each peril the rulebook states:

| Field | What it fixes |
|---|---|
| `index` | What is measured and in what unit |
| `primary` | The source read first |
| `fallbacks` | The sources that stand in, in order, and the silence that brings each in |
| `final_data`, `freeze_hours` | Which publication counts, and the moment after which revisions do not reopen a settlement |
| `criteria` | The tests a reading must pass before it is believed |
| attestation | The chain's own rule, quoted from the aggregator: validators, quorum, median, dispersion |
| `deadline_days`, `on_missing_data` | From the peril's data source: how long after the term the figure may still arrive, and what happens if it never does |
| `objection_days` | Thirty days after a settlement to name the reading in dispute, on the Proof page |
| successor | If the publisher stops or changes method, a named successor from the fallback chain, announced on the Proof page, in force seven days later; threshold, unit and steps unchanged |
| archive | Every validator report, the settled figure and the source's response are kept with the settlement, so the result can be reproduced from its inputs |

The rulebook carries a version (`2026-09`). A policy is settled under the
version printed in its contract; a later version applies to policies
written after it.

## Why the fallbacks are ordered as they are

Observation before reanalysis. Station data is what a person can look up;
a reanalysis is a model's reconstruction, and for wind it under-reads the
strong days. So the national service's station is primary for storm,
vehicle flood and drought; NASA POWER and ERA5 stand in only for a missing
day, and only after quantile mapping to the station's own record, so a
reanalysis day is read on the station's scale.

Reviewed before automatic. An automatic magnitude arrives in minutes and
is revised; the reviewed figure a week later is the one that stands. An
automatic figure may arm a policy; it does not settle it.

Two sources before one. Where two independent sources agree within a
stated tolerance the reading settles at once; a single source settles only
once its own revision window has passed.

## When the cover starts, and why it is not the day it is bought

A premium is the chance of an event in a term of so many days, worked out
for a buyer who does not know whether one is coming. Almost every peril
here breaks that assumption in the same way: the event is public before it
happens. A named storm is on the news about a week before it lands and the
models behind those forecasts run out to roughly ten days. An earthquake
gives no warning, but its aftershock sequence is public from the moment the
mainshock is felt, and that sequence is where the next weeks of shaking
actually sit. A dry season is not forecast at all — it is watched — and by
the time a farmer knows the rain has not come, weeks of the window are gone
and the total is already low. An airline knows its aircraft is late hours
before the passenger does.

Cover bought inside those windows is bought by someone who knows more than
the price does, and the pool loses the difference on every such policy. The
people who bought early pay for it. So each peril answers it in the way its
own index allows, and the answer goes into the rulebook (`waiting` in
`RULES`) and therefore into section 10 of every contract:

| Peril | Rule |
|---|---|
| Earthquake | Cover starts 3 days after it is bought |
| Storm | Cover starts 10 days after it is bought |
| Vehicle flood | Cover starts 10 days after it is bought |
| Drought | Cover starts on the day the station's season opens, and sales for a season close 15 days before that |
| Flight delay | No wait; the cover has to be bought at least 24 hours before the scheduled departure |

Three things follow, and each is stated rather than left to be worked out.

**The wait does not shorten the cover.** A year bought is a year of cover;
it starts later and ends later. Nothing about the price changes either: a
window of a given length costs the same wherever it is put, for a hazard
that does not know what day it is, which is why `build_policy` moves
`starts_at` and leaves `term_days` alone.

**An event inside the wait pays nothing and ends nothing.** This is the
part a policy elsewhere often gets wrong. The cover starts on the day the
document names whatever the weeks before it brought; the policy is not
cancelled and the premium is not returned. `Chain._too_early` is the one
place that decides it, and it catches two cases: the block falling inside
the wait, and — less obvious — a source whose index is a running maximum
still carrying the figure a storm set during the wait on the morning the
cover starts. The second needs `EdgeReading.peak_at`, when the maximum was
last raised, because `attested_at` only says when the source last spoke and
a quiet day speaks too.

**Drought is a sales deadline, not a wait.** A season is 150 days long and
cannot be waited out, so `Station.opens` makes the season a range of dates
in the calendar, the same every year, and the season a policy measures is
the next one to open. `Drought.refuse_to_write` closes sales 15 days before
it does; cover bought after that is cover for the following season, and
both dates are on the quote and in the contract before anything is paid.
The chain's own rainfall source follows the same calendar: it opens on the
station's day, fills, closes, and stands at zero until the next year's
opening, so the months between two seasons measure nothing and no policy
covers them.

Flight is the exception that proves the shape of the rest: the cover names
one flight, so a waiting period would put that flight outside the cover
instead of inside it. It refuses the sale instead, and because a date alone
is a different instant in every timezone, the subject carries the scheduled
departure time and `FlightDelay.departs_at` reads it in the clock of the
airport the flight leaves from.

## What is not here yet

The objection is recorded and answered by the operator; there is no
second-instance reviewer. The archive holds the responses as received; a
signed copy from the publisher is not obtainable for most sources. Both are
stated as gaps rather than papered over.
