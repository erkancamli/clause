"""Validators reading the same thing, and what happens when they differ.

This is the case Rialo has not published a rule for, so it is the case Clause
has to be most explicit about. These tests are the specification.
"""

from __future__ import annotations

import pytest

from clause.chain.rex import (
    Aggregation,
    Aggregator,
    Agreement,
    RexReport,
    RexUpdate,
    authority_key,
    topic_for,
    shorten_topic,
)


def report(values, topic="topic:abc", field_name="max_magnitude", round_=10):
    out = RexReport(
        topic=topic, reference="api.seismic.example/v1/x",
        field=field_name, round=round_,
    )
    for index, value in enumerate(values):
        out.add(RexUpdate(validator=f"validator-{index}", value=value, round=round_))
    return out


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------


def test_agreeing_validators_settle_at_the_median() -> None:
    result = Aggregator().aggregate(report([7.18, 7.20, 7.22, 7.21]))
    assert result.agreement is Agreement.AGREED
    assert result.settles
    assert result.value == pytest.approx(7.205)


def test_the_median_ignores_one_validator_reading_nonsense() -> None:
    """A mean would be dragged by this. That is why it is not a mean."""
    clean = Aggregator().aggregate(report([7.20, 7.21, 7.19, 7.20]))
    assert clean.settles
    # One validator reports a corrupted figure. The median barely moves, but the
    # dispersion guard now refuses the round outright, which is the safer failure.
    dirty = Aggregator().aggregate(report([7.20, 7.21, 7.19, 71.0]))
    assert dirty.agreement is Agreement.DISPUTED
    assert dirty.median == pytest.approx(7.205)


def test_too_few_validators_is_not_a_reading() -> None:
    result = Aggregator().aggregate(report([7.2, 7.2]))
    assert result.agreement is Agreement.NO_QUORUM
    assert result.value is None
    assert "2 of 4" in result.note


def test_disagreement_beyond_tolerance_refuses_rather_than_averages() -> None:
    """The case that decides whether this is insurance or a coin toss."""
    result = Aggregator().aggregate(report([5.40, 5.42, 5.90, 5.95]))
    assert result.agreement is Agreement.DISPUTED
    assert not result.settles
    assert result.dispersion is not None and result.dispersion > 0.05


def test_a_reading_on_the_edge_of_tolerance_still_settles() -> None:
    # 5% of 100 is 5.0, so a spread of exactly 5 is inside the tolerance.
    result = Aggregator().aggregate(report([97.5, 100.0, 100.0, 102.5]))
    assert result.agreement is Agreement.AGREED
    assert result.dispersion == pytest.approx(0.05)


def test_unanimous_validators_have_no_dispersion() -> None:
    result = Aggregator().aggregate(report([42.0, 42.0, 42.0, 42.0]))
    assert result.settles
    assert result.spread == 0
    assert result.dispersion == 0


def test_a_median_of_zero_does_not_divide_by_zero() -> None:
    agreed = Aggregator().aggregate(report([0.0, 0.0, 0.0, 0.0]))
    assert agreed.settles
    split = Aggregator().aggregate(report([0.0, 0.0, 0.0, 4.0]))
    assert split.agreement is Agreement.DISPUTED


# ---------------------------------------------------------------------------
# The quorum, which has to hold at any validator count
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "validators, expected",
    [(4, 3), (7, 6), (10, 8), (2, 2), (3, 3), (100, 75)],
)
def test_quorum_rounds_up_and_never_falls_below_two(validators, expected) -> None:
    assert Aggregator(validators=validators).quorum == expected


def test_quorum_cannot_exceed_the_validator_set() -> None:
    assert Aggregator(validators=3, quorum_share=1.0).quorum == 3


def test_a_bad_quorum_share_is_refused() -> None:
    for share in (0.0, -0.2, 1.5):
        with pytest.raises(ValueError):
            Aggregator(quorum_share=share)


def test_a_negative_tolerance_is_refused() -> None:
    with pytest.raises(ValueError):
        Aggregator(dispersion_tolerance=-0.1)


# ---------------------------------------------------------------------------
# What the buyer is told
# ---------------------------------------------------------------------------


def test_the_rule_is_stated_in_terms_a_buyer_can_read() -> None:
    text = Aggregator().describe()
    assert "3 of 4" in text
    assert "median" in text
    assert "5%" in text


def test_every_verdict_carries_its_own_working() -> None:
    """An auditor recomputes the figure from the report, not from our word."""
    result = Aggregator().aggregate(report([7.18, 7.20, 7.22, 7.21]))
    assert result.reported == 4
    assert result.expected == 4
    assert len(result.updates) == 4
    assert all(u.key.startswith("0x") for u in result.updates)
    payload = result.to_dict()
    assert payload["agreement"] == "agreed"
    assert len(payload["updates"]) == 4


def test_a_validator_key_has_the_published_shape() -> None:
    """Rialo authority keys are 96 byte BLS12-381 keys, shown as hex."""
    key = authority_key("validator-0")
    assert key.startswith("0x")
    assert len(key) == 2 + 96
    assert key != authority_key("validator-1")


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


def test_one_source_and_field_give_one_topic() -> None:
    """Which is what lets a single reading settle a whole book at once."""
    a = topic_for("api.seismic.example/v1/x", "max_magnitude")
    b = topic_for("api.seismic.example/v1/x", "max_magnitude")
    assert a == b


def test_a_different_field_is_a_different_topic() -> None:
    a = topic_for("api.meteo.example/v1/konya", "rainfall_mm")
    b = topic_for("api.meteo.example/v1/konya", "window_closed")
    assert a != b


def test_a_topic_shortens_for_display_without_losing_its_ends() -> None:
    topic = topic_for("api.seismic.example/v1/x", "max_magnitude")
    short = shorten_topic(topic)
    assert short.endswith(topic[-4:])
    assert len(short) < len(topic)
