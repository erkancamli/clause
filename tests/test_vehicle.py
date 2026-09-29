"""Vehicle cover against flooding from extreme daily rain."""

from __future__ import annotations

import pytest

from clause.perils import VEHICLE_FLOOD
from clause.perils.vehicle import model
from clause.pricing.simulation import Exposure, WorldDraws, settle

RIZE = {"latitude": 41.02, "longitude": 40.52}
KONYA = {"latitude": 37.87, "longitude": 32.49}


def test_the_rainfall_model_passed_and_says_what_changed() -> None:
    v = model()["validation"]
    assert v["passed"] and v["tested_from"] == v["fitted_until"] + 1
    assert v["changes_after_first_run"], "a change made after seeing a result is recorded"
    # Every country whose own rainfall model passed, and no others.
    from clause.perils.daily import models, passed
    assert VEHICLE_FLOOD.territory == passed("rain")
    assert "TR" in VEHICLE_FLOOD.territory
    for code, doc in models("rain").items():
        assert (code in VEHICLE_FLOOD.territory) == bool(doc["validation"]["passed"]), code


def test_each_place_pays_on_what_is_extreme_there() -> None:
    wet = VEHICLE_FLOOD.curve_for(VEHICLE_FLOOD.validate_subject(dict(RIZE)))
    dry = VEHICLE_FLOOD.curve_for(VEHICLE_FLOOD.validate_subject(dict(KONYA)))
    assert wet.attachment > dry.attachment
    for curve in (wet, dry):
        levels = [b.level for b in curve.breakpoints]
        assert levels == sorted(levels)


def test_the_trigger_is_about_a_one_in_ten_year_day() -> None:
    subject = VEHICLE_FLOOD.validate_subject(dict(RIZE))
    p = VEHICLE_FLOOD.exceedance(subject, 365.25)(VEHICLE_FLOOD.curve_for(subject).attachment)
    assert p == pytest.approx(0.10, abs=0.005)


def test_outside_the_tested_places_is_refused() -> None:
    with pytest.raises(ValueError, match="60 km"):
        VEHICLE_FLOOD.validate_subject({"latitude": 35.68, "longitude": 139.69})


def test_the_capital_model_agrees_with_the_price() -> None:
    subject = VEHICLE_FLOOD.validate_subject(dict(KONYA))
    exposure = Exposure("v", "vehicle_flood", subject, VEHICLE_FLOOD.curve_for(subject), 1000.0, 365.25)
    losses = settle(exposure, WorldDraws.draw(trials=20000, years=1.0, seed=9))
    observed = sum(1 for x in losses if x > 0) / len(losses)
    assert observed == pytest.approx(0.10, abs=0.01)


def test_the_basis_risk_names_what_is_not_covered() -> None:
    text = VEHICLE_FLOOD.basis_risk
    for word in ("accidents", "theft", "hail"):
        assert word in text
