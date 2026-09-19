"""The special functions, checked against published values.

Every price this protocol quotes rests on these. They are written out rather
than imported precisely so they can be checked, and this is the checking.
"""

from __future__ import annotations

import math

import pytest

from clause.mathx import (
    MathError,
    gamma_cdf,
    gamma_quantile,
    lognormal_cdf,
    lower_gamma_regularised,
    normal_cdf,
    normal_quantile,
    poisson_cdf,
    poisson_pmf,
    poisson_sf,
    quantile_from_cdf,
    rate_for_window,
    upper_gamma_regularised,
)


# -- incomplete gamma -------------------------------------------------------


@pytest.mark.parametrize(
    "a, x, expected",
    [
        # P(1, x) = 1 - exp(-x), the exponential distribution.
        (1.0, 1.0, 0.6321205588285577),
        (1.0, 2.0, 0.8646647167633873),
        # P(1/2, x) = erf(sqrt(x)), which ties the gamma to the normal.
        (0.5, 0.5, 0.6826894921370859),
        (0.5, 2.0, 0.9544997361036416),
        # Values from standard tables.
        (5.0, 5.0, 0.5595067149347875),
        (3.0, 2.0, 0.3233235838169365),
        (10.0, 3.0, 0.0011024881301153755),
    ],
)
def test_lower_gamma_matches_published_values(a: float, x: float, expected: float) -> None:
    assert lower_gamma_regularised(a, x) == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("n, x", [(1, 0.5), (3, 2.0), (10, 3.0), (25, 20.0), (40, 55.0)])
def test_lower_gamma_matches_direct_summation(n: int, x: float) -> None:
    """Cross check against an identity, which beats trusting a typed table.

    For integer shape, P(n, x) is one minus the Poisson tail, and that sum can
    be written out term by term with nothing shared with the implementation
    under test.
    """
    direct = 1.0 - sum(
        x ** k * math.exp(-x) / math.factorial(k) for k in range(n)
    )
    assert lower_gamma_regularised(float(n), x) == pytest.approx(direct, rel=1e-11)


def test_upper_and_lower_gamma_sum_to_one() -> None:
    for a in (0.3, 1.0, 2.5, 8.0, 40.0):
        for x in (0.1, 1.0, 5.0, 20.0, 60.0):
            total = lower_gamma_regularised(a, x) + upper_gamma_regularised(a, x)
            assert total == pytest.approx(1.0, abs=1e-12)


def test_gamma_is_monotone_in_x() -> None:
    previous = -1.0
    for x in [i * 0.4 for i in range(1, 60)]:
        value = lower_gamma_regularised(3.0, x)
        assert value >= previous
        previous = value


@pytest.mark.parametrize("a, x", [(0.0, 1.0), (-1.0, 1.0)])
def test_gamma_rejects_a_bad_shape(a: float, x: float) -> None:
    with pytest.raises(MathError):
        lower_gamma_regularised(a, x)


def test_gamma_rejects_a_negative_argument() -> None:
    with pytest.raises(MathError):
        lower_gamma_regularised(1.0, -1.0)


# -- gamma distribution -----------------------------------------------------


def test_gamma_cdf_at_the_mean() -> None:
    # A gamma with shape 2 and scale 3 has mean 6, and lands below it 59.4% of
    # the time: the right skew that makes it fit rainfall.
    assert gamma_cdf(6.0, 2.0, 3.0) == pytest.approx(0.5939941502901616, rel=1e-9)


def test_gamma_quantile_inverts_the_cdf() -> None:
    for p in (0.01, 0.1, 0.5, 0.9, 0.99):
        value = gamma_quantile(p, 5.949, 19.836)
        assert gamma_cdf(value, 5.949, 19.836) == pytest.approx(p, abs=1e-8)


def test_gamma_quantile_at_zero() -> None:
    assert gamma_quantile(0.0, 2.0, 3.0) == 0.0


def test_gamma_cdf_below_zero_is_zero() -> None:
    assert gamma_cdf(-5.0, 2.0, 3.0) == 0.0
    assert gamma_cdf(0.0, 2.0, 3.0) == 0.0


def test_gamma_rejects_a_bad_scale() -> None:
    with pytest.raises(MathError):
        gamma_cdf(1.0, 1.0, 0.0)


# -- Poisson ----------------------------------------------------------------


def test_poisson_pmf_matches_published_values() -> None:
    assert poisson_pmf(0, 1.0) == pytest.approx(math.exp(-1.0), rel=1e-12)
    assert poisson_pmf(2, 3.0) == pytest.approx(0.22404180765538775, rel=1e-10)


def test_poisson_pmf_sums_to_one() -> None:
    for rate in (0.2, 1.0, 4.2, 18.0):
        total = sum(poisson_pmf(k, rate) for k in range(0, 200))
        assert total == pytest.approx(1.0, abs=1e-10)


def test_poisson_cdf_matches_published_values() -> None:
    assert poisson_cdf(2, 3.0) == pytest.approx(0.42319008112684353, rel=1e-10)
    assert poisson_cdf(0, 0.5) == pytest.approx(math.exp(-0.5), rel=1e-12)


def test_poisson_survival_is_the_trigger_probability() -> None:
    """A policy paying on at least one event uses exactly this."""
    for rate in (0.001, 0.05, 0.5, 2.0):
        assert poisson_sf(0, rate) == pytest.approx(1.0 - math.exp(-rate), rel=1e-10)


def test_poisson_at_a_zero_rate() -> None:
    assert poisson_pmf(0, 0.0) == 1.0
    assert poisson_pmf(1, 0.0) == 0.0
    assert poisson_sf(0, 0.0) == 0.0


def test_poisson_rejects_a_negative_rate() -> None:
    with pytest.raises(MathError):
        poisson_pmf(1, -1.0)


# -- normal -----------------------------------------------------------------


def test_normal_cdf_matches_published_values() -> None:
    assert normal_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
    assert normal_cdf(1.96) == pytest.approx(0.9750021048517795, rel=1e-10)
    assert normal_cdf(-1.96) == pytest.approx(0.0249978951482205, rel=1e-10)


def test_normal_quantile_matches_published_values() -> None:
    assert normal_quantile(0.975) == pytest.approx(1.959963984540054, abs=1e-6)
    assert normal_quantile(0.995) == pytest.approx(2.5758293035489004, abs=1e-6)
    assert normal_quantile(0.5) == pytest.approx(0.0, abs=1e-9)


def test_normal_quantile_round_trips() -> None:
    for x in (-3.0, -1.2, 0.0, 0.7, 2.4):
        assert normal_quantile(normal_cdf(x)) == pytest.approx(x, abs=1e-6)


def test_normal_quantile_at_the_edges() -> None:
    assert normal_quantile(0.0) == -math.inf
    assert normal_quantile(1.0) == math.inf


def test_normal_quantile_rejects_a_bad_probability() -> None:
    for p in (-0.1, 1.1, float("nan")):
        with pytest.raises(MathError):
            normal_quantile(p)


def test_lognormal_below_zero_is_zero() -> None:
    assert lognormal_cdf(0.0, 0.0, 1.0) == 0.0
    assert lognormal_cdf(-1.0, 0.0, 1.0) == 0.0


def test_lognormal_at_its_median() -> None:
    """The median of a lognormal is exp(mu), which the flight model relies on."""
    assert lognormal_cdf(math.exp(2.0), 2.0, 0.9) == pytest.approx(0.5, abs=1e-12)


# -- generic quantile -------------------------------------------------------


def test_quantile_from_cdf_inverts_a_known_curve() -> None:
    value = quantile_from_cdf(lambda x: normal_cdf(x), 0.9, -10.0, 10.0)
    assert value == pytest.approx(1.2815515655446004, abs=1e-6)


def test_quantile_from_cdf_rejects_a_bad_bracket() -> None:
    with pytest.raises(MathError):
        quantile_from_cdf(normal_cdf, 0.5, 1.0, 1.0)


# -- helpers ----------------------------------------------------------------


def test_rate_for_window_scales_with_time() -> None:
    assert rate_for_window(1.0, 365.25) == pytest.approx(1.0)
    assert rate_for_window(2.0, 182.625) == pytest.approx(1.0)
    assert rate_for_window(1.0, 0.0) == 0.0


def test_rate_for_window_rejects_a_negative_window() -> None:
    with pytest.raises(MathError):
        rate_for_window(1.0, -1.0)
