"""The demonstration's own book, kept to a size.

A simulated chain writes policies by the thousand and they used to be kept
for ever: every checkpoint encoded them, every capital reading walked past
them. Settled ones past a window are forgotten, and two things must hold.
Nothing a person bought may be touched. And every figure the chain
publishes about itself must be the same afterwards, because the history
happened whether or not its record is still carried.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.chain.world import Settlement
from clause.protocol.policy import PolicyStatus


def _settle(chain, policy, kind: str, block: int) -> None:
    chain.settlements.append(Settlement(
        signature="0xsig", policy_id=policy.policy_id, block_number=block,
        condition_block=block - 3, at=1.0, kind=kind,
        index_value=6.0 if kind == "paid" else None,
        amount=policy.limit if kind == "paid" else 0.0, summary=kind))


def test_settled_demonstration_policies_are_forgotten_and_the_figures_do_not_move(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUSE_DEMO_KEEP", "4")
    app = create_app(trials=200, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, specimens=True),
                     store_path=tmp_path / "book.sqlite")
    with TestClient(app) as client:
        pool, chain = app.state.pool, app.state.chain
        demo = [p for p in pool.policies.values() if (p.metadata or {}).get("synthetic")]
        assert len(demo) >= 8, "the seeded demonstration book is what this test trims"
        # Ten of the demonstration's own, settled; every one with its settlement.
        for i, policy in enumerate(demo[:10]):
            policy.status = PolicyStatus.PAID if i % 5 == 0 else PolicyStatus.LAPSED
            policy.ends_at = 1000.0 + i
            _settle(chain, policy, "paid" if i % 5 == 0 else "lapsed", 100 + i)
        # One a person bought, settled on the same day, and one still running.
        bought = demo[10]
        bought.metadata["synthetic"] = False
        bought.status = PolicyStatus.LAPSED
        bought.ends_at = 1000.0
        _settle(chain, bought, "lapsed", 90)
        open_demo = demo[11]
        open_demo.status = PolicyStatus.ACTIVE

        before = client.get("/api/health").json()["chain"]
        kept_ids = set(pool.policies)
        settled = [p for p in pool.policies.values()
                   if not p.is_open and app.state.demo_policy(p)]
        newest = {p.policy_id for p in sorted(settled, key=lambda p: (p.ends_at or 0.0))[-4:]}
        forgotten = app.state.forget_demo_book()

        assert forgotten == len(settled) - 4 > 0, "all but the four most recent"
        assert bought.policy_id in pool.policies, "a policy a person bought is never forgotten"
        assert open_demo.policy_id in pool.policies, "an open policy is never forgotten"
        gone = kept_ids - set(pool.policies)
        assert len(gone) == forgotten and all(s.policy_id not in gone for s in chain.settlements)
        assert newest & gone == set(), "the most recent are the ones kept"
        assert {p.policy_id for p in settled} - gone == newest

        after = client.get("/api/health").json()["chain"]
        for figure in ("settlements", "paid", "lapsed", "expired", "mean_latency_blocks"):
            assert after[figure] == before[figure], figure
        # Asked again, with nothing left to do, it does nothing.
        assert app.state.forget_demo_book() == 0


def test_a_trimmed_book_is_read_back_as_it_was_left(tmp_path, monkeypatch) -> None:
    """The settlement log is written by appending, so a trimmed one has to be
    written again rather than leaving the file longer than the book."""
    monkeypatch.setenv("CLAUSE_DEMO_KEEP", "4")
    path = tmp_path / "book.sqlite"
    app = create_app(trials=200, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, specimens=True), store_path=path)
    with TestClient(app) as client:
        pool, chain = app.state.pool, app.state.chain
        demo = [p for p in pool.policies.values() if (p.metadata or {}).get("synthetic")]
        for i, policy in enumerate(demo[:10]):
            policy.status = PolicyStatus.LAPSED
            policy.ends_at = 1000.0 + i
            _settle(chain, policy, "lapsed", 100 + i)
        app.state.forget_demo_book()
        kept = len(chain.settlements)
        figures = client.get("/api/health").json()["chain"]
        # A later settlement still lands, after the trim.
        _settle(chain, demo[11], "paid", 500)

    again = create_app(trials=200, seed=11, run_chain=False, seed_book=False,
                       settings=Settings(faucet=True, specimens=True), store_path=path)
    with TestClient(again) as client:
        read = client.get("/api/health").json()["chain"]
        assert len(again.state.chain.settlements) == kept + 1
        assert read["settlements"] == figures["settlements"] + 1
        assert read["lapsed"] == figures["lapsed"] and read["paid"] == figures["paid"] + 1


def test_only_what_nobody_can_reach_is_forgotten(tmp_path, monkeypatch) -> None:
    """A book written before the addresses changed shape holds demonstration
    policies with neither the marker nor a recognisable address. What marks
    them is that nobody can act as their holder. Everything somebody can
    still reach, or that carries the contract its holder accepted, stays."""
    from test_commerce import register

    monkeypatch.setenv("CLAUSE_DEMO_KEEP", "1")
    app = create_app(trials=200, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, specimens=True),
                     store_path=tmp_path / "book.sqlite")
    with TestClient(app) as client:
        pool = app.state.pool
        demo = [p for p in pool.policies.values() if (p.metadata or {}).get("synthetic")]
        _device, address = register(client)

        # Three settled policies with nothing of the demonstration on them:
        # one nobody can reach, one held by a registered device, one that
        # carries its contract.
        stray, newer, held, papered = demo[0], demo[1], demo[2], demo[3]
        for i, policy in enumerate((stray, newer, held, papered)):
            policy.status = PolicyStatus.LAPSED
            policy.ends_at = 10.0 + i          # the stray is the oldest, so not the one kept
            policy.metadata.pop("synthetic", None)
            policy.holder = "CLSnobodyHoldsThisAddressAtAll1111111111111"
        held.holder = address
        papered.metadata["contract_hash"] = "0xabc"

        assert app.state.demo_policy(stray) is True
        assert app.state.demo_policy(held) is False
        assert app.state.demo_policy(papered) is False

        assert app.state.forget_demo_book() == 1, "two nobody can reach, the newer one kept"
        assert stray.policy_id not in pool.policies, "nobody could ever have reached it"
        assert newer.policy_id in pool.policies, "the most recent is the one kept"
        assert held.policy_id in pool.policies, "a device is registered for its holder"
        assert papered.policy_id in pool.policies, "it carries the contract its holder accepted"
