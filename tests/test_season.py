"""The seasonal rainfall behind drought cover, and where its numbers come from.

Drought cover pays as a season's rain falls short of what the season normally
brings, so the price turns on two numbers per station: the normal and the
variability. They used to be typed into the source under a comment admitting
it. These tests hold them to the record instead.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from clause.hazard import season_build as sb
from clause.mathx import gamma_cdf
from clause.perils import weather as wx


def series(first: dt.date, last: dt.date, mm: float, *, missing: set[str] = frozenset()) -> dict[str, float]:
    out, day = {}, first
    while day <= last:
        key = day.strftime("%Y%m%d")
        out[key] = -999.0 if key in missing else mm
        day += dt.timedelta(days=1)
    return out


def a_station(**kwargs) -> wx.Station:
    fields = dict(code="XX-TEST", name="Test", region="Test", latitude=0.0, longitude=0.0,
                  opens=(4, 1), window_days=100, normal_mm=100.0, variability=0.3)
    fields.update(kwargs)
    return wx.Station(**fields)


def test_a_season_is_the_days_of_its_own_window_and_no_others() -> None:
    station = a_station(opens=(4, 1), window_days=100)
    got = sb.totals(series(dt.date(1981, 1, 1), dt.date(1982, 12, 31), 2.0), station, 1982)
    assert sorted(got) == [1981, 1982]
    # A hundred days of two millimetres, and not a drop of the rest of the year.
    assert got[1981] == pytest.approx(200.0)


def test_a_season_the_record_does_not_cover_is_dropped() -> None:
    station = a_station(opens=(11, 1), window_days=120)     # runs into the next year
    whole = series(dt.date(1981, 1, 1), dt.date(1982, 12, 31), 1.0)
    got = sb.totals(whole, station, 1982)
    assert 1981 in got                     # November 1981 into February 1982: covered
    assert 1982 not in got                 # November 1982 into 1983: the record stops


def test_a_season_with_too_many_gaps_is_dropped() -> None:
    station = a_station(opens=(4, 1), window_days=100)
    days = [f"1981{(dt.date(1981, 4, 1) + dt.timedelta(days=i)):%m%d}" for i in range(20)]
    whole = series(dt.date(1981, 1, 1), dt.date(1981, 12, 31), 1.0, missing=set(days))
    assert 1981 not in sb.totals(whole, station, 1981)
    # Three missing days out of a hundred is a gap, not a hole.
    few = series(dt.date(1981, 1, 1), dt.date(1981, 12, 31), 1.0, missing=set(days[:3]))
    assert sb.totals(few, station, 1981)[1981] == pytest.approx(97.0)


def test_the_two_numbers_are_the_mean_and_the_coefficient_of_variation() -> None:
    mean, cv = sb.moments([90.0, 100.0, 110.0])
    assert mean == pytest.approx(100.0)
    assert cv == pytest.approx(10.0 / 100.0)          # the sample standard deviation over the mean
    assert sb.moments([50.0, 50.0, 50.0])[1] == 0.0


def test_the_tested_level_is_the_level_the_policy_would_pay_at() -> None:
    mean, cv = 200.0, 0.3
    low = sb.gamma_quantile(mean, cv, 0.2)
    shape = 1.0 / cv ** 2
    assert gamma_cdf(low, shape, mean / shape) == pytest.approx(0.2, abs=1e-4)
    assert low < mean                                  # a one in five dry season is a dry one


# ---------------------------------------------------------------------------
# What the station table offers
# ---------------------------------------------------------------------------


def test_the_price_comes_from_the_record_and_not_from_the_source() -> None:
    doc = wx.measured()
    rows = {row["code"]: row for row in doc["stations"]}
    for code, station in wx.STATIONS.items():
        assert station.normal_mm == rows[code]["normal_mm"], code
        assert station.variability == rows[code]["variability"], code
    # And the figures left in the source are genuinely superseded, not copied.
    differ = [c for c in wx.STATIONS
              if wx._DEFINED[c].variability != wx.STATIONS[c].variability]
    assert len(differ) > 0.9 * len(wx.STATIONS)


def test_a_season_nobody_measured_is_not_on_sale(monkeypatch: pytest.MonkeyPatch) -> None:
    kept = dict(wx.measured())
    try:
        monkeypatch.setattr(wx, "measured", lambda: {"validation": {"passed": False},
                                                     "stations": kept["stations"]})
        wx._stations.cache_clear()
        assert len(wx.STATIONS) == 0
        from clause.perils import DROUGHT

        assert DROUGHT.territory == frozenset()
    finally:
        monkeypatch.undo()
        wx._stations.cache_clear()
    assert len(wx.STATIONS) == len(wx._DEFINED)


def test_the_test_that_failed_is_written_down_where_it_cannot_be_read_as_a_pass() -> None:
    validation = wx.measured()["validation"]
    fixed = validation["fixed_test"]
    # The test set before any result was seen: fit on 1981 to 2010, test after.
    assert fixed["fitted_until"] == 2010 and fixed["tested_from"] == 2011
    # It failed, and the file says so in its own entry rather than in a footnote.
    assert fixed["passed"] is False
    assert fixed["below_the_1_in_5"] < fixed["expected"]
    # What failed was the climate, not the distribution: the same gamma
    # describes the seasons it was fitted on.
    assert validation["in_sample"]["passed"] is True
    assert "failed" in validation["changes_after_first_run"]
    assert str(fixed["below_the_1_in_5"]) in validation["changes_after_first_run"]
    # And the model is sold on the current climate, not on the whole record.
    assert validation["fitted_on"] == "the most recent 30 seasons"
