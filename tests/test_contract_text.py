"""The document a buyer signs, read as a document.

An independent pass found that printing twice the policy's ceiling in section
2 passed 87 tests across the ten files that touch /api/contract, and so did
deleting two of the promises the contract makes. Only section 10, the premium
figure and the storm title were ever read. The contract is the binding
artefact of this product, so the figures in it and the sentences that limit
what the insurer may do are pinned here.

Nothing in this file is about wording for its own sake. Each assertion is
either a figure that has to be the policy's own, or a sentence whose absence
would change what the insurer could do.
"""

from __future__ import annotations

import re

import pytest

from clause.perils import DROUGHT, EARTHQUAKE, FLIGHT_DELAY, STORM, VEHICLE_FLOOD
from clause.protocol import contract as contract_module

LIMIT = 100_000.0
PREMIUM = 15_372.84
FEE = 329.23
TERM = 365.0
BOUGHT = 1_792_740_000.0
STARTS = 1_793_000_000.0


def written(peril, subject, **over):
    terms = dict(
        peril=peril, subject=peril.validate_subject(subject), limit=LIMIT,
        term_days=TERM, premium=PREMIUM, fee=FEE, carrier=None,
        holder="ADDRESS", country="TR",
        cancellation={"days": 14, "basis": "pro rata"},
        starts_at=STARTS, bought_at=BOUGHT,
        value_basis="rebuild cost at 517 USDC per square metre",
    )
    terms.update(over)
    return contract_module.render(**terms)


QUAKE = {"latitude": 40.99, "longitude": 29.03, "radius_km": 50.0,
         "built": 2005, "place": "İstanbul, Kadıköy"}
WEATHER = {"latitude": 41.0, "longitude": 28.9}
FIELD = {"station": "TR-KONYA", "distance_km": 8.0, "hectares": 50.0}

EVERY_PERIL = [("earthquake", EARTHQUAKE, QUAKE),
               ("storm", STORM, WEATHER),
               ("vehicle_flood", VEHICLE_FLOOD, WEATHER)]


# -- the figures ------------------------------------------------------------

@pytest.mark.parametrize("name,peril,subject", EVERY_PERIL)
def test_the_ceiling_is_the_policys_own(name, peril, subject) -> None:
    """Section 2's figure. Printed at twice the limit, 87 tests passed."""
    text = written(peril, subject)
    assert f"The most this policy pays: {LIMIT:,.2f} USDC." in text, name
    # And no other amount is offered as the ceiling.
    for wrong in (LIMIT * 2, LIMIT / 2, LIMIT + 1):
        assert f"The most this policy pays: {wrong:,.2f} USDC." not in text


@pytest.mark.parametrize("limit", [1_000.0, 37_500.5, 250_000.0])
def test_the_ceiling_follows_the_limit_it_is_given(limit: float) -> None:
    text = written(EARTHQUAKE, QUAKE, limit=limit)
    assert f"The most this policy pays: {limit:,.2f} USDC." in text


def test_the_term_and_the_start_are_the_policys_own() -> None:
    text = written(EARTHQUAKE, QUAKE)
    assert f"Term: {TERM:g} days from " in text
    # Three days, which is the earthquake wait, counted from the two stamps.
    assert "3 days later" in text
    assert f"runs its full {TERM:g} days from there" in text


def test_the_ladder_in_the_document_is_the_policys_own_curve() -> None:
    subject = EARTHQUAKE.validate_subject(QUAKE)
    curve = EARTHQUAKE.curve_for(subject)
    unit = EARTHQUAKE.unit_for(subject)
    text = written(EARTHQUAKE, QUAKE)
    steps = EARTHQUAKE.reading_curve(subject, curve).describe(unit)
    assert steps
    for step in steps:
        assert step in text, step


# -- the sentences that limit what the insurer may do -----------------------

PROMISES = (
    # No reading, no cover: the premium comes back rather than being kept.
    "the premium is returned in full",
    # The indemnity limit, said as a limit.
    "it does not pay more than the ceiling whatever the loss",
    # What parametric means, said in the contract rather than in the copy.
    "with no claim, no assessor and no proof of loss",
)


@pytest.mark.parametrize("promise", PROMISES)
@pytest.mark.parametrize("name,peril,subject", EVERY_PERIL)
def test_every_contract_carries_every_promise(promise, name, peril,
                                              subject) -> None:
    text = written(peril, subject).lower()
    assert promise.lower() in text, f"{name} does not say {promise!r}"


def section(text: str, number: int) -> str:
    """One numbered section of the contract, without the ones after it.

    Asked for because a promise searched for in the whole document is
    satisfied by any copy of it anywhere: "the premium is returned in full"
    is in section 3 and again in the rulebook's own silence line at the end,
    so deleting the one in section 3 left the document saying it once and
    every test green.
    """
    found = re.search(rf"^{number}\. .*?(?=^\d+\. |\Z)", text, re.S | re.M)
    assert found, f"section {number} is not in the contract"
    return found.group(0)


@pytest.mark.parametrize("name,peril,subject", EVERY_PERIL)
def test_the_silence_rule_is_in_the_section_about_paying(name, peril, subject) -> None:
    """No reading, no cover, said where a buyer looks for what they get."""
    paying = section(written(peril, subject), 3)
    assert "the premium is returned in full" in paying.lower(), name
    assert "if no reading is published" in paying.lower(), name


def test_cancellation_says_when_it_stops_being_possible() -> None:
    """Without it, a buyer who can see the event coming could still cancel,
    and the pool carries a policy nobody would keep.

    Asked inside section 6, because "cannot be cancelled" appears in the
    sentence beside it as well: deleting the line that names the trigger left
    the whole suite green.
    """
    cancelling = section(written(EARTHQUAKE, QUAKE), 6)
    assert "cannot be cancelled" in cancelling.lower()
    assert "nothing can be cancelled once the index has reached its trigger" in \
        cancelling.lower()
    assert "within one hour of buying" in cancelling.lower()


def test_the_document_names_who_is_liable_and_who_supervises_them() -> None:
    text = written(EARTHQUAKE, QUAKE)
    assert "1. The parties" in text
    assert "Insurer:" in text and "supervised by" in text
    assert "Policyholder:" in text
    assert "Capital:" in text


def test_the_index_and_its_publisher_are_named() -> None:
    for name, peril, subject in EVERY_PERIL:
        text = written(peril, subject)
        source = peril.data_source(peril.validate_subject(subject))
        assert source.publisher in text, name
        assert str(source.settlement_deadline_days) in text, name


def test_the_address_goes_in_when_there_is_one() -> None:
    """The contract is the one place the address belongs in full."""
    text = written(EARTHQUAKE, QUAKE, address={
        "street": "222. Cadde", "number": "14", "flat": "7",
        "postcode": "34303", "city": "Küçükçekmece"})
    assert "222. Cadde, 14, 7, 34303, Küçükçekmece" in text


def test_the_same_terms_write_the_same_document() -> None:
    """Deterministic in its inputs, which is what makes a hash of it mean
    anything."""
    assert written(EARTHQUAKE, QUAKE) == written(EARTHQUAKE, QUAKE)

# -- section 10, which is the one section the suite did read ---------------

@pytest.mark.parametrize("name,peril,subject", EVERY_PERIL)
def test_the_silence_rule_is_one_sentence(name, peril, subject) -> None:
    """Read off the live API, in the binding document:

        Silence: if no final figure has been published 7 days after the term
        ends, If the network publishes nothing for the radius within seven
        days of the term ending, the policy expires and the premium is
        returned in full..

    Each peril's on_missing_data is a whole sentence starting with a capital
    "If", and the rulebook interpolated it after a comma. Two sentences in
    one, a capital in the middle, the same deadline in two notations, and a
    doubled full stop, on every contract the protocol had written.
    """
    said = [line.strip() for line in written(peril, subject).splitlines()
            if line.strip().startswith("Silence:")]
    assert len(said) == 1, said
    line = said[0]
    assert ".." not in line, line
    assert line.endswith("."), line
    body = line[len("Silence: "):]
    # One sentence: nothing after the first full stop, and no capital letter
    # arriving mid-sentence where a clause was spliced in.
    assert body.count(".") == 1, line
    inside = body[:-1]
    assert " If " not in inside, line
    assert " if no final figure has been published" not in line, line


@pytest.mark.parametrize("name,peril,subject", EVERY_PERIL)
def test_the_silence_rule_still_says_what_happens(name, peril, subject) -> None:
    """Reading better is not the point if it stops saying the thing."""
    text = written(peril, subject)
    said = [line for line in text.splitlines()
            if line.strip().startswith("Silence:")][0].lower()
    assert "premium" in said and "returned in full" in said, said
    deadline = peril.data_source(peril.validate_subject(subject)) \
        .settlement_deadline_days
    in_words = {7: "seven", 14: "fourteen", 21: "twenty-one"}.get(deadline)
    assert in_words is None or in_words in said, (deadline, said)
