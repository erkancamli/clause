"""The proof page opens with the record instead of asking for one.

Until now /api/lineage was the only way in, and it answers about a policy you
can already name. Somebody arriving at the proof page for the first time has no
id to give it, so the page opened with an empty box and proved nothing. The
register is the other half: which policies there are to ask about.

The tests that matter here are the two about what it refuses to flatter. A
register that only lists what paid is an advertisement, so the policies that ran
their term without the index reaching the line have to be in it; and the holder
has to stay out of it, because nothing in the argument needs to know whose
policy it was.
"""

from __future__ import annotations

import pytest

from conftest import start_cover
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.chain import Chain, ChainConfig
from clause.perils import EARTHQUAKE  # noqa: F401  (registers the peril)
from clause.pricing import PricingEngine
from clause.protocol import Pool, PolicyStatus
from clause.protocol.wallet import derive_address
from clause.chain.world import BLOCK_TIME_SECONDS

KADIKOY = "api.seismic.example/v1/max-magnitude?lat=40.99&lon=29.03&radius_km=50"
_GRACE_DAYS = 45.0


def blocks_for(term_days: float, config: ChainConfig) -> int:
    per_block = BLOCK_TIME_SECONDS * config.world_acceleration / 86400.0
    return int((term_days + _GRACE_DAYS) / per_block) + 200


def built(seed: int = 3):
    pool = Pool(engine=PricingEngine(trials=500, seed=seed))
    pool.deposit("lp", 20_000_000.0)
    config = ChainConfig(seed=seed)
    return pool, Chain(pool, config), config


def write(pool: Pool, chain: Chain, subject: dict, limit: float, term: float):
    policy = pool.write(
        peril_key="earthquake", subject=subject, limit=limit,
        term_days=term, holder="holder",
    )
    chain.register(policy)
    start_cover(chain, policy)
    return policy


def a_paid_and_an_untriggered_policy():
    """One policy the ground reached, and one it never did."""
    pool, chain, config = built()
    paid = write(pool, chain, {"location": "IST-KADIKOY", "radius_km": 50}, 100_000, 365)
    quiet = write(
        pool, chain,
        {"latitude": 38.46, "longitude": 27.22, "radius_km": 25.0}, 50_000, 30,
    )

    chain.attest(KADIKOY, "max_magnitude", 7.2)
    for _ in range(blocks_for(30, config)):
        chain.produce_block()
    return pool, chain, paid, quiet


def test_the_register_carries_what_did_not_pay_as_well_as_what_did() -> None:
    pool, chain, paid, quiet = a_paid_and_an_untriggered_policy()
    assert pool.policies[paid.policy_id].status is PolicyStatus.PAID

    rows = chain.recent_decisions(20)
    kinds = {row["policy_id"]: row["kind"] for row in rows}
    assert kinds.get(paid.policy_id) == "paid"
    assert kinds.get(quiet.policy_id) in {"lapsed", "expired"}

    settled = next(r for r in rows if r["policy_id"] == paid.policy_id)
    # A row has to say why on its own: the line that was written, the figure
    # that was read, and the block the two met in.
    assert settled["trigger"] > 0
    # What the row prints is the figure the validators agreed on, not the one
    # the test injected. Those are close but never identical, and printing the
    # injected one would be showing a number nothing on the chain holds.
    assert settled["measured"] == pytest.approx(7.2, abs=0.05)
    assert settled["amount"] > 0
    assert settled["block_number"] >= settled["condition_block"]
    assert settled["subject_text"] and settled["peril_name"] and settled["predicate"]

    empty = next(r for r in rows if r["policy_id"] == quiet.policy_id)
    assert empty["amount"] == 0


def test_the_register_does_not_say_whose_policy_it_was() -> None:
    _, chain, paid, _ = a_paid_and_an_untriggered_policy()
    row = next(r for r in chain.recent_decisions(20) if r["policy_id"] == paid.policy_id)
    assert "holder" not in row
    assert "account" not in row
    assert "holder" not in repr(row)


def test_one_row_per_policy_newest_first() -> None:
    """A policy that settled in instalments is one entry, not a run of them."""
    _, chain, _, _ = a_paid_and_an_untriggered_policy()
    rows = chain.recent_decisions(20)
    ids = [row["policy_id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert [row["block_number"] for row in rows] == sorted(
        (row["block_number"] for row in rows), reverse=True
    )


def test_the_endpoint_is_public_and_carries_the_book_figures() -> None:
    """No sign-in: the record is the chain's, not ours, so the page that shows
    it cannot be the thing deciding who may look."""
    app = create_app(trials=200, seed=5, run_chain=False, seed_book=False)
    with TestClient(app) as client:
        chain = app.state.chain
        pool = app.state.pool
        wallets = app.state.wallets

        def funded(label: str, amount: float) -> str:
            address = derive_address("clause/test/" + label)
            wallets.connect(address, fund=False)
            wallets.credit(address, amount, "test funding", kind="faucet")
            return address

        pool.deposit(funded("proof-register-lp", 20_000_000.0), 20_000_000.0)
        policy = pool.write(
            peril_key="earthquake",
            subject={"location": "IST-KADIKOY", "radius_km": 50},
            limit=100_000, term_days=365,
            holder=funded("proof-register-holder", 100_000.0),
        )
        chain.register(policy)
        start_cover(chain, policy)
        chain.attest(KADIKOY, "max_magnitude", 7.2)
        for _ in range(chain.confirm_blocks(policy) + 4):
            chain.produce_block()

        reply = client.get("/api/decided?limit=5")
        assert reply.status_code == 200
        body = reply.json()
        assert [row["policy_id"] for row in body["items"]] == [policy.policy_id]
        assert body["book"]["paid"] >= 1
        assert body["book"]["policies"] >= 1
        assert body["book"]["height"] > 0

        # And every row is one the lineage endpoint will still answer for.
        lineage = client.get("/api/lineage/" + policy.policy_id)
        assert lineage.status_code == 200


def test_the_limit_is_bounded() -> None:
    app = create_app(trials=200, seed=5, run_chain=False, seed_book=False)
    with TestClient(app) as client:
        assert client.get("/api/decided?limit=0").status_code == 422
        assert client.get("/api/decided?limit=500").status_code == 422
        assert client.get("/api/decided").status_code == 200
