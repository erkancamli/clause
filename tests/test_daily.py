"""Daily extremes in more than one country, and which of them are sold.

The car cover pays on the largest day of rain and the storm cover on the largest
day of wind. Both were written only in Türkiye, not because the method is
Turkish but because the build only ever fetched Türkiye's eighty one provincial
centres. NASA POWER is global, so the method was global all along and the data
was not.
"""

from __future__ import annotations

import json

import pytest

from clause.perils import STORM, VEHICLE_FLOOD, daily


def a_model(code: str, *, passed: bool, places=((("Somewhere", 0.0, 0.0)),)) -> dict:
    return {
        "code": code, "name": code, "kind": "rain_extreme", "version": "t",
        "index": "test", "unit": "mm", "sources": [],
        "validation": {"passed": passed, "failed": [] if passed else ["count"],
                       "fitted_until": 2010, "tested_from": 2011},
        "places": [{"name": n, "latitude": la, "longitude": lo,
                    "gumbel": {"mu": 30.0, "beta": 9.0},
                    "levels_mm": {"2": 33.3, "5": 41.5, "10": 50.0, "25": 58.0, "50": 63.0},
                    "record_years": 45, "fit_years": 30, "largest_mm": 90.0}
                   for n, la, lo in places],
    }


@pytest.fixture
def two_countries(tmp_path, monkeypatch):
    """One country whose model passed and one whose model did not."""
    (tmp_path / "rain_AA.json").write_text(
        json.dumps(a_model("AA", passed=True, places=(("Aaville", 10.0, 10.0),))), encoding="utf-8")
    (tmp_path / "rain_BB.json").write_text(
        json.dumps(a_model("BB", passed=False, places=(("Beeburg", 10.2, 10.0),))), encoding="utf-8")
    monkeypatch.setattr(daily, "MODELS_DIR", tmp_path)
    daily.reload()
    yield
    daily.reload()


def test_a_country_is_sold_on_its_own_backtest(two_countries) -> None:
    assert sorted(daily.models("rain")) == ["AA", "BB"]
    assert daily.passed("rain") == frozenset({"AA"})
    assert VEHICLE_FLOOD.territory == frozenset({"AA"})


def test_a_failed_country_is_not_a_fallback(two_countries) -> None:
    """Beeburg is 22 km from Aaville and its own model failed.

    The nearest fitted place must come from a country that may be sold. A place
    from a country whose backtest failed is not a near miss, it is the wrong
    number written confidently.
    """
    place, km = daily.nearest("rain", 10.2, 10.0)
    assert place is not None and place["name"] == "Aaville" and place["country"] == "AA"
    assert 20 < km < 25          # the nearer place was Beeburg's, and it is not offered

    subject = VEHICLE_FLOOD.validate_subject({"latitude": 10.2, "longitude": 10.0})
    assert subject["station"] == "Aaville" and subject["country"] == "AA"
    assert VEHICLE_FLOOD.risk_country(subject) == "AA"


def test_past_the_distance_the_refusal_names_the_countries(two_countries) -> None:
    with pytest.raises(ValueError) as caught:
        VEHICLE_FLOOD.validate_subject({"latitude": 40.0, "longitude": 40.0})
    said = str(caught.value)
    assert "60 km" in said and "AA" in said
    assert "BB" not in said      # a country that failed is not offered as somewhere to go


def test_with_no_models_at_all_nothing_is_written(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(daily, "MODELS_DIR", tmp_path)
    daily.reload()
    try:
        assert daily.models("rain") == {} and daily.passed("rain") == frozenset()
        assert VEHICLE_FLOOD.territory == frozenset()
        assert STORM.territory == frozenset()
        with pytest.raises(ValueError, match="nowhere yet"):
            VEHICLE_FLOOD.validate_subject({"latitude": 40.99, "longitude": 29.03})
    finally:
        daily.reload()


# ---------------------------------------------------------------------------
# What the build fits, and where
# ---------------------------------------------------------------------------


def test_a_country_is_fitted_where_the_interface_offers_cover() -> None:
    from clause.hazard.daily_extremes import LEAST_PEOPLE, LEAST_PLACES, world_places

    # The Philippines is in this list because it is where it matters: the place
    # index holds both "Mandaluyong City" and "Mandaluyong" at one coordinate,
    # and without the check they would be two fits of one fetched series, each
    # counted separately in the country's own backtest.
    for code in ("JP", "US", "MX", "ID", "PH"):
        where = world_places(code)
        assert len(where) >= LEAST_PLACES, code
        seen = {(round(la, 2), round(lo, 2)) for _, la, lo in where}
        assert len(seen) == len(where), code
    names = [n for n, _, _ in world_places("PH")]
    assert len([n for n in names if n.startswith("Mandaluyong")]) == 1

    # A country with two large cities still gets enough places to fit on.
    small = world_places("GR")
    assert len(small) == LEAST_PLACES
    assert small[0][0] == "Athens"
    assert LEAST_PEOPLE == 200_000


def test_every_built_country_writes_its_own_file_and_its_own_verdict() -> None:
    for stem in ("rain", "wind"):
        built = daily.models(stem)
        assert "TR" in built, stem
        for code, doc in built.items():
            assert doc["code"] == code
            v = doc["validation"]
            assert v["fitted_until"] == 2010 and v["tested_from"] == 2011
            # "failed" lists every test that failed, and a country can be sold
            # on the other one, so an empty list is sufficient and not necessary.
            assert not v["failed"] or v["passed"] == ("record" not in v["failed"]
                                                      and not {"count", "rolling"} <= set(v["failed"]))
            assert doc["places"] and all(p["fit_years"] >= 25 for p in doc["places"])


def test_only_a_country_file_is_read_as_a_country(tmp_path, monkeypatch) -> None:
    """The models directory holds other things, and none of them is a country."""
    (tmp_path / "rain_AA.json").write_text(json.dumps(a_model("AA", passed=True)), encoding="utf-8")
    for stray in ("rain_notes.json", "rain_places.json", "rain_.json"):
        (tmp_path / stray).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(daily, "MODELS_DIR", tmp_path)
    daily.reload()
    try:
        assert sorted(daily.models("rain")) == ["AA"]
    finally:
        daily.reload()


def test_the_place_search_answers_for_the_cover_being_bought() -> None:
    """Which places can be priced depends on which cover, not on earthquakes.

    The rain model passes in one set of countries and the wind model in
    another, and neither is the earthquake set. Answering every search with the
    earthquake list marked the wrong places unavailable in each: a buyer typing
    Rome for a car cover was told it could not be priced, and Italy's rainfall
    model passes.
    """
    from clause.perils import EARTHQUAKE, STORM, VEHICLE_FLOOD
    from clause.perils.places import search_world

    def verdicts(peril):
        return {row["country"]: row["priced"]
                for row in search_world("a", limit=60, peril=peril)}

    for peril, cover in (("vehicle_flood", VEHICLE_FLOOD), ("storm", STORM),
                         ("earthquake", EARTHQUAKE)):
        for code, priced in verdicts(peril).items():
            assert priced == (code in cover.territory), (peril, code)

    # The three do not agree, which is why each has to be asked separately.
    assert VEHICLE_FLOOD.territory != EARTHQUAKE.territory
    assert VEHICLE_FLOOD.territory != STORM.territory

    # And an unknown peril falls back to the earthquake list rather than to none.
    fallback = verdicts("not_a_peril")
    assert fallback and all(v == (c in EARTHQUAKE.territory) for c, v in fallback.items())


# ---------------------------------------------------------------------------
# The two tests, and which one carries a country
# ---------------------------------------------------------------------------


def test_a_country_says_which_test_it_is_sold_on() -> None:
    """A second test was added after the first failed. Both are published.

    The fixed test asks whether a fit on 1981 to 2010 predicts 2011 onward. The
    rolling test asks whether a fit on the recent years predicts the next one,
    which is how the published levels are actually fitted and used. A country
    that failed the first and passed the second is sold on a model that tracks a
    moving climate rather than on one that was always right, and that is a
    different claim, so the file makes it rather than hiding it behind a
    boolean.
    """
    for stem in ("rain", "wind"):
        for code, doc in daily.models(stem).items():
            v = doc["validation"]
            fixed = "count" not in v["failed"]
            rolled = v["rolling"]["passed"]
            assert v["passed"] == (fixed or rolled) and "record" not in v["failed"], (stem, code)
            assert v["sold_on"] == (
                "the fixed test" if fixed
                else "the rolling test, the fixed one having failed" if rolled
                else "neither test"), (stem, code, v["sold_on"])
            assert (code in daily.passed(stem)) == v["passed"]

    # It is not a rubber stamp: it opens some countries and refuses others.
    rain = daily.models("rain")
    on_rolling = [c for c, d in rain.items() if d["validation"]["rolling"]["passed"]
                  and "count" in d["validation"]["failed"]]
    refused = [c for c, d in rain.items() if not d["validation"]["passed"]]
    assert on_rolling and refused, (on_rolling, refused)
    # Where it refuses, the rain beat a fit on the recent years too, and by a lot.
    for code in refused:
        r = rain[code]["validation"]["rolling"]
        assert r["observed"] > 1.5 * r["expected"], code


def test_the_rolling_test_never_sees_the_year_it_predicts() -> None:
    """Out of sample at every step, or it is not a test."""
    import datetime as dt

    from clause.hazard import daily_extremes as de
    from clause.hazard.rain_build import SPEC

    asked: list[tuple[int, int]] = []          # (last fitting year, year predicted)
    real_gumbel = de.gumbel
    seen_years: list[list[int]] = []

    class OnePlace:
        name, latitude, longitude, kind = "P", 0.0, 0.0, "province"

    made = {f"{y}0101": float(y - 1980) for y in range(1981, 2026)}

    def fetch(spec, la, lo, end):
        return made

    monkey = de.fetch
    try:
        de.fetch = fetch                       # type: ignore[assignment]

        def watch(values):
            seen_years.append(sorted(int(v) + 1980 for v in values))
            return real_gumbel(values)

        de.gumbel = watch                      # type: ignore[assignment]
        beat, trials = de._rolling(SPEC, [OnePlace()], 2025, "20251231")
    finally:
        de.fetch = monkey                      # type: ignore[assignment]
        de.gumbel = real_gumbel                # type: ignore[assignment]

    assert trials == 2025 - 2010               # one per year from 2011
    # Each fit saw only years before the one it was asked about, and at most the
    # window the published levels use.
    for i, years in enumerate(seen_years):
        predicted = 2011 + i
        assert max(years) == predicted - 1, (predicted, max(years))
        assert len(years) <= de.RECENT_YEARS and len(years) >= de.ROLLING_LEAST
    # A series rising every year beats its own fit every time, which is the
    # shape of a country this test refuses.
    assert beat == trials


def test_either_test_may_carry_a_country_but_the_record_may_not_be_waived() -> None:
    from clause.hazard.daily_extremes import verdict

    both = verdict(record_ok=True, count_ok=True, rolling_ok=True)
    assert both["passed"] and both["sold_on"] == "the fixed test" and both["failed"] == []

    moved = verdict(record_ok=True, count_ok=False, rolling_ok=True)
    assert moved["passed"] and moved["sold_on"].startswith("the rolling test")
    assert moved["failed"] == ["count"]        # the failure is still written down

    # The fixed test alone still carries a country whose rolling test failed.
    old = verdict(record_ok=True, count_ok=True, rolling_ok=False)
    assert old["passed"] and old["sold_on"] == "the fixed test"

    neither = verdict(record_ok=True, count_ok=False, rolling_ok=False)
    assert not neither["passed"] and neither["sold_on"] == "neither test"

    # Too few years is too few years, whatever either test says about them.
    for count_ok in (True, False):
        for rolling_ok in (True, False):
            short = verdict(record_ok=False, count_ok=count_ok, rolling_ok=rolling_ok)
            assert not short["passed"] and "record" in short["failed"]
