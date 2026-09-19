"""Special functions the pricing engine needs, written out rather than imported.

A parametric insurance protocol lives or dies on whether anyone believes its
prices. Hiding the distributions behind a numerical library means the one part
a reviewer most wants to check is the part they cannot see, so the handful of
functions actually needed are implemented here, documented, and tested against
published values.

Everything below is standard: the regularised incomplete gamma function by
series and continued fraction (Numerical Recipes, section 6.2), the normal
distribution through the error function in the standard library, and quantiles
by bisection on a monotone CDF.
"""

from __future__ import annotations

import math
from typing import Callable

__all__ = [
    "lower_gamma_regularised",
    "upper_gamma_regularised",
    "gamma_cdf",
    "gamma_quantile",
    "poisson_pmf",
    "poisson_cdf",
    "poisson_sf",
    "normal_cdf",
    "normal_quantile",
    "lognormal_cdf",
    "quantile_from_cdf",
    "MathError",
]

# Convergence controls. The series and the continued fraction both converge
# quickly over the ranges this protocol uses; the caps exist so a bad input
# fails loudly instead of spinning.
_EPS = 1e-12
_MAX_ITERATIONS = 400
_TINY = 1e-300


class MathError(ValueError):
    """Raised when a function is called outside its domain or fails to converge."""


# ---------------------------------------------------------------------------
# Incomplete gamma
# ---------------------------------------------------------------------------


def _gamma_series(a: float, x: float) -> float:
    """Lower regularised incomplete gamma P(a, x) by its series expansion.

    Converges fast for x < a + 1.
    """
    if x <= 0.0:
        return 0.0

    ap = a
    total = 1.0 / a
    term = total
    for _ in range(_MAX_ITERATIONS):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * _EPS:
            return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    raise MathError(f"gamma series did not converge for a={a}, x={x}")


def _gamma_continued_fraction(a: float, x: float) -> float:
    """Upper regularised incomplete gamma Q(a, x) by continued fraction.

    Converges fast for x > a + 1. Modified Lentz method.
    """
    b = x + 1.0 - a
    c = 1.0 / _TINY
    d = 1.0 / b
    h = d

    for i in range(1, _MAX_ITERATIONS + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _TINY:
            d = _TINY
        c = b + an / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            return h * math.exp(-x + a * math.log(x) - math.lgamma(a))
    raise MathError(f"gamma continued fraction did not converge for a={a}, x={x}")


def lower_gamma_regularised(a: float, x: float) -> float:
    """P(a, x): the regularised lower incomplete gamma function."""
    if a <= 0.0:
        raise MathError(f"shape must be positive, got {a}")
    if x < 0.0:
        raise MathError(f"argument must not be negative, got {x}")
    if x == 0.0:
        return 0.0
    if x < a + 1.0:
        return _gamma_series(a, x)
    return 1.0 - _gamma_continued_fraction(a, x)


def upper_gamma_regularised(a: float, x: float) -> float:
    """Q(a, x) = 1 - P(a, x)."""
    if a <= 0.0:
        raise MathError(f"shape must be positive, got {a}")
    if x < 0.0:
        raise MathError(f"argument must not be negative, got {x}")
    if x == 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gamma_series(a, x)
    return _gamma_continued_fraction(a, x)


# ---------------------------------------------------------------------------
# Gamma distribution
# ---------------------------------------------------------------------------


def gamma_cdf(x: float, shape: float, scale: float) -> float:
    """Probability that a gamma variate is at or below x.

    Seasonal rainfall totals are conventionally modelled as gamma, which is why
    this is the distribution the weather products are priced on.
    """
    if shape <= 0.0 or scale <= 0.0:
        raise MathError(f"shape and scale must be positive, got {shape}, {scale}")
    if x <= 0.0:
        return 0.0
    return lower_gamma_regularised(shape, x / scale)


def gamma_quantile(p: float, shape: float, scale: float) -> float:
    """The value a gamma variate falls below with probability p."""
    _check_probability(p)
    if p == 0.0:
        return 0.0
    upper = max(shape * scale, 1.0)
    while gamma_cdf(upper, shape, scale) < p and upper < 1e12:
        upper *= 2.0
    return quantile_from_cdf(lambda v: gamma_cdf(v, shape, scale), p, 0.0, upper)


# ---------------------------------------------------------------------------
# Poisson
# ---------------------------------------------------------------------------


def poisson_pmf(k: int, rate: float) -> float:
    """Probability of exactly k events when the mean count is `rate`."""
    if k < 0:
        return 0.0
    if rate < 0.0:
        raise MathError(f"rate must not be negative, got {rate}")
    if rate == 0.0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(rate) - rate - math.lgamma(k + 1))


def poisson_cdf(k: int, rate: float) -> float:
    """Probability of at most k events."""
    if k < 0:
        return 0.0
    if rate == 0.0:
        return 1.0
    # The identity that makes this exact rather than a sum of small terms.
    return upper_gamma_regularised(k + 1, rate)


def poisson_sf(k: int, rate: float) -> float:
    """Probability of more than k events, which for k=0 is the trigger chance.

    Earthquake and other event counts are Poisson, so a policy that pays on at
    least one qualifying event over its term is priced with poisson_sf(0, rate).
    """
    return 1.0 - poisson_cdf(k, rate)


# ---------------------------------------------------------------------------
# Normal and lognormal
# ---------------------------------------------------------------------------


def normal_cdf(x: float, mean: float = 0.0, sigma: float = 1.0) -> float:
    if sigma <= 0.0:
        raise MathError(f"sigma must be positive, got {sigma}")
    return 0.5 * (1.0 + math.erf((x - mean) / (sigma * math.sqrt(2.0))))


def normal_quantile(p: float, mean: float = 0.0, sigma: float = 1.0) -> float:
    """Inverse normal CDF, by the Acklam rational approximation.

    Accurate to about 1e-9 across the range, which is far tighter than any
    input this protocol carries.
    """
    _check_probability(p)
    if p == 0.0:
        return -math.inf
    if p == 1.0:
        return math.inf

    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)

    low, high = 0.02425, 1.0 - 0.02425

    if p < low:
        q = math.sqrt(-2.0 * math.log(p))
        z = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    elif p <= high:
        q = p - 0.5
        r = q * q
        z = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        z = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)

    return mean + sigma * z


def lognormal_cdf(x: float, log_mean: float, log_sigma: float) -> float:
    if x <= 0.0:
        return 0.0
    return normal_cdf(math.log(x), log_mean, log_sigma)


# ---------------------------------------------------------------------------
# Generic quantile
# ---------------------------------------------------------------------------


def quantile_from_cdf(
    cdf: Callable[[float], float],
    p: float,
    low: float,
    high: float,
    tolerance: float = 1e-10,
) -> float:
    """Invert any monotone CDF by bisection.

    Used for the capital tests, where the aggregate loss distribution has no
    closed form and is only available as a callable.
    """
    _check_probability(p)
    if high <= low:
        raise MathError(f"bracket must be increasing, got [{low}, {high}]")

    for _ in range(200):
        middle = 0.5 * (low + high)
        if cdf(middle) < p:
            low = middle
        else:
            high = middle
        if high - low < tolerance:
            break
    return 0.5 * (low + high)


def _check_probability(p: float) -> None:
    if not (0.0 <= p <= 1.0) or math.isnan(p):
        raise MathError(f"probability must lie in [0, 1], got {p}")


# ---------------------------------------------------------------------------
# Small helpers used across the pricing code
# ---------------------------------------------------------------------------


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def annualised(rate_per_period: float, periods_per_year: float) -> float:
    """Convert a per period event rate to a yearly one."""
    return rate_per_period * periods_per_year


def rate_for_window(annual_rate: float, days: float) -> float:
    """The expected event count over a window of a given length in days."""
    if days < 0:
        raise MathError(f"window must not be negative, got {days}")
    return annual_rate * days / 365.25
