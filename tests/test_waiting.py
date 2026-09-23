"""The waiting period: the days between buying cover and the cover starting.

The price is the chance of an event in an ordinary term, worked out for someone
who does not know whether one is coming. Forecasts break that. A named storm is
on the news a week before it lands; an aftershock sequence is public knowledge
from the moment the mainshock is felt; a dry season is half over before anyone
can see it; and an airline knows its aircraft is late hours before a passenger
does. Cover bought inside those windows is bought by someone who knows more
than the price does, and the pool pays the difference on every such policy.

Each peril answers that in the way its own index allows: four wait, drought
closes sales before the season opens, and flight refuses the sale inside the
last day because a wait would leave the insured flight outside the cover.
"""

from __future__ import annotations

import datetime as dt

import pytest

from clause.chain import Chain, ChainConfig
from clause.perils import get_peril
from clause.perils.flight import BOOK_AHEAD_HOURS
from clause.perils.weather import STATIONS
from clause.pricing import PricingEngine
from clause.protocol import Pool, PolicyStatus
from clause.protocol.policy import build_policy
from clause.protocol.rulebook import RULES
from conftest import FLIGHT_DATE

DAY = 86400.0

SUBJECTS = {
    "earthquake": {"latitude": 41.0, "longitude": 29.0, "radius_km": 50.0},
    "storm": {"latitude": 41.0, "longitude": 29.0},
    "vehicle_flood": {"latitude": 41.0, "longitude": 29.0},
    "drought": {"station": "TR-KONYA", "distance_km": 6.0, "hectares": 50.0},
    "flight_delay": {"route": "TK-IST-LHR", "flight_number": "TK1979",
                     "departure_date": FLIGHT_DATE, "departure_time": "09:30"},
}
WAITS = {"earthquake": 3.0, "storm": 10.0, "vehicle_flood": 10.0,
         "drought": 15.0, "flight_delay": 0.0}


def written(peril_key: str, *, now: float | None = None, term_days: float = 150.0):
    return build_policy(
        peril_key=peril_key, subject=dict(SUBJECTS[peril_key]), limit=10_000.0,
        term_days=term_days, holder="holder", premium=100.0, expected_loss=50.0,
        risk_load=10.0, expense_load=10.0, marginal_capital=1.0, now=now,
    )


# ---------------------------------------------------------------------------
# What each peril declares
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(WAITS))
def test_every_peril_declares_its_waiting_period(key: str) -> None:
    assert get_peril(key).waiting_days == WAITS[key]


@pytest.mark.parametrize("key", sorted(WAITS))
def test_the_rulebook_says_the_same_number_of_days(key: str) -> None:
    """The contract and the code cannot drift: whatever a peril waits, the
    sentence that goes into every policy has to name the same figure."""
    said = RULES[key]["waiting"]
    days = int(WAITS[key])
    if days:
        assert f"{days} days" in said, said
    else:
        assert "no waiting period" in said
        assert f"{BOOK_AHEAD_HOURS} hours" in said


# ---------------------------------------------------------------------------
# What a policy does with it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["earthquake", "storm", "vehicle_flood"])
def test_cover_starts_after_the_wait_and_keeps_its_whole_term(key: str) -> None:
    now = dt.datetime(2026, 11, 3, 9, 0, tzinfo=dt.timezone.utc).timestamp()
    policy = written(key, now=now, term_days=365.0)
    assert policy.bought_at == now
    assert policy.starts_at == pytest.approx(now + WAITS[key] * DAY)
    # The wait moves the term, it does not eat into it.
    assert policy.ends_at - policy.starts_at == pytest.approx(365.0 * DAY)


def test_a_flight_starts_the_moment_it_is_bought() -> None:
    """The one peril that cannot wait: the cover names a flight, and a wait
    would put that flight outside the cover instead of inside it."""
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    policy = written("flight_delay", now=now, term_days=2.0)
    assert policy.starts_at == pytest.approx(now)


# ---------------------------------------------------------------------------
# Drought: a season is a range of dates, and sales for it close before it opens
# ---------------------------------------------------------------------------


def at(year: int, month: int, day: int) -> float:
    return dt.datetime(year, month, day, 9, 0, tzinfo=dt.timezone.utc).timestamp()


def test_a_station_season_is_a_range_of_calendar_dates() -> None:
    station = STATIONS["TR-KONYA"]
    opens, closes = station.window(2027)
    assert (opens.month, opens.day) == station.opens
    assert (closes - opens).days == station.window_days - 1
    # The words on the policy are read off those dates rather than typed
    # beside them, so the two cannot disagree.
    assert station.season == f"{opens:%B} to {closes:%B}"


def test_drought_cover_starts_on_the_day_the_season_opens() -> None:
    drought = get_peril("drought")
    subject = dict(SUBJECTS["drought"])
    bought = at(2026, 10, 12)
    policy = written("drought", now=bought, term_days=150.0)
    opens, _ = drought.window_for(subject, now=bought)
    assert opens == dt.date(2027, 4, 1)
    assert dt.datetime.fromtimestamp(policy.starts_at, dt.timezone.utc).date() == opens
    assert dt.datetime.fromtimestamp(policy.starts_at, dt.timezone.utc).hour == 0


def test_sales_close_fifteen_days_before_the_season_opens() -> None:
    drought = get_peril("drought")
    subject = dict(SUBJECTS["drought"])
    assert drought.refuse_to_write(subject, now=at(2027, 3, 17)) == ""
    refused = drought.refuse_to_write(subject, now=at(2027, 3, 18))
    assert "closed on 17 March 2027" in refused
    with pytest.raises(ValueError, match="closed on 17 March 2027"):
        written("drought", now=at(2027, 3, 18))


def test_a_season_already_under_way_cannot_be_insured() -> None:
    """Half its rain has fallen and both sides can see how much. The cover on
    offer in June is cover for the season after this one."""
    drought = get_peril("drought")
    subject = dict(SUBJECTS["drought"])
    opens, _ = drought.window_for(subject, now=at(2027, 6, 1))
    assert opens == dt.date(2028, 4, 1)
    assert drought.refuse_to_write(subject, now=at(2027, 6, 1)) == ""


# ---------------------------------------------------------------------------
# Flight: twenty-four hours, counted in the departure airport's own clock
# ---------------------------------------------------------------------------


def test_a_flight_is_refused_inside_the_last_day() -> None:
    flight = get_peril("flight_delay")
    subject = flight.validate_subject({
        "route": "TK-IST-LHR", "flight_number": "TK1979",
        "departure_date": "2027-02-10", "departure_time": "09:00",
    })
    # Istanbul is UTC+3 all year, so 09:00 there is 06:00 UTC.
    leaves = dt.datetime(2027, 2, 10, 6, 0, tzinfo=dt.timezone.utc).timestamp()
    assert flight.departs_at(subject) == leaves
    assert flight.refuse_to_write(subject, now=leaves - 25 * 3600) == ""
    assert "24 hours" in flight.refuse_to_write(subject, now=leaves - 23 * 3600)
    assert "already left" in flight.refuse_to_write(subject, now=leaves + 60)


def test_the_hours_are_counted_where_the_flight_leaves_from() -> None:
    """A date on its own is a different instant in every timezone, which is
    what the departure time is there to settle. London in February is on UTC
    and Istanbul is three hours ahead of it, so the same clock time on the
    same day is two different moments."""
    flight = get_peril("flight_delay")
    common = {"flight_number": "TK1979", "departure_date": "2027-02-10",
              "departure_time": "09:00"}
    istanbul = flight.departs_at(flight.validate_subject({"route": "TK-IST-LHR", **common}))
    london = flight.departs_at(flight.validate_subject(
        {"route": "BA-LHR-IST", "flight_number": "BA0676",
         "departure_date": "2027-02-10", "departure_time": "09:00"}))
    assert london - istanbul == 3 * 3600


def test_a_flight_subject_carries_the_scheduled_time() -> None:
    flight = get_peril("flight_delay")
    subject = flight.validate_subject({
        "route": "TK-IST-LHR", "flight_number": "TK1979",
        "departure_date": FLIGHT_DATE, "departure_time": "9:05",
    })
    assert subject["departure_time"] == "09:05"
    assert "09:05" in flight.describe_subject(subject)
    with pytest.raises(ValueError, match="HH:MM"):
        flight.validate_subject({"route": "TK-IST-LHR", "flight_number": "TK1979",
                                 "departure_date": FLIGHT_DATE, "departure_time": "half nine"})


# ---------------------------------------------------------------------------
# What the chain does with an event inside the wait
# ---------------------------------------------------------------------------


KADIKOY = "api.seismic.example/v1/max-magnitude?lat=40.99&lon=29.03&radius_km=50"


def built() -> tuple[Pool, Chain]:
    pool = Pool(engine=PricingEngine(trials=600, seed=4))
    pool.deposit("lp", 20_000_000.0)
    return pool, Chain(pool, ChainConfig(seed=4))


def test_an_event_inside_the_wait_pays_nothing_and_ends_nothing() -> None:
    pool, chain = built()
    policy = pool.write(peril_key="earthquake", limit=100_000.0, term_days=365.0,
                        holder="holder",
                        subject={"location": "IST-KADIKOY", "radius_km": 50.0})
    chain.register(policy)
    assert chain.world_now(policy) < policy.starts_at

    chain.attest(KADIKOY, "max_magnitude", 7.2)
    for _ in range(60):
        chain.produce_block()

    # Not paid, and not closed either: the cover starts on the day the document
    # names, whatever the days before it brought.
    assert pool.policies[policy.policy_id].status is PolicyStatus.ACTIVE
    assert policy.payout == 0.0
    assert policy.metadata.get("held_in_waiting")


def test_a_reading_left_standing_from_the_wait_does_not_settle_it_later() -> None:
    """The subtle half. A rainfall source keeps the largest daily total it has
    seen and goes on reporting every day after it, so the downpour that fell
    during the waiting period is still the figure standing in the reading on
    the morning the cover starts. Telling one from the other means knowing when
    the maximum was last raised, which is not when the source last spoke."""
    pool, chain = built()
    policy = pool.write(peril_key="vehicle_flood", limit=50_000.0, term_days=365.0,
                        holder="holder", subject=dict(SUBJECTS["vehicle_flood"]))
    armed = chain.register(policy)

    # A downpour on the day the cover was bought, well inside the ten day wait.
    chain.attest(policy.data_reference, "rain_24h_mm", 400.0, final=False)
    reading = chain.readings[policy.data_reference]
    assert float(reading.fields["rain_24h_mm"]) > 300.0

    while chain.world_now(policy) < policy.starts_at:
        chain.produce_block()
    for _ in range(40):
        chain.produce_block()

    # The cover has started and the figure standing in the reading is far above
    # the trigger, and it settles nothing, because the day it records is not a
    # day of this cover.
    assert chain.world_now(policy) >= policy.starts_at
    assert chain._too_early(armed)
    assert pool.policies[policy.policy_id].status is PolicyStatus.ACTIVE
    assert policy.payout == 0.0

    # The source reporting again is not the same as a bigger day: an ordinary
    # wet Tuesday moves when the source last spoke and nothing else.
    reading.attested_at = chain.timestamp
    assert chain._too_early(armed)

    # A day that does beat it, after the cover started, is this cover's.
    reading.peak_at = chain.timestamp
    assert not chain._too_early(armed)


def test_the_wait_reads_the_clock_a_policy_was_written_in() -> None:
    """Cover a person bought keeps the term on its document: their year is a
    year, however fast the demonstration's world is turning. So the day a
    source's running maximum was raised has to be read on that same clock, and
    not on the chain's own, which stands a long way behind it. Read on the
    wrong one, such a policy is inside its waiting period for ever."""
    pool, chain = built()
    policy = pool.write(peril_key="vehicle_flood", limit=50_000.0, term_days=365.0,
                        holder="holder", subject=dict(SUBJECTS["vehicle_flood"]))
    policy.metadata["interest"] = {"what": "a car", "value": 300_000.0}
    armed = chain.register(policy)

    # A downpour today, on cover whose ten days are still to run.
    chain.attest(policy.data_reference, "rain_24h_mm", 400.0, final=False)
    assert chain._too_early(armed)

    # The same downpour, on cover that started yesterday.
    policy.starts_at = policy.bought_at - DAY
    assert not chain._too_early(armed)
