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
        # Two pots, not one. The ones that paid are a few in a hundred and they
        # are the whole of what the proof page is for; sharing a pot with the
        # quiet majority flushed them at the same rate, so the page ended up
        # counting thousands of payments it could not show a single one of.
        paid = lambda x: str(getattr(x.status, "value", x.status)) == "paid"
        payments = sorted([p for p in settled if paid(p)], key=lambda p: (p.ends_at or 0.0))
        quiet = sorted([p for p in settled if not paid(p)], key=lambda p: (p.ends_at or 0.0))
        newest = {p.policy_id for p in quiet[-4:]} | {p.policy_id for p in payments}
        forgotten = app.state.forget_demo_book()

        assert forgotten == max(0, len(quiet) - 4) > 0, "all but the four most recent quiet ones"
        assert all(p.policy_id in pool.policies for p in payments), (
            "a policy that paid is the proof, and is kept while there is room")
        assert bought.policy_id in pool.policies, "a policy a person bought is never forgotten"
        assert open_demo.policy_id in pool.policies, "an open policy is never forgotten"
        gone = kept_ids - set(pool.policies)
        assert len(gone) == forgotten and all(s.policy_id not in gone for s in chain.settlements)
        assert newest & gone == set(), "the most recent, and every payment, are kept"
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


def test_a_key_that_cannot_be_read_does_not_make_its_owner_nobody() -> None:
    """The background job deletes settled policies nobody can reach.

    "Nobody can reach it" was read off the key store, so a key this build
    could not load took its owner out of the set of people who exist, and
    their settled policies were deleted inside thirty seconds, permanently.
    Being unable to read somebody's key is a reason to stop, not a licence:
    the address is what makes a policy theirs and the key is only what lets
    them act on it.
    """
    from clause.chain.world import Chain
    from clause.pricing.engine import PricingEngine
    from clause.api.privy import Accounts
    from clause.protocol.auth import Authenticator
    from clause.protocol.carrier import Registry
    from clause.protocol.pool import Pool
    from clause.protocol.wallet import Wallets
    from clause.store import Store, restore

    auth = Authenticator()
    pool = Pool(engine=PricingEngine(trials=50, seed=1))
    store = Store(":memory:")
    import json

    store.write(meta={}, logs={},
                docs={"key": {"addr-unreadable": json.dumps("not a key anybody can parse")}})

    restore(store, pool=pool, wallets=Wallets(), chain=Chain(pool),
            registry=Registry(), auth=auth, accounts=Accounts())

    assert "addr-unreadable" not in auth.keys, "it genuinely could not be read"
    assert "addr-unreadable" in auth.unreadable, "but it is still somebody's"


# ---------------------------------------------------------------------------
# Who arrives, and what is kept
# ---------------------------------------------------------------------------


def test_nobody_arrives_who_was_not_sent_by_a_person() -> None:
    """A policy every eight seconds is eleven thousand a day. That was worth
    having when the book was empty and stops being worth having the moment
    real policies are in it: the invented ones crowd the register, they are
    what the retention then has to forget, and every figure on the proof page
    becomes mostly about them."""
    import os
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "clause" / "api" / "app.py").read_text(encoding="utf-8")
    line = [l for l in source.splitlines() if "CLAUSE_DEMO_ARRIVALS" in l and "environ" in l]
    assert line, "the trickle has no switch"
    assert '"0"' in line[0], f"invented buyers are on by default: {line[0].strip()}"
    # And the task is only created when the switch says a positive number.
    assert "if run_chain and arrival_gap > 0 else None" in source


def test_the_policies_that_paid_are_kept_when_the_quiet_ones_are_forgotten() -> None:
    """The count outlives the record, and only the record can be read back.

    Sharing one pot meant payments were flushed at the same rate as everything
    else, and since they are a few in a hundred the register ran out of them
    long before it ran out of anything: the proof page said thousands had been
    paid and could not show one. Measured on the live protocol, which had
    2,974 payments counted and none that could be opened.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "clause" / "api" / "app.py").read_text(encoding="utf-8")
    assert "demo_keep_paid" in source, "payments have no pot of their own"
    where = source.index("def forget_demo_book")
    body = source[where:where + 2400]
    assert "payments" in body and "quiet" in body, "the two are not separated"
    assert "len(quiet) - demo_keep" in body
    assert "len(payments) - demo_keep_paid" in body
