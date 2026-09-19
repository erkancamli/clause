"""The policy as a document: what the buyer reads and accepts before signing.

A parametric policy is short enough to read in full, so it is shown in full,
and the buyer's signature over the terms covers the hash of this exact text.
The protocol rebuilds the text from the same inputs when the application
arrives and refuses to proceed if the hash the buyer accepted is not the hash
of what it would issue: nothing can be accepted unread, and nothing can change
between the reading and the signing.

The document has the parts distance selling rules ask an insurer to give
before a contract is made (the insurer, what is covered and what is not, the
price and how it is paid, the right to cancel, the law, complaints), written
in plain words. English is the binding text; the site shows a translation
beside it and says so.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

VERSION = "2026-09"


def _money(value: float) -> str:
    return f"{value:,.2f} USDC"


def _when(seconds: float) -> str:
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).strftime("%d %B %Y")


def render(
    *, peril: Any, subject: dict[str, Any], limit: float, term_days: float,
    premium: float, fee: float, carrier: dict[str, Any] | None, holder: str,
    country: str, cancellation: dict[str, Any], plan: dict[str, Any] | None = None,
    starts_at: float | None = None, address: dict[str, Any] | None = None,
    value_basis: str = "",
) -> str:
    """The contract, as plain text with headings. Deterministic in its inputs."""
    curve = peril.curve_for(subject)
    unit = peril.unit_for(subject)
    source = peril.data_source(subject)
    company = (carrier or {}).get("name") or "the issuing company named at approval"
    authority = (carrier or {}).get("authority") or "its insurance supervisor"
    specimen = bool((carrier or {}).get("specimen"))
    steps = "\n".join(f"    {line}" for line in curve.describe(unit))
    where = peril.describe_subject(subject)
    if address:
        parts = [address.get(k, "") for k in ("street", "number", "flat", "postcode", "city")]
        where = ", ".join(str(p) for p in parts if p) + f" ({where})"
    start = _when(starts_at) if starts_at else "the day the application is approved"
    cool = cancellation.get("cooling_off_days", 0)
    law = cancellation.get("law", "")
    if not plan or plan.get("count", 1) <= 1:
        pay = (f"{_money(premium)} premium and {_money(fee)} issuing fee, {_money(premium + fee)} in all, "
               f"paid in full on approval")
    else:
        surcharge = float(plan.get("surcharge_total", 0.0))
        amounts = plan.get("amounts") or [plan["amount"]] * int(plan["count"])
        each = (f"{_money(amounts[0])} each" if len(set(amounts)) == 1
                else f"{_money(amounts[0])} each and {_money(amounts[-1])} for the last")
        pay = (f"{_money(premium)} premium and {_money(fee)} issuing fee"
               + (f" and {_money(surcharge)} for paying in parts ({plan['surcharge']:.0%})" if surcharge > 0 else "")
               + f", {_money(plan['total'])} in all, in {plan['count']} instalments of {each}: the first on "
               f"approval and one every {plan['every_days']:g} days after it, taken from the holder's address; a "
               f"missed instalment not paid within {plan['grace_days']:g} days ends the policy, and "
               f"any premium still owed when a payout is made is deducted from it. A refund returns "
               f"what has been paid, less the cover already used")
    short = cancellation.get("short_cover_days", 30)
    lines = [
        f"CLAUSE PARAMETRIC POLICY · contract version {VERSION}",
        "",
        "1. The parties",
        f"    Insurer: {company}, supervised by {authority}."
        + (" This company is a specimen, not a real company; nothing in this document is real cover." if specimen else ""),
        f"    Policyholder: the person controlling the address that signs this contract, resident in {country}. The address is on the policy record and its token.",
        "    Capital: the Clause pool on Rialo, which stands behind every payout.",
        "",
        "2. What is insured",
        f"    {peril.title_for(subject)}.",
        f"    Where: {where}.",
        f"    The most this policy pays: {_money(limit)}." + (f" Basis of that ceiling: {value_basis}." if value_basis else ""),
        f"    Term: {term_days:g} days from {start}.",
        "",
        "3. When it pays, and how much",
        f"    The index is {peril.index_name}, measured in {unit}, published by {source.publisher}.",
        "    It pays these shares of the ceiling at these readings, with no claim, no assessor and no proof of loss:",
        steps,
        f"    A payout is made in the block that carries the final reading, after a correction window, to the policyholder's address.",
        f"    If no reading is published within {source.settlement_deadline_days} days of the term ending, the premium is returned in full.",
        "",
        "4. What it does not do",
        f"    {peril.basis_risk}",
        "    It does not pay for damage from anything other than the index reaching its trigger, and it does not pay more than the ceiling whatever the loss.",
        "",
        "5. The price",
        f"    {pay}.",
        "    A commission paid to a partner who sold this policy is not returned on cancellation.",
        "",
        "6. The right to cancel",
        "    Within one hour of buying, for any reason, the whole premium and fee come back.",
        (f"    Within {cool:g} days of buying, under {law}, the whole premium and fee come back."
         if cool else f"    Cover of {short:g} days or less has no cooling off period under the law that applies."),
        ("    After that, the unexpired part of the premium comes back on cancellation."
         if cancellation.get("pro_rata_after") else
         "    After that the policy runs to the end of its term; it cannot be cancelled once the season or the flight can be seen."),
        "    Nothing can be cancelled once the index has reached its trigger.",
        "",
        "7. Before the policy is issued",
        "    The insurer screens the policyholder against sanctions lists and, above 10,000 USDC of cover, confirms their identity and their interest in what is insured (title, lease or registration). The premium is held, not taken, until it decides; a rejection or no decision within three days returns everything.",
        "",
        "8. Records",
        "    The policy is registered on chain as a token that cannot be transferred, naming this document by its hash. Every reading, every validator report and the settlement itself are on chain and can be read by anyone.",
        "    The protocol keeps the terms, the address of what is insured and the outcome of the insurer's checks, and nothing that identifies the policyholder beyond their address.",
        "",
        "9. Law and complaints",
        f"    This contract is governed by the law of {country}, where the policyholder is resident, and disputes go to its courts and its insurance ombudsman. Complaints go first to the insurer at the contact it gave when it registered.",
        "    The English text of this document is the binding one; translations are for convenience.",
    ]
    return "\n".join(lines)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
