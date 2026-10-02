"""A policy the chain cannot evaluate stays armed, and takes nothing with it.

A predicate reads one named figure out of one named source. If that figure is
not in the snapshot the evaluation raises rather than returning false: false is
"the index has not reached the trigger", which is an answer, and raising is
"nobody has told me", which is not. Inside the evaluation loop the two end the
same way, with the policy left armed for its deadline to close; the difference
is that a raise which is not caught does not end there at all. It leaves the
loop, and the loop is shared. Every armed policy a block wakes is evaluated in
the same pass, so one unreadable policy would take down the block and with it
the settlements of everybody whose reading did arrive, every block, until
somebody noticed.

So what these tests hold down is containment. The unreadable policy stays
armed and unpaid, its neighbour on a source that did publish settles in the
same pass, and the block closes.
"""

from __future__ import annotations

import pytest

from clause import predicate as pred
from clause.chain import Chain, ChainConfig
from clause.pricing import PricingEngine
from clause.protocol import Pool, PolicyStatus


def built(seed: int = 3):
    pool = Pool(engine=PricingEngine(trials=200, seed=seed))
    pool.deposit("lp", 20_000_000.0)
    return pool, Chain(pool, ChainConfig(seed=seed))


def quake(pool: Pool, chain: Chain, location: str):
    """A quake policy on this chain, with its waiting period behind it."""
    policy = pool.write(
        peril_key="earthquake",
        subject={"location": location, "radius_km": 50, "built": 2021},
        limit=100_000, term_days=365, holder="holder",
    )
    armed = chain.register(policy)
    while chain.world_now(policy) < policy.starts_at:
        chain.produce_block()
    return policy, armed


def unreadable(chain: Chain, policy) -> None:
    """Take the figure this policy's predicate reads out of the snapshot.

    The source is still there and still publishing; what it is publishing no
    longer includes the field this policy was written against.
    """
    chain.readings[policy.data_reference].fields.pop("max_magnitude")


def test_a_figure_that_is_not_there_is_a_refusal_not_a_no() -> None:
    pool, chain = built()
    policy, armed = quake(pool, chain, "IST-KADIKOY")
    unreadable(chain, policy)

    with pytest.raises(pred.EvaluationError):
        pred.evaluate(armed.tree, chain.snapshot())


def keeps_publishing(chain: Chain, policy, blocks: int) -> int:
    """Run the chain on with the source publishing a figure beside the one
    this policy reads, which is what wakes it to be evaluated again.

    Without this the source is never heard from, the index never names the
    policy as a candidate, and the evaluation under test is never reached:
    a policy left alone proves nothing about a policy that is looked at.
    Returns the number of evaluations the run made.
    """
    before = chain._evaluations
    for count in range(blocks):
        chain.attest(policy.data_reference, "events", count + 1)
        chain.produce_block()
    return chain._evaluations - before


def test_a_policy_it_cannot_read_stays_armed() -> None:
    pool, chain = built()
    policy, armed = quake(pool, chain, "IST-KADIKOY")
    unreadable(chain, policy)

    looked_at = keeps_publishing(chain, policy, 12)

    assert looked_at >= 12, "the policy was never evaluated, so nothing is proved"
    assert armed.account in chain.armed
    assert pool.policies[policy.policy_id].status is PolicyStatus.ACTIVE


def test_one_unreadable_policy_does_not_hold_up_the_others() -> None:
    """The reason the raise is caught per policy and not per block."""
    pool, chain = built()
    mute, mute_armed = quake(pool, chain, "IST-KADIKOY")
    heard, heard_armed = quake(pool, chain, "IZM-KONAK")
    unreadable(chain, mute)

    chain.attest(heard.data_reference, "max_magnitude", 7.4)
    fired = chain._evaluate([mute_armed, heard_armed], chain.height)

    assert fired == 1
    assert heard_armed.account not in chain.armed
    assert mute_armed.account in chain.armed


def test_a_block_still_closes_with_an_unreadable_policy_in_the_book() -> None:
    """The block is the shared thing. One policy nobody can read must not
    stop it, because stopping it stops everybody."""
    pool, chain = built()
    policy, _ = quake(pool, chain, "IST-KADIKOY")
    unreadable(chain, policy)

    height = chain.height
    looked_at = keeps_publishing(chain, policy, 5)

    assert looked_at >= 5
    assert chain.height == height + 5
