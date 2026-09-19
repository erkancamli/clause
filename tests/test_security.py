"""The refusals, tested one by one against the audit that found them missing.

Each test here names the finding it closes. A regression in this file is not a
cosmetic failure: every one of these was, at some point in this project's life,
an open door on a server about to face the internet.
"""

from __future__ import annotations

import os
import time

import pytest

from clause.api.security import (
    MAX_LIMIT,
    MAX_TERM_DAYS,
    RateLimiter,
    Refused,
    Settings,
    bounded,
    clean_subject,
    finite,
    looks_like_address,
    safe_detail,
)


# ---------------------------------------------------------------------------
# Finding 4: Infinity through JSON, straight into the ledger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_numbers_are_refused(value: float) -> None:
    """Field(gt=0) lets Infinity through, because Infinity is greater than zero."""
    with pytest.raises(Refused) as caught:
        finite(value, "amount")
    assert caught.value.status_code == 422


def test_an_ordinary_number_passes() -> None:
    assert finite(12.5, "amount") == 12.5


def test_bounds_are_enforced_at_both_ends() -> None:
    assert bounded(100.0, "limit", 1.0, 1000.0) == 100.0
    for bad in (0.5, 1001.0):
        with pytest.raises(Refused):
            bounded(bad, "limit", 1.0, 1000.0)


def test_an_unbounded_term_is_refused() -> None:
    """A term long enough to overflow gives a policy that never ends."""
    with pytest.raises(Refused):
        bounded(1e9, "term_days", 0.5, MAX_TERM_DAYS)


def test_an_absurd_limit_is_refused() -> None:
    with pytest.raises(Refused):
        bounded(MAX_LIMIT * 10, "limit", 1.0, MAX_LIMIT)


# ---------------------------------------------------------------------------
# Finding 7: the subject was a free form document held forever
# ---------------------------------------------------------------------------


def test_a_normal_subject_passes_through() -> None:
    cleaned = clean_subject({"location": "IST-KADIKOY", "radius_km": 50})
    assert cleaned == {"location": "IST-KADIKOY", "radius_km": 50.0}


def test_a_megabyte_flight_number_is_refused() -> None:
    """It became a dict key, part of a predicate, and part of every response."""
    with pytest.raises(Refused):
        clean_subject({"flight_number": "T" * 100_000})


def test_a_subject_with_too_many_fields_is_refused() -> None:
    with pytest.raises(Refused):
        clean_subject({f"k{i}": i for i in range(40)})


def test_a_nested_subject_is_refused() -> None:
    with pytest.raises(Refused):
        clean_subject({"location": {"deeply": {"nested": 1}}})


def test_an_empty_or_wrong_typed_subject_is_refused() -> None:
    for bad in ({}, [], "IST", None):
        with pytest.raises(Refused):
            clean_subject(bad)  # type: ignore[arg-type]


def test_infinity_inside_a_subject_is_refused_too() -> None:
    with pytest.raises(Refused):
        clean_subject({"radius_km": float("inf")})


def test_a_boolean_is_not_a_number_here() -> None:
    """True == 1 in Python, and a silently coerced flag is a bug waiting."""
    with pytest.raises(Refused):
        clean_subject({"radius_km": True})


# ---------------------------------------------------------------------------
# Finding 9: addresses used as keys without being checked
# ---------------------------------------------------------------------------


def test_an_address_must_have_the_right_shape() -> None:
    good = "0x" + "ab" * 20
    assert looks_like_address(good) == good
    # The base58 form Rialo shows is an address too; the old hex form stays one.
    assert looks_like_address("HddrYhoVi2UAGXvJuCCZMECGGcdjK6FfwHB9cb9vpCJV") == "HddrYhoVi2UAGXvJuCCZMECGGcdjK6FfwHB9cb9vpCJV"
    for bad in ["", "0x", "nope", "0x" + "zz" * 20, "0x" + "ab" * 19, "HddrYhoVi2UAGXvJuCCZMECGGcdjK6FfwHB9cb9vpCJ0"]:
        with pytest.raises(Refused):
            looks_like_address(bad)


# ---------------------------------------------------------------------------
# Finding 3: one laptop in a loop
# ---------------------------------------------------------------------------


def test_a_caller_is_cut_off_after_its_allowance() -> None:
    limiter = RateLimiter()
    for _ in range(5):
        limiter.check("1.2.3.4", "quote", limit=5, window=60)
    with pytest.raises(Refused) as caught:
        limiter.check("1.2.3.4", "quote", limit=5, window=60)
    assert caught.value.status_code == 429


def test_one_caller_being_limited_does_not_limit_another() -> None:
    limiter = RateLimiter()
    for _ in range(5):
        limiter.check("1.2.3.4", "quote", limit=5, window=60)
    limiter.check("5.6.7.8", "quote", limit=5, window=60)


def test_classes_of_work_are_limited_separately() -> None:
    """Quoting runs a simulation. Reading blocks does not."""
    limiter = RateLimiter()
    for _ in range(5):
        limiter.check("1.2.3.4", "quote", limit=5, window=60)
    limiter.check("1.2.3.4", "read", limit=5, window=60)


def test_the_window_lets_a_caller_back_in() -> None:
    limiter = RateLimiter()
    limiter.check("1.2.3.4", "quote", limit=1, window=0.05)
    with pytest.raises(Refused):
        limiter.check("1.2.3.4", "quote", limit=1, window=0.05)
    time.sleep(0.06)
    limiter.check("1.2.3.4", "quote", limit=1, window=0.05)


def test_idle_callers_are_swept_so_the_table_cannot_be_grown() -> None:
    limiter = RateLimiter()
    limiter.check("old", "read", limit=10, window=60)
    for bucket in limiter._buckets.values():
        bucket.hits[0] = time.time() - 10_000
    limiter._last_sweep = 0.0
    limiter.check("new", "read", limit=10, window=60)
    assert ("old", "read") not in limiter._buckets


# ---------------------------------------------------------------------------
# Finding 2: the demo endpoints
# ---------------------------------------------------------------------------


def test_demo_endpoints_are_off_by_default() -> None:
    settings = Settings()
    assert settings.demo_endpoints is False
    assert settings.faucet is False
    assert settings.public_docs is False
    assert settings.allowed_origins == ()


def test_a_demo_endpoint_is_invisible_when_disabled() -> None:
    """Not 401, which would confirm it exists. It is simply not there."""
    with pytest.raises(Refused) as caught:
        Settings().require_operator("anything")
    assert caught.value.status_code == 404


def test_a_demo_endpoint_needs_the_right_token() -> None:
    settings = Settings(demo_endpoints=True, operator_token="s3cret")
    settings.require_operator("s3cret")
    for wrong in (None, "", "s3cres", "s3cret ", "much longer than the token"):
        with pytest.raises(Refused) as caught:
            settings.require_operator(wrong)
        assert caught.value.status_code == 401


def test_a_demo_build_refuses_to_start_without_a_token() -> None:
    """Otherwise the safe default is one environment variable away from unsafe."""
    keep = dict(os.environ)
    try:
        os.environ["CLAUSE_DEMO"] = "1"
        os.environ.pop("CLAUSE_OPERATOR_TOKEN", None)
        with pytest.raises(RuntimeError):
            Settings.from_env()
    finally:
        os.environ.clear()
        os.environ.update(keep)


def test_settings_read_from_the_environment() -> None:
    keep = dict(os.environ)
    try:
        os.environ.update({
            "CLAUSE_DEMO": "1",
            "CLAUSE_OPERATOR_TOKEN": "token",
            "CLAUSE_ORIGINS": "https://clause.insure, https://www.clause.insure",
            "CLAUSE_FAUCET": "1",
        })
        settings = Settings.from_env()
        assert settings.demo_endpoints and settings.faucet
        assert settings.allowed_origins == (
            "https://clause.insure", "https://www.clause.insure",
        )
        assert settings.public_docs is False
    finally:
        os.environ.clear()
        os.environ.update(keep)


# ---------------------------------------------------------------------------
# Finding 6: error text as a balance oracle
# ---------------------------------------------------------------------------


def test_internal_detail_does_not_reach_the_caller() -> None:
    error = RuntimeError("0xabc holds 12,345.67 against a required 50,000.00")
    shown = safe_detail(error, fallback="that request could not be completed")
    assert "12,345" not in shown
    assert shown == "that request could not be completed"
