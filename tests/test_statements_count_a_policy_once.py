"""A policy appears in one month's statement, in the month it was written.

An instalment plan pays the issuing fee in parts, and every part is a fee
entry. The statement de-duplicated within a month but not across months, and
the platform's own totals de-duplicated nowhere, so the same policy was
counted once per instalment and its whole premium added again each time.

Measured before the fix, one policy with a 1,000.00 premium and a 60.00 fee
paid in twelve monthly parts:

    month                 policies  premiums_written
    2026-01 ... 2026-12          1          1,000.00   (each of twelve)
    TOTAL                       12         12,000.00
    truth                        1          1,000.00

and four parts inside a single month reported four policies and 4,000.00 in
one row. The money columns were right throughout; these two are the ones a
delegated authority desk reconciles first, and the platform publishes its
rate beside them, so an operator dividing one by the other read 0.083% for
a monthly plan against a stated 1%.
"""

from __future__ import annotations

import datetime as dt

import pytest

from clause.protocol.fees import Fees, platform_share
from clause.protocol.instalments import _parts

PREMIUM, FEE = 1000.0, 60.0
JANUARY = dt.datetime(2026, 1, 15, 12, tzinfo=dt.timezone.utc).timestamp()
MONTH = 30.5 * 86400.0


def paid_in(count: int, *, every: float = MONTH, policy: str = "CLS-1") -> Fees:
    """One policy whose fee arrives in ``count`` parts, ``every`` seconds apart."""
    fees = Fees()
    fee_parts = _parts(FEE, count)
    share_parts = _parts(platform_share(PREMIUM, FEE), count)
    for i in range(count):
        at = JANUARY + i * every
        for kind, amounts in (("fronting_fee", fee_parts), ("platform_fee", share_parts)):
            fees.record(carrier_id="C1", policy_id=policy, holder="buyer", kind=kind,
                        amount=amounts[i], premium=PREMIUM, now=at)
    return fees


def test_a_year_of_instalments_is_one_policy_and_one_premium() -> None:
    fees = paid_in(12)
    months = sorted(fees.months())
    assert len(months) == 12, "twelve months of entries, which is the point"
    rows = [fees.statement("C1", m) for m in months]
    assert sum(r["policies"] for r in rows) == 1
    assert sum(r["premiums_written"] for r in rows) == pytest.approx(1000.0, abs=0.01)
    # In the month it was written, and nowhere else.
    assert rows[0]["policies"] == 1 and rows[0]["premiums_written"] == pytest.approx(1000.0)
    assert all(r["policies"] == 0 and r["premiums_written"] == 0.0 for r in rows[1:])
    # And the money is still every month's own: the fee arrived in twelve parts.
    assert sum(r["fronting_fees"] for r in rows) == pytest.approx(60.0, abs=0.01)
    assert all(r["fronting_fees"] > 0 for r in rows)


def test_four_parts_inside_one_month_are_one_policy_too() -> None:
    fees = paid_in(4, every=2 * 86400.0)
    one = fees.statement("C1", "2026-01")
    assert one["policies"] == 1
    assert one["premiums_written"] == pytest.approx(1000.0, abs=0.01)
    assert one["fronting_fees"] == pytest.approx(60.0, abs=0.01)
    assert len(one["lines"]) == 8, "every entry is still a line on the statement"


def test_the_platforms_own_totals_count_the_same_way() -> None:
    by_month = paid_in(12).platform_totals()["by_month"]
    assert sum(r["policies"] for r in by_month.values()) == 1
    assert sum(r["premiums"] for r in by_month.values()) == pytest.approx(1000.0, abs=0.01)
    assert by_month["2026-01"]["policies"] == 1
    assert by_month["2026-06"]["policies"] == 0
    assert by_month["2026-06"]["platform_fees"] > 0, "the month's money is the month's"


def test_the_published_rate_divides_out_of_the_two_columns() -> None:
    """Which is what an operator checks, and what the counting broke."""
    totals = paid_in(12).platform_totals()
    fees_taken = totals["platform_fees"]
    written = sum(r["premiums"] for r in totals["by_month"].values())
    assert fees_taken / written == pytest.approx(totals["rate"], abs=0.0005)


def test_two_policies_in_a_month_are_two() -> None:
    """The de-duplication is per policy, not per month."""
    fees = paid_in(12)
    for kind, amount in (("fronting_fee", 5.0), ("platform_fee", 0.83)):
        fees.record(carrier_id="C1", policy_id="CLS-2", holder="buyer", kind=kind,
                    amount=amount, premium=500.0, now=JANUARY + 3600.0)
    one = fees.statement("C1", "2026-01")
    assert one["policies"] == 2
    assert one["premiums_written"] == pytest.approx(1500.0, abs=0.01)


def test_the_month_a_policy_was_written_in_is_its_earliest_entry() -> None:
    fees = paid_in(12)
    assert fees.written_in() == {"CLS-1": "2026-01"}
