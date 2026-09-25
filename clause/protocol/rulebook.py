"""The calculation agent's rulebook: how a reading becomes the number a
policy settles on, written down as a policy term.

A parametric policy is only as good as the answer to five questions,
asked before anything happens: which source is read, and which stands in
when it is silent; what counts as the final figure and when it is frozen,
since agencies revise; what a reading has to pass before it is believed;
how long the policyholder has to object; and what happens if the
publisher goes away. Cat bonds answer these in a calculation agent
agreement that runs to pages. Here each peril answers them in a few
lines that go into every contract and onto a page anyone can read, and
the chain's own attestation rule (validators, quorum, median, dispersion)
is quoted beside them, because that is the part a person can check.
"""

from __future__ import annotations

from typing import Any

OBJECTION_DAYS = 30
SUCCESSOR_NOTICE_DAYS = 7
VERSION = "2026-09"

SUCCESSOR_RULE = (
    f"If the primary publisher stops publishing or changes its method, the operator names a successor source of "
    f"equal standing from the fallback chain, announces it on the Proof page, and the change takes effect "
    f"{SUCCESSOR_NOTICE_DAYS} days later for readings after that day; the policy's threshold, unit and steps do not change."
)
ARCHIVE_RULE = (
    "Every reading the validators reported, the figure the aggregator settled on and the source's response as "
    "received are kept with the settlement and can be read back, so the result can be reproduced from the "
    "inputs rather than taken on trust."
)

RULES: dict[str, dict[str, Any]] = {
    "earthquake": {
        "title": "Earthquake",
        "index": "Magnitude within the radius (Mw, the moment magnitude), or the shaking intensity at the address (MMI) where the policy says so",
        "primary": "The national seismic network (in Türkiye AFAD, with Kandilli as a second reading), the reviewed event page. Where this protocol does not yet read a national network, the primary is USGS and the policy says so rather than naming a source nobody asks",
        "fallbacks": [
            "USGS ShakeMap and the USGS reviewed magnitude for the same event, when the national network has not published within 24 hours",
            "A modelled footprint from the catalogue magnitude and the ground-motion model this protocol prices with, only when neither network has published within 72 hours; marked as modelled on the Proof page",
        ],
        "final_data": "The reviewed magnitude as published 7 days after the origin time; for shaking, the ShakeMap or national shaking map version current 72 hours after the origin time",
        "freeze_hours": 168,
        "waiting": (
            "Cover starts 3 days after it is bought and then runs its full term. An earthquake whose origin time falls in those 3 days pays nothing, and the policy is not cancelled by it: the cover starts on its day and the term is unchanged. The wait is there because an aftershock sequence is public knowledge from the moment the mainshock is felt, and cover bought on that knowledge is priced for someone who does not have it. It is deliberately short: an aftershock sequence stays elevated for weeks and this does not wait it out, so the pool carries the rest of that sequence rather than the buyer"
        ),
        "criteria": [
            "The event's origin time falls inside the policy term",
            "The epicentre or the address falls inside the radius or the grid cell the policy names",
            "The magnitude or intensity is the reviewed figure, not an automatic first estimate; an automatic figure may arm the policy but does not settle it",
            "Two independent networks within 0.3 magnitude units, or one network 7 days after the event",
        ],
    },
    "storm": {
        "title": "Storm",
        "index": "Daily maximum sustained wind at the address, km/h",
        "primary": "The ERA5 reanalysis for the cell the address falls in, with ERA5-Land read against it, taken from the archive rather than the forecast. This protocol does not yet read a national meteorological service, so this is a model's estimate for a cell and not a station at the address, and the policy says so rather than naming a station nobody asks",
        "fallbacks": [
            "NASA POWER (MERRA-2) at the address's grid cell, when the station's daily value is missing",
            "ERA5 at the same cell, quantile-mapped to the station's own climatology, when both are missing for the day",
        ],
        "final_data": "The station's quality-controlled daily value as published 14 days after the day; a reanalysis figure is final when the month is published",
        "freeze_hours": 336,
        "waiting": (
            "Cover starts 10 days after it is bought and then runs its full term. A day inside those 10 days pays nothing however hard the wind blows, and the policy is not cancelled by it. The wait is longer than any weather forecast can see, so the cover is bought against the weather and not against the news"
        ),
        "criteria": [
            "The day falls inside the policy term",
            "The station is within 25 km of the address, or the grid cell contains it",
            "The value passes the service's own quality flags; a flagged value is not used",
            "A reanalysis value is only used after quantile mapping to the station, since reanalyses under-read strong wind",
        ],
    },
    "vehicle_flood": {
        "title": "Vehicle flood",
        "index": "Daily rainfall at the address, mm in 24 hours",
        "primary": "The ERA5 reanalysis for the cell the address falls in, with ERA5-Land read against it, taken from the archive rather than the forecast. This protocol does not yet read a national meteorological service, so this is a model's estimate for a cell and not a station at the address, and the policy says so rather than naming a station nobody asks",
        "fallbacks": [
            "NASA POWER (MERRA-2) at the address's grid cell, when the station's daily total is missing",
            "ERA5 at the same cell, quantile-mapped to the station's own climatology, when both are missing for the day",
        ],
        "final_data": "The station's quality-controlled daily total as published 14 days after the day",
        "freeze_hours": 336,
        "waiting": (
            "Cover starts 10 days after it is bought and then runs its full term. A day inside those 10 days pays nothing however much rain falls, and the policy is not cancelled by it. The wait is longer than any rainfall warning runs ahead of the rain"
        ),
        "criteria": [
            "The day falls inside the policy term",
            "The station is within 25 km of the address, or the grid cell contains it",
            "The value passes the service's own quality flags",
            "The vehicle's address is the one on the policy; the reading is for that place whatever the vehicle did that day",
        ],
    },
    "drought": {
        "title": "Drought",
        "index": "Cumulative rainfall at the station over the season, mm",
        "primary": "The national meteorological service's station named on the policy, its cumulative total",
        "fallbacks": [
            "The service's nearest neighbouring station, distance-weighted, when the named station has a gap of more than 5 days",
            "ERA5 at the station's cell, quantile-mapped, when the gap is longer than 30 days",
        ],
        "final_data": "The cumulative total as published 14 days after the season ends",
        "freeze_hours": 336,
        "waiting": (
            "Cover starts on the day the station's season opens, and the season it measures is that one, from its first day to its last. Sales for a season close 15 days before it opens: a season already under way cannot be insured, because part of its rain has already fallen and both sides can see how much, and cover bought after the deadline is cover for the following season. The deadline and the season's own dates are on the policy before it is bought"
        ),
        "criteria": [
            "The season's start and end are the policy's, and they are calendar dates fixed for the station, not counted from the day the cover was bought",
            "Gaps of up to 5 days are filled from the neighbouring station; longer gaps switch the source for the gap only",
            "A total that falls below the station's lowest recorded season is checked against the neighbour before it settles",
        ],
    },
    "flight_delay": {
        "title": "Flight delay",
        "index": "Arrival delay of the flight named on the policy, minutes after the scheduled arrival",
        "primary": "The airline's or the air navigation service's published arrival time for that flight number and date",
        "fallbacks": [
            "An independent flight status aggregator (ADS-B based) for the same flight, when the airline has not published within 12 hours",
            "The airport's arrival record, when neither has published within 48 hours",
        ],
        "final_data": "The arrival time as published 3 days after the scheduled date; a cancellation or a diversion counts as the longest delay the policy pays on",
        "freeze_hours": 72,
        "waiting": (
            "There is no waiting period, because the cover names one flight and a wait would leave that flight outside the cover rather than inside it. Instead the cover has to be bought at least 24 hours before the scheduled departure, counted from the time on the ticket in the clock of the airport the flight leaves from. Inside that last day the aircraft is assigned and the crew is rostered, and a schedule already slipping can be read off any flight tracker, so cover bought there is bought on what the price does not know"
        ),
        "criteria": [
            "The flight number, date and scheduled departure are the policy's; a rebooking onto another flight is not this flight",
            "Arrival means the aircraft's gate arrival, not touchdown, where both are published",
            "Two sources within 10 minutes of each other, or one source 3 days after the date",
        ],
    },
}


def for_peril(key: str, *, deadline_days: int | None = None, on_missing_data: str = "",
              attestation: str = "") -> dict[str, Any]:
    """The rulebook for one peril, with what the chain and the source add."""
    base = RULES.get(key)
    if base is None:
        raise KeyError(key)
    return {
        "peril": key, **base, "objection_days": OBJECTION_DAYS, "successor": SUCCESSOR_RULE, "archive": ARCHIVE_RULE,
        "deadline_days": deadline_days, "on_missing_data": on_missing_data, "attestation": attestation,
        "version": VERSION,
    }


def contract_lines(key: str, *, deadline_days: int | None = None, on_missing_data: str = "",
                   attestation: str = "") -> list[str]:
    """The rulebook as a contract section, four spaces in like the rest."""
    try:
        r = for_peril(key, deadline_days=deadline_days, on_missing_data=on_missing_data, attestation=attestation)
    except KeyError:
        return []
    lines = [
        "10. How the reading is determined (calculation rules)",
        f"    Index: {r['index']}.",
        f"    Primary source: {r['primary']}.",
    ]
    for i, fb in enumerate(r["fallbacks"], start=1):
        lines.append(f"    Fallback {i}: {fb}.")
    lines.append(f"    Final figure: {r['final_data']}; the figure is frozen {r['freeze_hours'] // 24} days after the event and later revisions do not reopen a settlement.")
    for c in r["criteria"]:
        lines.append(f"    Test: {c}.")
    if r.get("waiting"):
        lines.append(f"    When the cover applies: {r['waiting']}.")
    if attestation:
        lines.append(f"    Attestation: {attestation}")
    if deadline_days:
        lines.append(f"    Silence: if no final figure has been published {deadline_days} days after the term ends, {on_missing_data or 'the policy ends and the premium is returned'}.")
    lines.append(f"    Objection: the policyholder may object to a settlement on the Proof page within {OBJECTION_DAYS} days of it, naming the reading they dispute; the operator answers with the archived inputs.")
    lines.append(f"    Successor source: {SUCCESSOR_RULE}")
    lines.append(f"    Archive: {ARCHIVE_RULE}")
    lines.append(f"    Rulebook version {VERSION}.")
    return lines
