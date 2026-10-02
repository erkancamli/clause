"""A listener that fails every time looked exactly like one that works.

The chain calls its listeners when a token moves and when a policy settles,
and catches whatever they throw so that one bad listener cannot stop a
settlement. That is right. What was missing is that nothing downstream
noticed: the anchor's token listener is what writes a policy to the public
chain, and a line in a log file nobody is reading is not the same as a
figure on the operator's page.

Counted now, with the last one named, beside the other chain figures.

And the other half of the same silence: a policy whose predicate can never
be evaluated, because the reading it needs is not on the chain, is skipped
on every block and stays armed until its deadline. That is the intended
behaviour and nothing asked for it, so the branch could have been deleted
without a test failing.
"""

from __future__ import annotations

import pytest

from clause.chain.world import Chain, ChainConfig
from clause.pricing import PricingEngine
from clause.protocol.pool import Pool


def chain() -> Chain:
    pool = Pool(engine=PricingEngine(trials=200, seed=3))
    pool.deposit("lp", 1_000_000.0)
    return Chain(pool, ChainConfig(seed=3))


def test_a_token_listener_that_throws_is_counted(monkeypatch) -> None:
    c = chain()
    before = c.stats()["listener_failures"]

    def angry(*_args, **_kw):
        raise RuntimeError("the anchor is not reachable")

    c.token_listeners.append(angry)
    c._token_event("minted", _a_policy())
    said = c.stats()
    assert said["listener_failures"] == before + 1
    assert "token listener failed" in said["last_listener_failure"]


def test_a_settlement_listener_that_throws_is_counted() -> None:
    from clause.chain.world import Settlement

    c = chain()

    def angry(_settlement):
        raise RuntimeError("no")

    c.listeners.append(angry)
    c._settled(Settlement(signature="sig", policy_id="CLS-X", block_number=2,
                          condition_block=1, at=0.0, kind="lapsed",
                          index_value=None, amount=0.0, summary="the term ended"))
    assert c.stats()["listener_failures"] == 1
    assert "settlement listener failed" in c.stats()["last_listener_failure"]


def test_a_listener_that_works_is_not_counted() -> None:
    c = chain()
    seen = []
    c.token_listeners.append(lambda event, policy: seen.append(event))
    c._token_event("minted", _a_policy())
    assert seen == ["minted"]
    assert c.stats()["listener_failures"] == 0
    assert c.stats()["last_listener_failure"] == ""


def test_one_bad_listener_does_not_stop_the_others() -> None:
    """Which is why they are caught in the first place."""
    c = chain()
    seen = []
    c.token_listeners.append(lambda *_: (_ for _ in ()).throw(RuntimeError("no")))
    c.token_listeners.append(lambda event, policy: seen.append(event))
    c._token_event("burned", _a_policy())
    assert seen == ["burned"]
    assert c.stats()["listener_failures"] == 1


def _a_policy():
    from types import SimpleNamespace
    return SimpleNamespace(policy_id="CLS-X", holder="a", metadata={}, limit=1000.0,
                           peril_key="earthquake")
