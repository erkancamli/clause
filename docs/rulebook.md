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

## What is not here yet

The objection is recorded and answered by the operator; there is no
second-instance reviewer. The archive holds the responses as received; a
signed copy from the publisher is not obtainable for most sources. Both are
stated as gaps rather than papered over.
