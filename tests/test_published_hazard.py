"""The national hazard models, as their own authorities publish them.

Our own model is a catalogue since 1973 and a global shaking equation with no
site term. Where a country publishes a probabilistic hazard model, that model
knows the ground, the basin and the faults our catalogue has not seen, and it
is the figure its own regulator prices against. These tests cover the reading
of a published curve and the one number it moves in our pricing.
"""

from __future__ import annotations

import json
import math

import pytest

from clause.hazard import published as pub
from clause.perils import shaking as sh

# Osaka, as J-SHIS publishes it: surface velocity at four exceedance
# probabilities in fifty years, turned into annual rates.
OSAKA = (34.6937, 135.5023)
OSAKA_PGV = ((42.6, 0.39), (71.7, 0.10), (91.6, 0.05), (130.8, 0.02))


def osaka_curve() -> tuple[tuple[float, float], ...]:
    return tuple(sorted((pub.mmi_from_pgv(pgv), -math.log(1.0 - p) / 50.0)
                        for pgv, p in OSAKA_PGV))


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch):
    """One published point at Osaka, in place of whatever the build wrote."""
    def place(latitude: float, longitude: float, curve=None) -> tuple[dict, ...]:
        return ({"country": "JP", "name": "Osaka", "latitude": latitude,
                 "longitude": longitude, "curve": curve or osaka_curve(),
                 "publisher": "NIED J-SHIS", "reference": "https://www.j-shis.bosai.go.jp/",
                 "measure": "PGV, cm/s", "conversion": "Worden 2012", "version": "test"},)

    def install(latitude: float = OSAKA[0], longitude: float = OSAKA[1], curve=None) -> None:
        rows = place(latitude, longitude, curve)
        monkeypatch.setattr(pub, "curves", lambda: rows)
        pub.nearest.cache_clear()
        sh._shift.cache_clear()

    install()
    yield install
    pub.nearest.cache_clear()
    sh._shift.cache_clear()


def test_velocity_becomes_intensity_by_the_published_relation() -> None:
    # Worden, Gerstenberger, Rhoades and Wald (2012), as ShakeMap's own
    # implementation carries it: three straight pieces in log velocity.
    assert pub.mmi_from_pgv(1.0) == pytest.approx(3.78, abs=0.01)     # log10 v = 0
    assert pub.mmi_from_pgv(0.0) == 0.0
    # The pieces meet where the paper joins them, so the curve has no step in it.
    for log_joint in (-1.21, 0.53):
        joint = 10 ** log_joint
        below = pub.mmi_from_pgv(joint * 0.999)
        above = pub.mmi_from_pgv(joint * 1.001)
        assert below == pytest.approx(above, abs=0.02), f"a step at log v = {log_joint}"
    # And it agrees with the intensity ShakeMap prints for a recorded velocity:
    # 16 to 31 cm/s is VII, 31 to 60 is VIII, 60 to 116 is IX.
    assert 6.5 < pub.mmi_from_pgv(20.0) < 7.6
    assert 7.6 <= pub.mmi_from_pgv(42.6) < 8.5
    assert 8.5 <= pub.mmi_from_pgv(90.0) < 9.4


def test_the_curve_is_read_between_its_points_and_beyond_them() -> None:
    curve = ((6.0, 0.01), (7.0, 0.001))
    assert pub.rate_at(curve, 6.0) == pytest.approx(0.01)
    assert pub.rate_at(curve, 7.0) == pytest.approx(0.001)
    # Straight in log rate: halfway is the geometric mean, not the arithmetic one.
    assert pub.rate_at(curve, 6.5) == pytest.approx(math.sqrt(0.01 * 0.001))
    assert pub.rate_at(curve, 6.5) < 0.5 * (0.01 + 0.001)
    # Below the first point the curve does not invent hazard it does not show.
    assert pub.rate_at(curve, 4.0) == pytest.approx(0.01)
    # Above the last it carries on down the last slope.
    assert pub.rate_at(curve, 8.0) == pytest.approx(0.0001)
    assert pub.rate_at((), 7.0) == 0.0


def test_a_curve_describes_places_near_it_and_no_further(published) -> None:
    near = pub.nearest(*OSAKA)
    assert near is not None and near["name"] == "Osaka" and near["distance_km"] == 0.0
    # Kobe, about 30 km west, is described by it.
    assert pub.nearest(34.69, 135.20) is not None
    # Tokyo, four hundred kilometres away, is not.
    assert pub.nearest(35.68, 139.69) is None
    assert pub.NEAR_KM == 60.0


def test_the_site_term_makes_our_curve_agree_with_the_published_one(published) -> None:
    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    term = sh.site_term(subject)
    assert term is not None
    assert term["place"] == "Osaka" and term["publisher"] == "NIED J-SHIS"
    assert not term["at_the_limit"]
    # Japan says Osaka shakes harder than a global equation with no site term
    # expects, and by more than the equation's own scatter.
    assert term["shift"] > sh.IPE_SIGMA
    # After the term, the return periods we quote are the ones Japan publishes,
    # as closely as a single number can follow a curve of another shape.
    for level, rate in osaka_curve():
        ours = sh.rate_at_least(subject, level)
        assert ours == pytest.approx(rate, rel=0.7), f"MMI {level:.2f}"
    # And what one number could not follow is carried out with it, not hidden.
    assert 1.0 < term["worst_ratio"] < 2.0


def test_the_term_moves_the_answer_and_nothing_else(published) -> None:
    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    shift = sh.shift_at(subject)
    assert shift != 0.0
    # rate_at_least is the raw curve read one site term lower, exactly.
    for level in (6.0, 6.5, 7.0, 7.5):
        assert sh.rate_at_least(subject, level) == pytest.approx(
            sh.raw_rate_at_least(subject, level - shift))
    # The raw curve is untouched: the same rates the catalogue model always gave.
    assert sh.raw_rate_at_least(subject, 7.0) > 0.0


def test_a_far_stronger_published_curve_is_not_followed_without_limit(published) -> None:
    # Violent shaking once a decade: stronger than anything our model produces.
    published(curve=((9.5, 0.1), (9.9, 0.01)))
    term = sh.site_term({"latitude": OSAKA[0], "longitude": OSAKA[1]})
    assert term is not None
    assert term["at_the_limit"] is True
    assert abs(term["shift"]) == sh.SHIFT_LIMIT


def test_an_address_no_published_model_covers_is_priced_as_before(published) -> None:
    somewhere = {"latitude": 35.68, "longitude": 139.69}
    assert sh.site_term(somewhere) is None
    assert sh.shift_at(somewhere) == 0.0
    assert sh.rate_at_least(somewhere, 7.0) == pytest.approx(sh.raw_rate_at_least(somewhere, 7.0))


def test_the_events_drawn_for_capital_carry_the_same_term(published) -> None:
    import random

    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    shift = sh.shift_at(subject)
    with_term = sum(sum(sh.draw(random.Random(s), subject)) for s in range(40))
    sh._shift.cache_clear()
    monkey = sh.shift_at
    try:
        sh.shift_at = lambda subject: 0.0        # type: ignore[assignment]
        without = sum(sum(sh.draw(random.Random(s), subject)) for s in range(40))
    finally:
        sh.shift_at = monkey                      # type: ignore[assignment]
    assert with_term != without
    assert (with_term > without) == (shift > 0)


def test_the_quote_says_whose_model_priced_it(published) -> None:
    """A buyer is told whose figure the frequencies are, not left to assume."""
    from fastapi.testclient import TestClient

    from clause.api.app import create_app

    client = TestClient(create_app(trials=200))
    reply = client.get("/api/hazard", params={"latitude": OSAKA[0], "longitude": OSAKA[1]}).json()
    said = reply["shaking"]["published"]
    assert said["publisher"] == "NIED J-SHIS" and said["place"] == "Osaka"
    assert said["distance_km"] == 0.0 and said["shift"] > 0

    # An address no published model covers says nothing rather than something.
    far = client.get("/api/hazard", params={"latitude": 35.68, "longitude": 139.69}).json()
    assert "published" not in far["shaking"]


def test_the_shipped_curves_are_hazard_curves() -> None:
    """The file the build wrote, read as the runtime reads it."""
    doc = pub.OUT
    assert doc.exists(), "the published models are part of the product, not a local build"
    countries = json.loads(doc.read_text(encoding="utf-8"))
    assert set(countries) <= set(pub.SOURCES)
    for code, country in countries.items():
        assert country["publisher"] and country["reference"].startswith("https://")
        # What the build could not read is named rather than passed over, so a
        # hole in the model cannot be mistaken for a place with no hazard.
        assert isinstance(country["missed"], list)
        assert len(country["missed"]) < 0.02 * len(country["points"])
        for point in country["points"]:
            curve = point["curve"]
            assert len(curve) >= 2, f"{code} {point['name']}"
            motion = [x for x, _ in curve]
            rates = [y for _, y in curve]
            assert motion == sorted(motion) and len(set(motion)) == len(motion)
            assert all(a > b for a, b in zip(rates, rates[1:])), f"{code} {point['name']}"
            assert all(y > 0 for y in rates)

    read = pub.curves()
    assert len(read) == sum(len(c["points"]) for c in countries.values())
    for row in read:
        curve = row["curve"]
        # In intensity by the time the runtime sees it, weak end dropped, and
        # strictly increasing, because this is the axis the runtime reads along
        # and two points at one intensity with two frequencies is not a curve.
        levels = [level for level, _ in curve]
        assert levels[0] >= pub.LEAST_INTENSITY, row["name"]
        assert len(set(levels)) == len(levels), row["name"]
        assert levels == sorted(levels)
        # And it reaches the shaking a policy is written on.
        assert levels[-1] >= 6.0, row["name"]


def test_the_fit_is_made_where_the_policy_lives(published) -> None:
    """A curve's weak end is most of its points and none of its risk.

    A published curve runs from shaking nobody insures against upward. Fitting
    one number over the whole of it lets the parts below any trigger decide the
    term, which is what left New York's fit sixteen times out on the levels it
    is actually sold at.
    """
    priced = osaka_curve()
    # The same curve with four more points far below anything a policy attaches
    # to, where our model and theirs have no reason to agree.
    noise = ((3.1, 2.0), (3.5, 1.5), (4.0, 1.0), (4.5, 0.5))
    published(curve=tuple(sorted(noise + priced)))
    with_noise = sh.site_term({"latitude": OSAKA[0], "longitude": OSAKA[1]})
    sh._shift.cache_clear()
    published(curve=priced)
    without = sh.site_term({"latitude": OSAKA[0], "longitude": OSAKA[1]})
    assert with_noise is not None and without is not None
    assert with_noise["shift"] == without["shift"]
    assert with_noise["worst_ratio"] == without["worst_ratio"]
    assert sh.FIT_BAND == (5.0, 10.0)
