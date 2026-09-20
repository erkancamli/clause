"""The book survives a restart.

A policy bought, a company approved with its review trail, a Privy account
joined on two devices, a settlement the chain performed: all of it is still
there after the process stops and a new one starts on the same file.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.store import Store, decode, encode
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_privy import device, link, sign, token, verifier
from conftest import FLIGHT_DATE


def app_on(path, token=False, **kw):
    from test_operator import TOKEN
    settings = Settings(faucet=True, operator_token=TOKEN)
    return create_app(trials=300, run_chain=False, seed_book=True, settings=settings,
                      privy_verifier=verifier(), store_path=path, **kw)


def test_objects_round_trip_through_the_encoding() -> None:
    from clause.protocol import specimen_registry

    registry = specimen_registry()
    for carrier in registry.carriers.values():
        again = decode(encode(carrier))
        assert again == carrier


def test_the_whole_book_comes_back_after_a_restart(tmp_path) -> None:
    path = tmp_path / "clause.sqlite"
    phone, phone_pub = device()
    laptop, laptop_pub = device()

    with TestClient(app_on(path)) as client:
        first = link(client, phone, phone_pub, token()).json()
        link(client, laptop, laptop_pub, token())
        account = first["address"]
        book = client.get("/api/policies", params={"limit": 200}).json()
        pool_before = client.get("/api/pool").json()

    assert Store(path).count("ledger") > 0

    with TestClient(app_on(path)) as client:
        again = client.get("/api/policies", params={"limit": 200}).json()
        assert again["count"] == book["count"]
        assert {p["policy_id"] for p in again["items"]} == {p["policy_id"] for p in book["items"]}
        pool_after = client.get("/api/pool").json()
        assert round(pool_after["pool"]["balance"] if "pool" in pool_after else pool_after["balance"], 2) == \
               round(pool_before["pool"]["balance"] if "pool" in pool_before else pool_before["balance"], 2)
        # The laptop can still sign for the account made on the phone, with no
        # new Privy sign in: the join was kept.
        challenge = client.post("/api/auth/challenge", json={"address": account, "purpose": "sign-in"}).json()
        reply = client.post("/api/auth/verify", json={"address": account, "nonce": challenge["nonce"],
                                                       "signature": sign(laptop, challenge["message"])})
        assert reply.status_code == 200
        # And the Privy account still points at the same address.
        other, other_pub = device()
        assert link(client, other, other_pub, token()).json()["address"] == account


def test_a_review_decision_survives_a_restart(tmp_path) -> None:
    from test_operator import auth, registration, sign_in

    path = tmp_path / "clause.sqlite"
    with TestClient(app_on(path, token=True)) as client:
        reply = client.post("/api/carriers", json=registration())
        assert reply.status_code == 200, reply.text
        carrier_id = reply.json()["carrier"]["carrier_id"]
        act = client.post(f"/api/carriers/{carrier_id}/activate", json={"note": "checked the register"},
                          headers=auth(sign_in(client, "Erkan")))
        assert act.status_code == 200, act.text

    with TestClient(app_on(path, token=True)) as client:
        rows = client.get("/api/operator/carriers", headers=auth(sign_in(client, "Erkan"))).json()
        rows = rows["companies"]
        found = [c for c in rows if c["carrier_id"] == carrier_id]
        assert found and found[0]["status"] == "active"
        assert found[0]["reviews"][0]["reviewer"] == "Erkan"
        assert found[0]["reviews"][0]["note"] == "checked the register"


def test_settlements_and_the_clock_are_kept(tmp_path) -> None:
    """The chain's history is appended to, never rewritten, and the clock and
    height carry on from where they stopped rather than starting again."""
    path = tmp_path / "clause.sqlite"
    app = app_on(path)
    with TestClient(app) as client:
        before = client.get("/api/health").json()["chain"]
    store = Store(path)
    height = store.meta("chain")["height"]
    assert height == before["height"]
    with TestClient(app_on(path)) as client:
        after = client.get("/api/health").json()["chain"]
    assert after["height"] >= height
    assert after["settlements"] == before["settlements"]


def test_a_stored_file_cannot_build_arbitrary_classes() -> None:
    import pytest

    with pytest.raises(ValueError):
        decode({"__t": "os:system"})
    with pytest.raises(ValueError):
        decode({"__t": "subprocess:Popen"})


def test_cover_a_person_bought_that_the_demo_clock_closed_comes_back_in_force() -> None:
    from clause.protocol.policy import PolicyStatus
    from clause.protocol.pool import Pool
    from clause.store import LAPSE_NOTE, reinstate_lapsed_by_the_demo_clock

    from clause.pricing.engine import PricingEngine
    pool = Pool(engine=PricingEngine(trials=400, seed=5))
    pool.deposit("lp", 5_000_000)
    subject = {"route": "TK-IST-LHR", "flight_number": "TK1", "departure_date": FLIGHT_DATE}
    bought = pool.write(peril_key="flight_delay", subject=subject, limit=1_500, term_days=2, holder="h1")
    bought.metadata["interest"] = {"what": "my flight", "country": "TR"}
    synthetic = pool.write(peril_key="flight_delay", subject=subject, limit=1_500, term_days=2, holder="h2")
    for p in (bought, synthetic):
        pool.lapse(p)
    assert bought.settlement_note == LAPSE_NOTE
    # Only the one a person bought, and only while its term still runs.
    assert reinstate_lapsed_by_the_demo_clock(pool) == 1
    assert bought.status is PolicyStatus.ACTIVE and bought.metadata["reinstated"]["lapsed_at"]
    assert synthetic.status is PolicyStatus.LAPSED
    assert reinstate_lapsed_by_the_demo_clock(pool) == 0
    pool.lapse(bought)
    assert reinstate_lapsed_by_the_demo_clock(pool, now=bought.ends_at + 1) == 0


def test_old_0x_addresses_are_rewritten_in_rialo_form_everywhere() -> None:
    from clause.protocol.address import is_address
    from clause.protocol.pool import Pool, Provider, provider_key
    from clause.protocol.wallet import Wallets
    from clause.pricing.engine import PricingEngine
    from clause.store import legacy_to_rialo, migrate_legacy_addresses

    old = "0x" + "ab" * 20
    wallets = Wallets(demo_balance=0.0)
    wallets.connect(old, fund=False)
    wallets.credit(old, 10_000, "seed", kind="faucet")
    pool = Pool(engine=PricingEngine(trials=400, seed=5), wallets=wallets)
    wallets.connect("lp", fund=False); wallets.credit("lp", 4_000_000, "seed", kind="faucet")
    pool.deposit("lp", 4_000_000)
    pool.deposit(old, 100, tranche="mezzanine")
    policy = pool.write(peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50.0},
                        limit=20_000, term_days=365, holder=old)
    policy.metadata["paid_by"] = old

    class Auth:  # only the two dicts the migration touches
        keys = {old: "key-bytes"}
        signers = {old: ["k"]}

    class Accounts:
        _by_user = {"did:privy:1": old}

    class Registry:
        carriers = {}

    class Chain:
        settlements = []

    # An Ethereum address somebody chose as a payout destination is the same
    # shape and is not an account: it must survive untouched.
    metamask = "0x" + "cd" * 20
    payouts = type("P", (), {"preferences": {old: {"account": old, "method": "evm", "rialo_address": metamask}},
                             "orders": {}})()
    n = migrate_legacy_addresses(pool=pool, wallets=wallets, chain=Chain(), registry=Registry(), auth=Auth(),
                                 accounts=Accounts(), payouts=payouts)
    assert n == 1
    assert payouts.preferences[legacy_to_rialo(old)]["rialo_address"] == metamask
    new = legacy_to_rialo(old)
    assert is_address(new) and not new.startswith("0x")
    assert policy.holder == new and policy.metadata["paid_by"] == new
    assert new in wallets.accounts and old not in wallets.accounts and wallets.accounts[new].address == new
    assert provider_key(new, "mezzanine") in pool.providers and pool.providers[provider_key(new, "mezzanine")].account == new
    assert all(old not in e.account for e in pool.ledger)
    assert Auth.keys == {new: "key-bytes"} and Accounts._by_user["did:privy:1"] == new
    assert payouts.preferences[new]["account"] == new
    # Running it again changes nothing.
    assert migrate_legacy_addresses(pool=pool, wallets=wallets, chain=Chain(), registry=Registry(), auth=Auth(),
                                    accounts=Accounts(), payouts=payouts) == 0


def test_a_key_registered_while_the_book_is_being_saved_does_not_lose_the_save(tmp_path, monkeypatch) -> None:
    """Registering a key holds no lock, and a dict that grows while it is
    walked raises: every save between one key and the next was lost that
    way. The books are copied before they are walked, so a key that arrives
    in the middle of a save is simply in the next one."""
    from clause import store as store_mod
    from clause.store import checkpoint
    from test_api_security import Device

    with TestClient(app_on(tmp_path / "clause.sqlite")) as client:
        app = client.app
        auth = app.state.auth
        first = auth.register(Device().public)
        arrived = []
        original = store_mod._text

        def text_and_a_new_key(item):
            # The first item walked: a device registers while the save runs.
            if not arrived:
                arrived.append(auth.register(Device().public))
            return original(item)

        monkeypatch.setattr(store_mod, "_text", text_and_a_new_key)
        target = Store(tmp_path / "again.sqlite")
        checkpoint(target, pool=app.state.pool, wallets=app.state.wallets, chain=app.state.chain,
                   registry=app.state.rules.registry, auth=auth, accounts=app.state.accounts,
                   pipeline=app.state.pipeline)
        assert arrived and first in target.docs("key")
        monkeypatch.setattr(store_mod, "_text", original)
        checkpoint(target, pool=app.state.pool, wallets=app.state.wallets, chain=app.state.chain,
                   registry=app.state.rules.registry, auth=auth, accounts=app.state.accounts,
                   pipeline=app.state.pipeline)
        assert arrived[0] in target.docs("key")
