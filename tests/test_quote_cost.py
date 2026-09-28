"""What a quote costs, and that cutting the cost changed no figure.

An earthquake quote on shaking took twelve seconds on the live server, and
the page gave up before it came: the capital model walked the address's
rate table on every one of its trials, and the capacity checks that follow
a quote simulated the whole book twice more with the candidate in it. The
draw now binary searches a cumulative table kept per address, and the
checks add the settled candidate to the cached book. Every number that
comes out has to be the number that came out before.
"""

from __future__ import annotations

import random

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.perils import EARTHQUAKE, shaking as sh
from clause.pricing import Exposure, capital_from_losses
from clause.pricing.simulation import settle

KADIKOY = {"latitude": 40.99, "longitude": 29.03, "radius_km": 50, "index": "shaking", "built": 1998}


def walk(rng: random.Random, subject: dict, part: str, magnitude_below: float | None) -> list[float]:
    """The draw as it was first written: the table walked for every event."""
    rows = [row for row in sh.density(subject, part)
            if magnitude_below is None or row[0] < magnitude_below]
    total = sum(r for _, _, r in rows)
    if total <= 0:
        return []
    count = sh._poisson(rng, total)
    out = []
    for _ in range(count):
        target, acc = rng.random() * total, 0.0
        for m, d, r in rows:
            acc += r
            if acc >= target:
                out.append(sh.mmi(m, d) + rng.gauss(0.0, sh.IPE_SIGMA))
                break
    return out


def test_the_cached_draw_is_the_table_walk_event_for_event() -> None:
    subject = EARTHQUAKE.validate_subject(dict(KADIKOY))
    for part, below in (("background", None), ("all", 6.5), ("all", None)):
        a, b = random.Random(f"{part}:{below}"), random.Random(f"{part}:{below}")
        drawn = [sh.draw(a, subject, part, magnitude_below=below) for _ in range(3000)]
        walked = [walk(b, subject, part, below) for _ in range(3000)]
        assert drawn == walked
        assert any(drawn), "a year with no event at all, three thousand times over"


def test_the_capacity_checks_see_the_book_the_quote_saw() -> None:
    app = create_app(trials=1500, seed=4, run_chain=False, seed_book=True, settings=Settings(faucet=True))
    pool, engine = app.state.pool, app.state.pool.engine
    subject = EARTHQUAKE.validate_subject(dict(KADIKOY))
    candidate = Exposure("candidate", "earthquake", subject, EARTHQUAKE.curve_for(subject), 50_000.0, 365.0)
    # Straight from the definitions, with nothing cached.
    direct = engine.simulate(pool.exposures(candidate)).losses
    assert pool.largest_single_event_loss(candidate) == max(direct)
    assert pool.required_capital(candidate) == capital_from_losses(direct, engine.trials).solvency_capital * pool.capital_buffer
    # The candidate settled once and remembered; the book cached on its own
    # membership, not on a membership that has the candidate in it.
    assert engine.losses_of(candidate) is engine.losses_of(Exposure(
        "candidate", "earthquake", dict(subject), EARTHQUAKE.curve_for(subject), 50_000.0, 365.0))
    assert engine.losses_of(candidate) == settle(candidate, engine.draws)
    assert engine._book_cache is not None and "candidate" not in engine._book_cache[0]
    # A different candidate is not the same candidate.
    other = Exposure("candidate", "earthquake", subject, EARTHQUAKE.curve_for(subject), 60_000.0, 365.0)
    assert engine.losses_of(other) is not engine.losses_of(candidate)


def test_the_contract_is_written_on_the_price_the_page_was_given() -> None:
    """The confirm step's calls, in the order the page now makes them: offers,
    the quote, then the contract carrying the quote's lock.

    The price the page is given is an offer's, not the pool's. Companies price
    the same risk themselves, so the quote is the floor under a price rather
    than a price anybody charges, and the contract names the company that
    would issue the cover and what that company asks for it.
    """
    app = create_app(trials=800, seed=6, run_chain=False, seed_book=True, settings=Settings(faucet=True))
    subject = {**KADIKOY, "place": "Kadıköy"}
    body = {"peril": "earthquake", "subject": subject, "limit": 50_000, "term_days": 365}
    with TestClient(app) as client:
        offers = client.post("/api/offers?country=TR&professional=false", json=body)
        assert offers.status_code == 200, offers.text
        quoted = client.post("/api/quote", json=body)
        assert quoted.status_code == 200, quoted.text
        # The pool's own arithmetic, which every company starts from.
        assert quoted.json()["premium"] == offers.json()["premium"]
        cheapest = offers.json()["offers"][0]
        interest = {"what": "a flat", "country": "TR", "inside_trigger_area": True, "value_at_risk": 90_000,
                    "size": {"kind": "home", "building": "flat", "area_m2": 150, "built": 1998}, "professional": False}
        contract = client.post("/api/contract", json={**body, "interest": interest, "settlement": "fiat",
                                                       "instalments": 1, "quote_id": quoted.json()["lock"]["id"]})
        assert contract.status_code == 200, contract.text
        assert contract.json()["premium"] == cheapest["premium"], (
            "the contract is written on a price no company was offering")
        assert f'{cheapest["premium"]:,.2f}' in contract.json()["text"]
