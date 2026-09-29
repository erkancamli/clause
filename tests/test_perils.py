"""The perils: what they pay, and what they believe about the world.

The structure and the model are tested apart, because they are separate things.
A payout curve is a contract and has to do exactly what it says at every index
value. A probability model is a view, and what is checked there is that it is
internally consistent and lands in the range the published science does.
"""

from __future__ import annotations

import math

import pytest

from clause.perils import (
    DROUGHT,
    EARTHQUAKE,
    FLIGHT_DELAY,
    Breakpoint,
    Direction,
    PayoutCurve,
    Shape,
    curve_from_spec,
    get_peril,
)
from clause.perils.flight import CANCELLATION_MINUTES, ROUTES
from clause.perils.quake import ALLOWED_RADII_KM, BACKGROUND_MAXIMUM, LOCATIONS
from clause.perils.weather import STATIONS
from conftest import FLIGHT_DATE


# ---------------------------------------------------------------------------
# Payout curves
# ---------------------------------------------------------------------------


def step_curve() -> PayoutCurve:
    return curve_from_spec([(100.0, 0.25), (200.0, 0.60), (300.0, 1.00)])


def test_step_curve_pays_nothing_below_attachment() -> None:
    curve = step_curve()
    assert curve.payout(0.0, 1000) == 0.0
    assert curve.payout(99.9, 1000) == 0.0


def test_step_curve_pays_each_band_exactly() -> None:
    curve = step_curve()
    assert curve.payout(100.0, 1000) == 250.0
    assert curve.payout(199.9, 1000) == 250.0
    assert curve.payout(200.0, 1000) == 600.0
    assert curve.payout(300.0, 1000) == 1000.0
    assert curve.payout(9999.0, 1000) == 1000.0


def test_step_curve_expected_share_is_the_layer_sum() -> None:
    """The decomposition the pricing engine relies on, checked by hand."""
    curve = step_curve()
    probabilities = {100.0: 0.40, 200.0: 0.10, 300.0: 0.02}
    expected = 0.25 * 0.40 + (0.60 - 0.25) * 0.10 + (1.00 - 0.60) * 0.02
    assert curve.expected_share(lambda level: probabilities[level]) == pytest.approx(expected)


def test_ramp_curve_interpolates() -> None:
    curve = curve_from_spec(
        [(100.0, 0.0), (200.0, 1.0)], shape=Shape.RAMP
    )
    assert curve.payout(100.0, 1000) == 0.0
    assert curve.payout(150.0, 1000) == pytest.approx(500.0)
    assert curve.payout(175.0, 1000) == pytest.approx(750.0)
    assert curve.payout(200.0, 1000) == 1000.0
    assert curve.payout(260.0, 1000) == 1000.0


def test_downward_curve_pays_as_the_index_falls() -> None:
    curve = curve_from_spec(
        [(80.0, 0.0), (40.0, 1.0)], shape=Shape.RAMP, direction=Direction.BELOW
    )
    assert curve.payout(90.0, 1000) == 0.0
    assert curve.payout(80.0, 1000) == 0.0
    assert curve.payout(60.0, 1000) == pytest.approx(500.0)
    assert curve.payout(40.0, 1000) == 1000.0
    assert curve.payout(10.0, 1000) == 1000.0


def test_ramp_expected_share_sits_between_its_bounds() -> None:
    """A ramp must pay less than a step at the same exhaustion, and more than
    one attaching only at the top."""
    ramp = curve_from_spec([(100.0, 0.0), (200.0, 1.0)], shape=Shape.RAMP)

    def exceedance(level: float) -> float:
        return max(0.0, min(1.0, (300.0 - level) / 300.0))

    share = ramp.expected_share(exceedance)
    assert exceedance(200.0) < share < exceedance(100.0)


def test_curve_rejects_decreasing_payouts() -> None:
    with pytest.raises(ValueError, match="must not decrease"):
        PayoutCurve(breakpoints=(Breakpoint(1.0, 0.8), Breakpoint(2.0, 0.4)))


def test_curve_rejects_breakpoints_running_the_wrong_way() -> None:
    with pytest.raises(ValueError, match="direction"):
        PayoutCurve(
            breakpoints=(Breakpoint(2.0, 0.1), Breakpoint(1.0, 0.9)),
            direction=Direction.ABOVE,
        )


def test_breakpoint_rejects_a_share_outside_the_limit() -> None:
    with pytest.raises(ValueError):
        Breakpoint(1.0, 1.4)


def test_curve_describes_itself_in_words() -> None:
    lines = step_curve().describe("minutes")
    assert len(lines) == 3
    assert "100" in lines[0] and "25%" in lines[0]


# ---------------------------------------------------------------------------
# Flight
# ---------------------------------------------------------------------------


def flight_subject() -> dict:
    return FLIGHT_DELAY.validate_subject(
        {"route": "TK-IST-LHR", "flight_number": "TK1979", "departure_date": FLIGHT_DATE}
    )


def test_flight_takes_any_two_airports() -> None:
    """There is no list of routes to be off any more. Six of them used to be
    the whole offer, which is not a product: a traveller whose flight was not
    one of them had nothing to insure. What is refused now is a code that is
    not an airport, and a flight that lands where it left."""
    both = FLIGHT_DELAY.validate_subject({
        "origin": "gru", "destination": "GIG", "flight_number": "G31234",
        "departure_date": FLIGHT_DATE, "departure_time": "07:15",
    })
    assert both["origin"] == "GRU" and both["destination"] == "GIG"
    assert not FLIGHT_DELAY.published(both)
    assert 300 < FLIGHT_DELAY.sector_km(both) < 400

    with pytest.raises(ValueError, match="not an airport code"):
        FLIGHT_DELAY.validate_subject({"origin": "ZZZ", "destination": "LHR",
                                       "flight_number": "X1", "departure_date": FLIGHT_DATE})
    with pytest.raises(ValueError, match="one airport and lands at another"):
        FLIGHT_DELAY.validate_subject({"origin": "IST", "destination": "IST",
                                       "flight_number": "X1", "departure_date": FLIGHT_DATE})


def test_a_flight_cover_written_before_the_catalogue_still_reads() -> None:
    """Policies sold when the six routes were the offer name a route and no
    airports. They still have to describe and settle the same way."""
    old = FLIGHT_DELAY.validate_subject(
        {"route": "TK-IST-LHR", "flight_number": "TK1979", "departure_date": FLIGHT_DATE}
    )
    assert old["origin"] == "IST" and old["destination"] == "LHR"
    assert FLIGHT_DELAY.published(old)


def test_flight_requires_a_number_and_a_date() -> None:
    with pytest.raises(ValueError):
        FLIGHT_DELAY.validate_subject({"route": "TK-IST-LHR", "flight_number": "", "departure_date": "d"})
    with pytest.raises(ValueError):
        FLIGHT_DELAY.validate_subject({"route": "TK-IST-LHR", "flight_number": "TK1", "departure_date": ""})


def test_flight_exceedance_is_monotone() -> None:
    exceedance = FLIGHT_DELAY.exceedance(flight_subject(), 2)
    previous = 1.1
    for level in (1, 30, 60, 120, 240, 600, 1439, CANCELLATION_MINUTES):
        value = exceedance(level)
        assert 0.0 <= value <= 1.0
        assert value <= previous + 1e-12
        previous = value


def test_flight_cancellation_sits_at_the_top_of_the_index() -> None:
    stats = ROUTES["TK-IST-LHR"]
    exceedance = FLIGHT_DELAY.exceedance(flight_subject(), 2)
    assert exceedance(CANCELLATION_MINUTES) == pytest.approx(stats.cancellation_rate)


def test_flight_trigger_probability_is_plausible() -> None:
    """A two hour delay is uncommon but not rare, which is what makes the
    product worth buying and affordable to sell."""
    curve = FLIGHT_DELAY.default_curve()
    probability = FLIGHT_DELAY.trigger_probability(flight_subject(), curve, 2)
    assert 0.01 < probability < 0.12


def test_flight_predicate_reads_its_own_source() -> None:
    subject = flight_subject()
    curve = FLIGHT_DELAY.default_curve()
    predicate = FLIGHT_DELAY.predicate(subject, curve, "p1")
    assert FLIGHT_DELAY.data_source(subject).reference in predicate
    assert ">= 120" in predicate


# ---------------------------------------------------------------------------
# Drought
# ---------------------------------------------------------------------------


def drought_subject(distance: float = 8.0) -> dict:
    return DROUGHT.validate_subject(
        {"station": "TR-KONYA", "distance_km": distance, "hectares": 50.0}
    )


def test_drought_rejects_a_field_too_far_from_the_station() -> None:
    with pytest.raises(ValueError, match="sixty kilometres"):
        DROUGHT.validate_subject({"station": "TR-KONYA", "distance_km": 90.0, "hectares": 10.0})


def test_drought_rejects_a_zero_area() -> None:
    with pytest.raises(ValueError, match="area"):
        DROUGHT.validate_subject({"station": "TR-KONYA", "distance_km": 5.0, "hectares": 0.0})


def test_station_gamma_fit_reproduces_its_own_moments() -> None:
    """Method of moments, so shape times scale must return the mean."""
    for station in STATIONS.values():
        assert station.shape * station.scale == pytest.approx(station.normal_mm)
        variance = station.shape * station.scale ** 2
        cv = math.sqrt(variance) / station.normal_mm
        assert cv == pytest.approx(station.variability, rel=1e-9)


def test_drought_curve_converts_from_shares_to_millimetres() -> None:
    subject = drought_subject()
    station = DROUGHT.station(subject)
    in_mm = DROUGHT.curve_in_mm(subject, DROUGHT.default_curve())
    assert in_mm.attachment == pytest.approx(0.80 * station.normal_mm)
    assert in_mm.exhaustion == pytest.approx(0.40 * station.normal_mm)


def test_drought_exceedance_is_a_lower_tail() -> None:
    exceedance = DROUGHT.exceedance(drought_subject(), 150)
    assert exceedance(0.0) == 0.0
    previous = -1.0
    for level in (10, 40, 80, 120, 200, 400):
        value = exceedance(level)
        assert value >= previous
        previous = value
    assert exceedance(10_000) == pytest.approx(1.0, abs=1e-6)


def test_drought_trigger_is_near_the_gamma_at_eighty_percent() -> None:
    subject = drought_subject()
    in_mm = DROUGHT.curve_in_mm(subject, DROUGHT.default_curve())
    probability = DROUGHT.exceedance(subject, 150)(in_mm.attachment)
    # Below eighty percent of normal is a bad but not unusual season.
    assert 0.2 < probability < 0.5


def test_drought_basis_risk_falls_with_distance() -> None:
    _, near = DROUGHT.basis_risk_for(drought_subject(2.0))
    _, far = DROUGHT.basis_risk_for(drought_subject(45.0))
    assert near > far
    assert 0.0 < far < near <= 1.0


def test_drought_predicate_waits_for_the_window_to_close() -> None:
    """The guard that separates insurance from a bet on the weather so far."""
    subject = drought_subject()
    predicate = DROUGHT.predicate(subject, DROUGHT.default_curve(), "p1")
    assert "window_closed >= 1" in predicate
    assert "rainfall_mm <=" in predicate


# ---------------------------------------------------------------------------
# Earthquake
# ---------------------------------------------------------------------------


def quake_subject(location: str = "IST-KADIKOY", radius: float = 50.0) -> dict:
    return EARTHQUAKE.validate_subject({"location": location, "radius_km": radius})


def test_quake_rejects_an_unlisted_radius() -> None:
    with pytest.raises(ValueError, match="radius"):
        EARTHQUAKE.validate_subject({"location": "IST-KADIKOY", "radius_km": 37.0})


def test_gutenberg_richter_falls_by_about_ten_per_magnitude() -> None:
    """The relation the whole background model rests on.

    Checked well below the truncation, where the law is the law. Nearer the cap
    the truncated form falls away faster on purpose, which the next test covers.
    """
    subject = quake_subject()
    for magnitude in (4.0, 4.3, 4.6):
        here = EARTHQUAKE.background_rate(subject, magnitude)
        higher = EARTHQUAKE.background_rate(subject, magnitude + 1.0)
        assert 6.0 < here / higher < 18.0


def test_background_is_truncated_rather_than_running_forever() -> None:
    """Above the cap, a region's events belong to its mapped fault.

    An untruncated law would keep assigning background probability to
    magnitudes no diffuse source in the zone can produce, and double count
    against the characteristic term that already covers them.
    """
    subject = quake_subject()
    assert EARTHQUAKE.background_rate(subject, BACKGROUND_MAXIMUM) == 0.0
    assert EARTHQUAKE.background_rate(subject, 7.5) == 0.0

    near_cap = EARTHQUAKE.background_rate(subject, BACKGROUND_MAXIMUM - 0.1)
    well_below = EARTHQUAKE.background_rate(subject, BACKGROUND_MAXIMUM - 1.1)
    # The fall over that last magnitude is steeper than the plain law's ten.
    assert well_below / near_cap > 12.0


def test_background_scales_with_the_area_of_the_circle() -> None:
    small = EARTHQUAKE.background_rate(quake_subject(radius=25.0), 5.0)
    large = EARTHQUAKE.background_rate(quake_subject(radius=50.0), 5.0)
    assert large / small == pytest.approx(4.0, rel=1e-9)


def test_the_fault_scales_with_length_not_area() -> None:
    """A rupture is a line, so a wider circle buys more trace, not more area.

    Background seismicity scales with the square of the radius. If the fault did
    too, the model would be treating a line as a density. Doubling the radius
    here should roughly double the fault term while quadrupling the background.
    """
    # Düzce sits about seven kilometres from the trace, so both circles are
    # crossed by it and the comparison is about how the chord grows rather than
    # about the circle first reaching the fault at all.
    def at(radius: float) -> dict:
        return EARTHQUAKE.validate_subject(
            {"latitude": 40.84, "longitude": 31.16, "radius_km": radius}
        )

    small = EARTHQUAKE.characteristic_rate(at(25.0), 6.0)
    large = EARTHQUAKE.characteristic_rate(at(50.0), 6.0)
    assert large > small
    assert large / small < 3.0, "a line source must not scale with area"

    background_small = EARTHQUAKE.background_rate(at(25.0), 5.0)
    background_large = EARTHQUAKE.background_rate(at(50.0), 5.0)
    assert background_large / background_small == pytest.approx(4.0, rel=1e-6)


def test_a_tighter_radius_buys_less_of_the_fault() -> None:
    """The buyer's main lever on basis risk, and it is now continuous.

    Under the earlier model the fault was in or out of the circle, which made a
    49 km radius and a 51 km one wildly different prices for no physical reason.
    Here the radius buys a share of the trace, so the curve is smooth.
    """
    rates = [
        EARTHQUAKE.characteristic_rate(quake_subject("ADY-MERKEZ", radius), 7.0)
        for radius in (25.0, 50.0, 100.0)
    ]
    assert rates[0] < rates[1] < rates[2]
    assert all(rate > 0 for rate in rates)


def test_a_circle_far_from_every_trace_has_no_fault_term() -> None:
    """Konya sits over two hundred kilometres from the nearest mapped system."""
    subject = EARTHQUAKE.validate_subject(
        {"latitude": 37.87, "longitude": 32.49, "radius_km": 50}
    )
    assert EARTHQUAKE.characteristic_rate(subject, 6.0) == 0.0
    assert EARTHQUAKE.background_rate(subject, 5.0) > 0.0


def test_istanbul_return_periods_sit_in_the_published_range() -> None:
    """The reason the characteristic term exists.

    Published work puts a magnitude seven event near Istanbul on the order of
    a century. Background seismicity alone would say several centuries, which
    is the error this model is built to avoid.
    """
    subject = quake_subject()
    rows = {row["magnitude"]: row for row in EARTHQUAKE.hazard_table(subject)}
    assert 50.0 < rows[7.0]["return_period_years"] < 200.0
    assert 8.0 < rows[5.5]["return_period_years"] < 40.0
    # And the fault, not the background, is what carries the large magnitudes.
    assert rows[7.0]["characteristic_rate"] > rows[7.0]["background_rate"]


def test_a_quiet_place_is_far_quieter_than_a_fault_line(): 
    """The whole point of a hazard surface: places differ, and by a lot."""
    subject = quake_subject("ANK-CANKAYA", 50.0)
    note = EARTHQUAKE.radius_note(subject)
    assert "No mapped system dominates" in note

    istanbul = EARTHQUAKE.local_rate(quake_subject(), 5.5)
    ankara = EARTHQUAKE.local_rate(subject, 5.5)
    assert istanbul > ankara * 5


def test_any_coordinate_in_the_country_can_be_priced() -> None:
    """Cover is not a list of five cities any more."""
    for latitude, longitude in (
        (41.29, 36.33),   # Samsun
        (37.07, 37.38),   # Gaziantep
        (38.49, 43.38),   # Van
        (36.90, 30.69),   # Antalya
        (39.75, 37.02),   # Sivas
    ):
        subject = EARTHQUAKE.validate_subject(
            {"latitude": latitude, "longitude": longitude, "radius_km": 50}
        )
        rate = EARTHQUAKE.local_rate(subject, 5.0)
        assert rate > 0, "every inhabited coordinate has some seismicity"
        assert EARTHQUAKE.radius_note(subject)


def test_a_coordinate_outside_the_country_is_refused() -> None:
    """Rather than extrapolating a Turkish hazard model into the Atlantic."""
    with pytest.raises(ValueError):
        EARTHQUAKE.validate_subject(
            {"latitude": 48.85, "longitude": 2.35, "radius_km": 50}
        )


def test_quake_exceedance_follows_poisson_occurrence() -> None:
    subject = quake_subject()
    exceedance = EARTHQUAKE.exceedance(subject, 365.25)
    rate = EARTHQUAKE.local_rate(subject, 6.0)
    assert exceedance(6.0) == pytest.approx(1.0 - math.exp(-rate), rel=1e-12)


def test_quake_exceedance_grows_with_the_term() -> None:
    subject = quake_subject()
    short = EARTHQUAKE.exceedance(subject, 30)(5.5)
    long = EARTHQUAKE.exceedance(subject, 365)(5.5)
    assert long > short > 0


def test_quake_rejects_a_zero_term() -> None:
    with pytest.raises(ValueError, match="term"):
        EARTHQUAKE.exceedance(quake_subject(), 0)


def test_every_location_prices_at_every_radius() -> None:
    curve = EARTHQUAKE.default_curve()
    for code in LOCATIONS:
        for radius in ALLOWED_RADII_KM:
            subject = quake_subject(code, radius)
            share = curve.expected_share(EARTHQUAKE.exceedance(subject, 365))
            assert 0.0 <= share < 0.5


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_lookup_names_the_alternatives() -> None:
    with pytest.raises(ValueError, match="offered perils"):
        get_peril("hurricane")


def test_every_peril_states_its_basis_risk() -> None:
    for peril in (FLIGHT_DELAY, DROUGHT, EARTHQUAKE):
        assert peril.basis_risk_level in {"low", "moderate", "high"}
        assert len(peril.basis_risk) > 80


def test_every_peril_names_what_happens_when_data_is_missing() -> None:
    """The case most parametric designs leave undefined."""
    subjects = {
        FLIGHT_DELAY: flight_subject(),
        DROUGHT: drought_subject(),
        EARTHQUAKE: quake_subject(),
    }
    for peril, subject in subjects.items():
        source = peril.data_source(subject)
        assert source.settlement_deadline_days > 0
        assert "return" in source.on_missing_data.lower()


# ---------------------------------------------------------------------------
# A record older than the shape it is read with
# ---------------------------------------------------------------------------


def test_a_flight_policy_from_before_the_airport_catalogue_can_still_be_read() -> None:
    """One old record took a whole page down.

    Cover written before the catalogue existed names a route rather than two
    airport codes. validate_subject reads that back into the two airports --
    but it runs when a policy is written, and a policy already in the book was
    written before it existed. Restored from disk, those records still carry
    `route`, so every line reaching for subject["origin"] raised KeyError on
    them and GET /api/policies answered five hundred for the whole book,
    because one of two thousand policies was old. Measured on the live
    protocol: ERR-46E6357A, KeyError: 'origin'.
    """
    from clause.perils.flight import FlightDelay, airports_of

    peril = FlightDelay()
    old = {"route": "TK-IST-LHR", "flight_number": "TK1979",
           "departure_date": "2026-11-02", "departure_time": "07:45"}
    assert airports_of(old) == ("IST", "LHR")
    said = peril.describe_subject(old)
    assert "IST" in said and "LHR" in said and "TK1979" in said
    # And the rest of the peril reads it too, not only its description.
    assert peril.route_key(old) == "TK-IST-LHR"
    assert peril.sector_km(old) > 0
    assert peril.departs_at(old) > 0


def test_the_two_shapes_describe_the_same_flight_the_same_way() -> None:
    """The comment on the migration says cover already sold must describe and
    settle the same way. That is only true if both shapes come out alike."""
    from clause.perils.flight import FlightDelay

    peril = FlightDelay()
    common = {"flight_number": "TK1979", "departure_date": "2026-11-02",
              "departure_time": "07:45"}
    old = {**common, "route": "TK-IST-LHR"}
    new = {**common, "origin": "IST", "destination": "LHR"}
    assert peril.describe_subject(old) == peril.describe_subject(new)
    assert peril.route_key(old) == peril.route_key(new)
    assert peril.sector_km(old) == peril.sector_km(new)


def test_a_record_nothing_can_name_is_still_a_record() -> None:
    """Failing to resolve a route must not take a page down with it: that is
    the fault this is here about, and raising a different exception in the
    same place would only change its name."""
    from clause.perils.flight import FlightDelay, airports_of

    peril = FlightDelay()
    nonsense = {"route": "not-a-route", "flight_number": "XX1",
                "departure_date": "2026-11-02"}
    assert airports_of(nonsense) == ("", "")
    assert isinstance(peril.describe_subject(nonsense), str)
    assert isinstance(peril.describe_subject({}), str)


def test_a_distance_that_is_not_about_this_site_is_not_quoted() -> None:
    """The sentence contradicted itself in its own second clause.

    "No mapped system dominates this site: the nearest trace is about 19253 km
    away." The trace database is Türkiye's, so for a point in Hawaii it answers
    with the distance to Anatolia, which is not a description of Oahu. It was
    unreachable outside Türkiye while every such address was refused; opening
    Hawaii on the USGS's own model made it a sentence a buyer reads.

    Where a trace is near enough to bear on the site, it is still named: Ankara
    has none dominating it and the nearest is 96 km off, which is worth saying.
    """
    from clause.perils.quake import TRACES_REACH_KM

    # Honolulu was the case that exposed it and has a catalogue model of its
    # own now, so the rule is shown where it still bites: a point our grids do
    # not reach, which falls to the fault traces and finds none.
    pacific = EARTHQUAKE.radius_note(
        {"latitude": 0.0, "longitude": -140.0, "radius_km": 50.0})
    assert "No mapped fault system reaches this site" in pacific
    assert "km away" not in pacific

    ankara = EARTHQUAKE.radius_note(
        {"latitude": 39.9208, "longitude": 32.8541, "radius_km": 50.0})
    assert "the nearest trace is about" in ankara
    assert " km away" in ankara

    # And the bound is what separates them, not the country.
    from clause.perils.geo import site_at
    assert site_at(39.9208, 32.8541).nearest_distance_km < TRACES_REACH_KM
    assert site_at(0.0, -140.0).nearest_distance_km > TRACES_REACH_KM
