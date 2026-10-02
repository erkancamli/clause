"""What the platform earns from the companies that write on it, and the
statement each company gets for it.

The buyer pays the pool's premium and, on top, the issuing company's
fronting fee. The platform takes nothing from the buyer: the price on the
screen is the pool's price, and stays so. It takes its fee from the
company, out of the fronting fee, the moment that fee is paid:

    platform fee = PLATFORM_FEE_RATE x premium, never more than the fee itself

so a company that charges no fee owes nothing, and a company that charges
five per cent keeps four. With an instalment plan the fee arrives in parts
and the platform's share of each part is proportional. When a fee comes
back to the buyer (a mistake undone within the hour, a cooling off period)
the platform's share comes back too, from the platform's own account.

Every movement is an entry here: which company, which policy, what kind,
how much, when. A month's entries for a company are its statement. Nothing
in the statement is computed after the fact from rates that may have
changed: the entries are what happened.

A policy is counted once, in the month it was written, and its premium with
it. That has to be said because an instalment plan writes a fee entry every
month it pays, and counting those is counting the same policy again: a
twelve month plan on a 1,000 premium was measured reporting twelve policies
and 12,000 written, and four entries in one month reported four policies and
4,000. The money columns were right either way. The two volume columns are
what a delegated authority desk reconciles first, and the rate an operator
divides out of them read 0.083% against a stated 1%.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

PLATFORM_FEE_RATE = 0.01
PLATFORM_ACCOUNT = "platform"

KINDS = ("fronting_fee", "fronting_fee_returned", "platform_fee", "platform_fee_returned")


def month_of(at: float) -> str:
    return dt.datetime.fromtimestamp(at, dt.timezone.utc).strftime("%Y-%m")


def platform_share(premium: float, fee: float, rate: float = PLATFORM_FEE_RATE) -> float:
    """The platform's fee on one policy: a share of the premium, capped by the
    company's fee, since it is taken out of that and nothing else."""
    if fee <= 0 or premium <= 0:
        return 0.0
    return round(min(fee, premium * rate), 2)


@dataclass(slots=True)
class FeeEntry:
    entry_id: str
    at: float
    month: str
    carrier_id: str
    policy_id: str
    holder: str
    kind: str                # one of KINDS
    amount: float            # always positive; the kind says which way it went
    premium: float           # the policy's premium, for the statement line

    def to_dict(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id, "at": self.at, "month": self.month,
                "carrier_id": self.carrier_id, "policy_id": self.policy_id, "holder": self.holder,
                "kind": self.kind, "amount": round(self.amount, 2), "premium": round(self.premium, 2)}


class Fees:
    def __init__(self, rate: float = PLATFORM_FEE_RATE) -> None:
        self.rate = rate
        self.entries: dict[str, FeeEntry] = {}
        self.lock = threading.RLock()

    def record(self, *, carrier_id: str, policy_id: str, holder: str, kind: str,
               amount: float, premium: float, now: float | None = None) -> FeeEntry | None:
        if kind not in KINDS:
            raise ValueError(f"unknown fee entry kind {kind!r}")
        amount = round(float(amount), 2)
        if amount <= 0:
            return None
        at = time.time() if now is None else now
        entry = FeeEntry(entry_id="FEE-" + secrets.token_hex(6).upper(), at=at, month=month_of(at),
                         carrier_id=carrier_id, policy_id=policy_id, holder=holder,
                         kind=kind, amount=amount, premium=round(float(premium), 2))
        with self.lock:
            self.entries[entry.entry_id] = entry
        return entry

    # -- statements -----------------------------------------------------------

    def months(self, carrier_id: str | None = None) -> list[str]:
        """Every month with an entry, newest first."""
        seen = {e.month for e in self.entries.values() if carrier_id is None or e.carrier_id == carrier_id}
        return sorted(seen, reverse=True)

    def written_in(self) -> dict[str, str]:
        """The month each policy was written in: the month of its earliest
        fee entry, whatever months the instalments after it fall in."""
        first: dict[str, float] = {}
        month: dict[str, str] = {}
        for e in self.entries.values():
            if e.kind not in ("fronting_fee", "platform_fee"):
                continue
            if e.policy_id not in first or e.at < first[e.policy_id]:
                first[e.policy_id] = e.at
                month[e.policy_id] = e.month
        return month

    def statement(self, carrier_id: str, month: str, *, names: dict[str, str] | None = None) -> dict[str, Any]:
        """One company's month: the lines, and the totals they add up to."""
        rows = sorted((e for e in self.entries.values() if e.carrier_id == carrier_id and e.month == month),
                      key=lambda e: e.at)
        return self._summarise(rows, carrier_id=carrier_id, month=month, names=names,
                               written=self.written_in())

    def statements(self, month: str, *, names: dict[str, str] | None = None) -> list[dict[str, Any]]:
        """Every company's statement for a month, for the operator."""
        by_carrier: dict[str, list[FeeEntry]] = {}
        for e in self.entries.values():
            if e.month == month:
                by_carrier.setdefault(e.carrier_id, []).append(e)
        written = self.written_in()
        return [self._summarise(sorted(rows, key=lambda e: e.at), carrier_id=c, month=month,
                                names=names, written=written)
                for c, rows in sorted(by_carrier.items())]

    def platform_totals(self) -> dict[str, Any]:
        """What the platform has taken and given back, all time and by month."""
        by_month: dict[str, dict[str, float]] = {}
        taken = returned = 0.0
        # Two passes over the entries, and no sort: Rewards.sweep asks for
        # the budget once per ended policy, so this is called about as many
        # times as there are policies, and nothing here needs the entries in
        # order. Measured at 8,000 entries, the sort was 0.5 ms of each call.
        written = self.written_in()
        counted: set[str] = set()
        for e in self.entries.values():
            row = by_month.setdefault(e.month, {"platform_fees": 0.0, "platform_fees_returned": 0.0, "premiums": 0.0,
                                                "policies": 0})
            if e.kind == "platform_fee":
                row["platform_fees"] += e.amount; taken += e.amount
                # The policy and its premium belong to the month it was
                # written, and to that month only, however many instalments
                # pay the fee afterwards.
                if e.policy_id not in counted and written.get(e.policy_id, e.month) == e.month:
                    counted.add(e.policy_id)
                    row["premiums"] += e.premium; row["policies"] += 1
            elif e.kind == "platform_fee_returned":
                row["platform_fees_returned"] += e.amount; returned += e.amount
        return {"rate": self.rate, "platform_fees": round(taken, 2), "platform_fees_returned": round(returned, 2),
                "net": round(taken - returned, 2),
                "by_month": {m: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}
                             for m, r in sorted(by_month.items(), reverse=True)}}

    @staticmethod
    def _summarise(rows: Iterable[FeeEntry], *, carrier_id: str, month: str,
                   names: dict[str, str] | None,
                   written: dict[str, str] | None = None) -> dict[str, Any]:
        rows = list(rows)
        written = written or {}
        totals = {k: 0.0 for k in KINDS}
        policies: set[str] = set()
        premiums = 0.0
        for e in rows:
            totals[e.kind] += e.amount
            # Written this month, and not already counted in it: an
            # instalment's fee is this month's money and last month's policy.
            if (e.kind == "fronting_fee" and e.policy_id not in policies
                    and written.get(e.policy_id, e.month) == month):
                policies.add(e.policy_id)
                premiums += e.premium
        fees_net = totals["fronting_fee"] - totals["fronting_fee_returned"]
        platform_net = totals["platform_fee"] - totals["platform_fee_returned"]
        return {
            "carrier_id": carrier_id, "carrier": (names or {}).get(carrier_id, carrier_id), "month": month,
            "policies": len(policies), "premiums_written": round(premiums, 2),
            "fronting_fees": round(totals["fronting_fee"], 2),
            "fronting_fees_returned": round(totals["fronting_fee_returned"], 2),
            "platform_fees": round(totals["platform_fee"], 2),
            "platform_fees_returned": round(totals["platform_fee_returned"], 2),
            # What the company was left with: its fees, less what came back, less the platform's share.
            "net_to_company": round(fees_net - platform_net, 2),
            "lines": [e.to_dict() for e in rows],
        }

    @staticmethod
    def csv(statement: dict[str, Any]) -> str:
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["entry_id", "at", "month", "carrier", "policy_id", "holder", "kind", "amount", "premium"])
        for line in statement["lines"]:
            w.writerow([line["entry_id"],
                        dt.datetime.fromtimestamp(line["at"], dt.timezone.utc).isoformat(timespec="seconds"),
                        line["month"], statement["carrier"], line["policy_id"], line["holder"], line["kind"],
                        f'{line["amount"]:.2f}', f'{line["premium"]:.2f}'])
        w.writerow([])
        for key in ("policies", "premiums_written", "fronting_fees", "fronting_fees_returned",
                    "platform_fees", "platform_fees_returned", "net_to_company"):
            w.writerow([key, statement[key]])
        return out.getvalue()
