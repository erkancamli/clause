"""Reading the world from the people who measure it.

Every fixture in tests/feeds is a response actually fetched from the agency
that serves it, trimmed to the records these tests read. They are the
6 February 2023 Kahramanmaras sequence, because it is the event this product
exists for and because the three agencies that measured it do not agree about
it -- which is the whole reason this package is more than one HTTP call.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from clause.oracle import Observation, digest_of
from clause.oracle import quake
from clause.oracle.agreement import TOLERANCE, agree, read_from
from clause.oracle.events import SAME_KM, SAME_SECONDS, events, largest, same_event

FEEDS = pathlib.Path(__file__).parent / "feeds"
PAZARCIK = 1675646252.0        # 2023-02-06 01:17:32 UTC
ELBISTAN = 1675679087.0        # 2023-02-06 10:24:47 UTC
FETCHED = 1790000000.0


def readings() -> list[Observation]:
    out: list[Observation] = []
    for name, parse in (("usgs", quake.read_usgs), ("afad", quake.read_afad),
                        ("emsc", quake.read_emsc)):
        body = (FEEDS / f"{name}_kahramanmaras.json").read_bytes()
        out += parse(body, f"https://example.invalid/{name}", now=FETCHED)
    return out


def test_each_agency_is_parsed_from_what_it_actually_sent() -> None:
    by_source = {o.source: o for o in readings() if abs(o.measured_at - PAZARCIK) < 60}
    assert set(by_source) == {"USGS", "AFAD", "EMSC"}
    assert by_source["USGS"].value == 7.8 and by_source["USGS"].scale == "mww"
    assert by_source["EMSC"].value == 7.8
    assert by_source["AFAD"].value == 7.7 and by_source["AFAD"].record_id == "543428"


def test_afad_publishes_utc_and_reading_it_as_local_would_move_every_settlement() -> None:
    """AFAD writes its times without a zone, which invites the wrong guess.

    Its own record of the Pazarcik earthquake reads 2023-02-06T01:17:32 and
    USGS independently puts the event at 01:17:34.342 UTC. Reading AFAD as
    Turkish local time would place it three hours earlier, which is enough to
    put an event on the wrong side of a waiting period.

    The two and a bit seconds between them are not an error either: an origin
    time is a solution to an inverse problem and the agencies solve it
    differently. That is why events are matched within a minute rather than
    within a second.
    """
    afad = [o for o in readings() if o.source == "AFAD"]
    biggest = max(afad, key=lambda o: o.value)
    assert biggest.measured_at == pytest.approx(PAZARCIK, abs=1.0)
    usgs = max((o for o in readings() if o.source == "USGS"), key=lambda o: o.value)
    gap = abs(biggest.measured_at - usgs.measured_at)
    assert gap < 10.0, "seconds apart, which is two agencies solving for an origin"
    assert gap < 3600.0 * 2, "and nowhere near the three hours a local reading would give"


def test_three_agencies_do_not_agree_and_the_reading_says_so() -> None:
    """USGS and EMSC say 7.8 for Pazarcik, AFAD says 7.7. For Elbistan USGS and
    EMSC say 7.5 and AFAD says 7.6. A policy written at 7.6 pays on one
    official source and not on another, and pretending otherwise is how a
    parametric product ends up in front of a regulator."""
    for at, expected in ((PAZARCIK, 7.8), (ELBISTAN, 7.5)):
        group = [o for o in readings() if abs(o.measured_at - at) < 60]
        assert len({o.value for o in group}) > 1, "the disagreement is the point"
        reading = read_from(group, peril="earthquake", primary="USGS")
        assert reading.value == expected, "the primary's number, not an average"
        assert reading.settles, reading.why
        assert reading.spread == pytest.approx(0.1, abs=0.001)
        assert len(reading.observations) == 3


def test_an_average_of_two_official_numbers_is_a_number_nobody_published() -> None:
    group = [o for o in readings() if abs(o.measured_at - PAZARCIK) < 60]
    reading = read_from(group, peril="earthquake", primary="AFAD")
    assert reading.value == 7.7, "the primary is the primary, whoever it is"
    assert reading.value in {o.value for o in group}


def test_sources_too_far_apart_hold_the_settlement_instead_of_picking_a_side() -> None:
    def one(source: str, value: float) -> Observation:
        return Observation(source=source, value=value, unit="magnitude",
                           measured_at=PAZARCIK, retrieved_at=FETCHED,
                           url="u", digest=digest_of(b""), latitude=37.2, longitude=37.0)
    close = read_from([one("USGS", 6.1), one("AFAD", 6.0)], peril="earthquake", primary="USGS")
    assert close.settles
    apart = read_from([one("USGS", 6.1), one("AFAD", 5.8)], peril="earthquake", primary="USGS")
    assert not apart.settles
    assert "do not agree" in apart.why and "5.8" in apart.why and "6.1" in apart.why


def test_a_country_with_one_agency_is_not_treated_as_a_disagreement() -> None:
    lone = [o for o in readings() if o.source == "USGS" and abs(o.measured_at - PAZARCIK) < 60]
    reading = read_from(lone, peril="earthquake", primary="USGS")
    assert reading.settles and reading.spread == 0.0
    assert "nothing to check it against" in reading.why


def test_two_earthquakes_two_minutes_apart_are_two_earthquakes() -> None:
    """The 7.5 at 10:24:47 and the 6.0 at 10:26:48 on the same morning. Any
    window wide enough to absorb the agencies' disagreement about the first is
    wide enough to swallow the second, so location separates them."""
    grouped = events(readings())
    assert len(grouped) == 5, [round(max(o.value for o in g), 1) for g in grouped]
    biggest = largest(readings())
    assert {o.source for o in biggest} == {"USGS", "AFAD", "EMSC"}
    assert max(o.value for o in biggest) == 7.8
    elbistan = next(g for g in grouped if abs(g[0].measured_at - ELBISTAN) < 60)
    assert max(o.value for o in elbistan) == 7.6      # AFAD's, and it is the same event
    assert all(abs(o.measured_at - ELBISTAN) < SAME_SECONDS for o in elbistan)


def test_an_epicentre_is_an_estimate_so_matching_is_generous_in_space() -> None:
    """The three agencies put the same earthquake as much as twelve kilometres
    apart. A rule tight enough to reject that would split one event into three."""
    group = [o for o in readings() if abs(o.measured_at - PAZARCIK) < 60]
    spread = max(abs(a.latitude - b.latitude) for a in group for b in group)
    assert spread > 0.05, "they really do disagree about where"
    assert all(same_event(group[0], other) for other in group)
    assert SAME_KM > 12.0 and SAME_SECONDS <= 60.0


def test_every_reading_carries_what_it_takes_to_check_it() -> None:
    """A payout a person cannot check is a payout they have to trust."""
    for o in readings():
        assert o.source and o.url and o.digest and o.unit
        assert o.measured_at > 0 and o.retrieved_at == FETCHED
        assert len(o.digest) == 16
        body = o.to_dict()
        assert body["digest"] == o.digest and body["url"] == o.url


def test_usgs_is_still_revising_the_2023_earthquakes_in_2026() -> None:
    """Which is why no cover can settle on the finally revised value: finally
    never arrives. The 7.8 was last revised on 13 April 2026, three years and
    two months after it happened."""
    usgs = [o for o in readings() if o.source == "USGS"]
    biggest = max(usgs, key=lambda o: o.value)
    assert biggest.revised_at > biggest.measured_at + 3 * 365 * 86400
    revised = dt.datetime.fromtimestamp(biggest.revised_at, dt.timezone.utc)
    assert revised.year >= 2026


def test_a_quarry_blast_is_not_an_earthquake() -> None:
    body = json.loads((FEEDS / "usgs_kahramanmaras.json").read_bytes())
    body["features"][0]["properties"]["type"] = "quarry blast"
    kept = quake.read_usgs(json.dumps(body).encode(), "u", now=FETCHED)
    assert len(kept) == len(body["features"]) - 1


def test_no_source_answered_is_not_a_reading_of_zero() -> None:
    verdict = agree([], peril="earthquake")
    assert not verdict.agreed and "no source answered" in verdict.why
    reading = read_from([], peril="earthquake", primary="USGS")
    assert not reading.settles and reading.value == 0.0


def test_every_peril_names_how_far_apart_its_sources_may_be() -> None:
    from clause.perils import REGISTRY
    for key in REGISTRY:
        assert key in TOLERANCE, f"{key} has no agreement tolerance"
        assert TOLERANCE[key] > 0
