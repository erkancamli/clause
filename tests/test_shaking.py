"""Shaking at the address, as an index for earthquake cover."""

from __future__ import annotations

import pytest

from clause.perils import EARTHQUAKE
from clause.perils import shaking as sh
from clause.pricing.simulation import Exposure, WorldDraws, settle

KADIKOY = {"latitude": 40.99, "longitude": 29.03, "radius_km": 50.0, "index": "shaking"}
TOKYO = {"latitude": 35.68, "longitude": 139.69, "radius_km": 50.0, "index": "shaking"}
ANKARA = {"latitude": 39.93, "longitude": 32.86, "radius_km": 50.0, "index": "shaking"}


def test_the_intensity_equation_behaves() -> None:
    assert sh.mmi(7.0, 10) > sh.mmi(7.0, 50) > sh.mmi(7.0, 150)
    assert sh.mmi(7.0, 20) > sh.mmi(6.0, 20) > sh.mmi(5.0, 20)
    assert 7.5 < sh.mmi(7.0, 10) < 9.5          # a large shallow quake nearby is severe


def test_the_index_is_part_of_the_subject() -> None:
    subject = EARTHQUAKE.validate_subject(dict(KADIKOY))
    assert subject["index"] == "shaking"
    assert "shaking at the address" in EARTHQUAKE.describe_subject(subject)
    assert EARTHQUAKE.data_source(subject).field == "mmi"
    # Pays from VII, where ordinary buildings are damaged; a 1985 building from lower.
    assert EARTHQUAKE.curve_for(subject).attachment == 7.0
    older = EARTHQUAKE.validate_subject({**KADIKOY, "built": 1985})
    assert EARTHQUAKE.curve_for(older).attachment < 7.0
    with pytest.raises(ValueError):
        EARTHQUAKE.validate_subject({**KADIKOY, "index": "vibes"})


def test_a_quiet_region_shakes_less() -> None:
    p_ank = EARTHQUAKE.exceedance(EARTHQUAKE.validate_subject(dict(ANKARA)), 365.25)
    p_ist = EARTHQUAKE.exceedance(EARTHQUAKE.validate_subject(dict(KADIKOY)), 365.25)
    assert p_ank(6.0) < p_ist(6.0)
    assert p_ist(8.0) < p_ist(7.0) < p_ist(6.0)


@pytest.mark.parametrize("raw", [KADIKOY, TOKYO])
def test_the_capital_model_settles_what_the_price_assumes(raw) -> None:
    subject = EARTHQUAKE.validate_subject(dict(raw))
    exposure = Exposure("s", "earthquake", subject, EARTHQUAKE.curve_for(subject), 1000.0, 365.25)
    losses = settle(exposure, WorldDraws.draw(trials=10000, years=1.0, seed=5))
    observed = sum(1 for x in losses if x > 0) / len(losses)
    modelled = EARTHQUAKE.exceedance(subject, 365.25)(exposure.curve.attachment)
    assert abs(observed - modelled) < 0.25 * modelled + 0.005


def test_the_hazard_endpoint_publishes_the_shaking_curve() -> None:
    from fastapi.testclient import TestClient
    from clause.api.app import create_app

    client = TestClient(create_app(trials=300))
    reply = client.get("/api/hazard", params={"latitude": 40.99, "longitude": 29.03}).json()
    shaking = reply["shaking"]
    assert len(shaking["levels"]) == len(shaking["annual_probability"])
    probs = shaking["annual_probability"]
    assert all(a >= b for a, b in zip(probs, probs[1:]))
