"""Identity, which is an address, and the money that moves against it.

The tests here are mostly about what the protocol refuses to know. There is no
account creation to test, no password reset, no profile. What there is to check
is that value cannot appear or vanish between the pool and an address, and that
a payout reaches its holder without the holder doing anything at all.
"""

from __future__ import annotations

import pytest

from conftest import start_cover

from clause.chain import Chain, ChainConfig
from clause.pricing import PricingEngine
from clause.protocol import (
    Pool,
    PoolError,
    PolicyStatus,
    WalletError,
    Wallets,
    derive_address,
    shorten,
)

KADIKOY = "api.seismic.example/v1/max-magnitude?lat=40.99&lon=29.03&radius_km=50"


def built(capital: float = 20_000_000.0, buyer_funds: float = 400_000.0):
    wallets = Wallets()
    pool = Pool(engine=PricingEngine(trials=1_500, seed=4), wallets=wallets)

    lp = wallets.connect(derive_address("lp"), fund=False).address
    wallets.credit(lp, capital, "seed", kind="faucet")
    pool.deposit(lp, capital)

    buyer = wallets.connect(derive_address("buyer"), fund=False).address
    wallets.credit(buyer, buyer_funds, "seed", kind="faucet")

    chain = Chain(pool, ChainConfig(seed=4))
    return wallets, pool, chain, buyer, lp


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------


def test_an_address_is_derived_not_registered() -> None:
    address = derive_address("anything")
    from clause.protocol.address import is_address
    assert is_address(address) and len(address) in (43, 44)
    # Deterministic from its seed, so a demo can be reproduced exactly.
    assert derive_address("anything") == address
    assert derive_address("something else") != address


def test_two_connections_to_one_address_are_the_same_holder() -> None:
    """Connecting is not registering, so it cannot happen twice."""
    wallets = Wallets()
    first = wallets.connect()
    second = wallets.connect(first.address)
    assert first is second
    assert len(wallets.accounts) == 1
    # And funding is not repeated by reconnecting.
    assert second.balance == wallets.demo_balance


def test_an_address_is_shown_short_enough_to_recognise() -> None:
    address = derive_address("display")
    short = shorten(address)
    assert short.startswith(address[:6])
    assert short.endswith(address[-4:])
    assert len(short) < len(address)


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def test_a_premium_leaves_the_buyer_and_arrives_in_the_pool() -> None:
    wallets, pool, _, buyer, _ = built()
    before_buyer = wallets.require(buyer).balance
    before_pool = pool.balance

    policy = pool.write(
        peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=100_000, term_days=365, holder=buyer,
    )

    assert wallets.require(buyer).balance == pytest.approx(before_buyer - policy.premium)
    assert pool.balance == pytest.approx(before_pool + policy.premium)


def test_an_address_that_cannot_pay_gets_no_cover() -> None:
    """And the refusal leaves nothing behind, which is the part worth testing."""
    wallets, pool, _, _, _ = built()
    broke = wallets.connect(derive_address("broke"), fund=False).address
    before = len(pool.policies)

    with pytest.raises(WalletError):
        pool.write(
            peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
            limit=100_000, term_days=365, holder=broke,
        )

    assert len(pool.policies) == before
    assert pool.ledger == [] or pool.ledger[-1].kind.value != "premium"
    pool.check_ledger()


def test_a_payout_reaches_the_holder_without_the_holder_doing_anything() -> None:
    wallets, pool, chain, buyer, _ = built()
    policy = pool.write(
        peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=200_000, term_days=365, holder=buyer,
    )
    chain.register(policy)
    start_cover(chain, policy)
    after_premium = wallets.require(buyer).balance

    chain.attest(KADIKOY, "max_magnitude", 7.2)
    for _ in range(chain.confirm_blocks(policy) + 3):   # the confirmation window
        chain.produce_block()

    settled = pool.policies[policy.policy_id]
    assert settled.status is PolicyStatus.PAID
    assert settled.payout > 0
    # No call was made on the holder's behalf. The balance simply moved.
    assert wallets.require(buyer).balance == pytest.approx(after_premium + settled.payout)


def test_a_refund_reaches_the_holder_when_the_source_goes_quiet() -> None:
    wallets, pool, chain, buyer, _ = built()
    policy = pool.write(
        peril_key="drought",
        subject={"station": "TR-SANLIURFA", "distance_km": 20, "hectares": 40},
        limit=55_000, term_days=140, holder=buyer,
    )
    chain.register(policy)
    start_cover(chain, policy)
    chain.silence("api.meteo.example/v1/station/TR-SANLIURFA/cumulative")
    after_premium = wallets.require(buyer).balance

    for _ in range(9_000):
        chain.produce_block()
        if pool.policies[policy.policy_id].status is not PolicyStatus.ACTIVE:
            break

    assert pool.policies[policy.policy_id].status is PolicyStatus.EXPIRED
    assert wallets.require(buyer).balance == pytest.approx(after_premium + policy.premium)


def test_value_is_conserved_between_the_pool_and_the_addresses() -> None:
    """Nothing is minted at the boundary. Every pool movement has a counterparty."""
    wallets, pool, chain, buyer, lp = built()
    for _ in range(3):
        policy = pool.write(
            peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
            limit=60_000, term_days=365, holder=buyer,
        )
        chain.register(policy)
        start_cover(chain, policy)

    chain.attest(KADIKOY, "max_magnitude", 7.2)
    for _ in range(4):
        chain.produce_block()

    funded = sum(
        movement.amount
        for account in wallets.accounts.values()
        for movement in account.movements
        if movement.kind == "faucet"
    )
    held = sum(account.balance for account in wallets.accounts.values())
    # Everything that was funded is either still at an address or in the pool.
    assert held + pool.balance == pytest.approx(funded)
    pool.check_ledger()


def test_a_wallet_records_why_each_movement_happened() -> None:
    wallets, pool, _, buyer, _ = built()
    policy = pool.write(
        peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
        limit=80_000, term_days=365, holder=buyer,
    )
    last = wallets.require(buyer).movements[-1]
    assert last.kind == "premium"
    assert last.reference == policy.policy_id
    assert last.amount == pytest.approx(-policy.premium)


# ---------------------------------------------------------------------------
# Reading a position back
# ---------------------------------------------------------------------------


def test_a_portfolio_is_assembled_from_policies_not_from_a_user_record() -> None:
    wallets, pool, chain, buyer, _ = built()
    other = wallets.connect(derive_address("other"), fund=False).address
    wallets.credit(other, 200_000, "seed", kind="faucet")

    mine = [
        pool.write(
            peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
            limit=40_000, term_days=365, holder=buyer,
        )
        for _ in range(2)
    ]
    pool.write(
        peril_key="earthquake", subject={"location": "ANK-CANKAYA", "radius_km": 25},
        limit=40_000, term_days=365, holder=other,
    )

    view = wallets.portfolio(buyer, pool.policies.values())
    assert view["policies_open"] == 2
    assert view["cover_in_force"] == pytest.approx(80_000)
    assert view["premium_paid"] == pytest.approx(sum(p.premium for p in mine))
    # The other address is not in it, and was never consulted.
    assert view["claims_received"] == 0.0


def test_an_address_that_never_connected_can_still_be_paid() -> None:
    """A payout does not require anyone to have used this interface."""
    wallets = Wallets()
    stranger = derive_address("stranger")
    assert wallets.get(stranger) is None

    wallets.credit(stranger, 1_000, "CLS-TEST", kind="payout")

    account = wallets.require(stranger)
    assert account.balance == pytest.approx(1_000)
    assert account.movements[-1].kind == "payout"


def test_a_portfolio_for_an_unknown_address_is_empty_not_an_error() -> None:
    wallets, pool, _, _, _ = built()
    view = wallets.portfolio(derive_address("nobody"), pool.policies.values())
    assert view["connected"] is False
    assert view["policies_open"] == 0
    assert view["cover_in_force"] == 0.0


def test_capital_provision_moves_against_an_address_too() -> None:
    wallets, pool, _, _, lp = built()
    before = wallets.require(lp).balance
    free = pool.free_capital()
    assert free > 0, "setup must leave something withdrawable"

    shares = free / pool.share_price / 2
    amount = pool.withdraw(lp, shares)

    assert wallets.require(lp).balance == pytest.approx(before + amount)
    pool.check_ledger()


def test_a_pool_without_wallets_still_balances() -> None:
    """The pool's own accounting does not depend on anyone watching the other side."""
    pool = Pool(engine=PricingEngine(trials=500, seed=1))
    pool.deposit("anonymous", 5_000_000)
    pool.write(
        peril_key="earthquake", subject={"location": "IZM-KONAK", "radius_km": 50},
        limit=50_000, term_days=365, holder="anonymous",
    )
    pool.check_ledger()


def test_a_demonstration_account_can_be_topped_up_and_only_there() -> None:
    from fastapi.testclient import TestClient
    from clause.api.app import FAUCET_CEILING, create_app
    from clause.api.security import Settings
    from test_api_security import Device, session_for

    for faucet in (True, False):
        app = create_app(trials=200, seed=1, run_chain=False, seed_book=False,
                         settings=Settings(faucet=faucet))
        with TestClient(app) as client:
            device = Device()
            address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
            auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
            reply = client.post("/api/wallet/faucet", headers=auth)
            if not faucet:
                assert reply.status_code == 404
                continue
            assert reply.status_code == 200 and reply.json()["added"] == 100_000
            assert client.post("/api/wallet/faucet").status_code == 401
            codes = [client.post("/api/wallet/faucet", headers=auth).status_code for _ in range(9)]
            assert 409 in codes, "the ceiling stops it"
            balance = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]
            assert balance == FAUCET_CEILING
