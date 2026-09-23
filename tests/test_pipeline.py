"""The policy pipeline: the operator's own refusals, in the path of money.

The compliance gate answers from the registry and the eligibility check from
what the buyer proved. Neither can say "not this address, whatever it proves"
or "nothing on this peril this week". These tests are about the thing that
can: that it runs at every stage that moves value, that the first rule to
deny stops it, that a moratorium stops new business and never a payout, that
a person can ask for the decision without acting and hears about their own
address only, and that the book survives a restart.
"""

from __future__ import annotations

import time

import pytest

from conftest import cover_has_started
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol import PolicyStatus
from clause.protocol.pipeline import Action, Match, PolicyError, PolicyPipeline, Rule
from clause.store import Store, decode, encode
from test_api_security import Device, buy_body, buy_terms, session_for
from test_payouts import TR_IBAN

TOKEN = "operator-token-for-tests"
OP = {"x-operator-token": TOKEN}
ADDRESS = "HddrYhoK5iZ9F7qdz3HgEwrY5Xk8Q5vjWJqYzY2tpCJV"


# ---------------------------------------------------------------------------
# The rules on their own
# ---------------------------------------------------------------------------


def test_the_first_rule_to_deny_stops_it_and_says_which() -> None:
    p = PolicyPipeline()
    p.deny(match=Match.COUNTRY, value="kp", reason="embargo", by="reviewer")
    p.pause(peril="*", reason="everything paused", by="reviewer")
    decision = p.check(Action(stage="purchase", peril="earthquake", countries=("TR", "KP")))
    assert not decision.allowed and decision.rule == Rule.DENYLIST.value
    assert decision.evaluated == ("denylist",)          # the moratorium never ran
    decision = p.check(Action(stage="purchase", peril="earthquake", countries=("TR",)))
    assert not decision.allowed and decision.rule == Rule.MORATORIUM.value
    assert decision.evaluated == ("denylist", "moratorium")
    assert p.check(Action(stage="settlement", countries=("TR",))).allowed


def test_a_moratorium_stops_new_business_and_never_a_payout() -> None:
    p = PolicyPipeline()
    p.pause(peril="earthquake", reason="M7.1 on the North Anatolian fault this morning", by="r",
            latitude=40.8, longitude=29.9, radius_km=150)
    inside = dict(peril="earthquake", countries=("TR",), latitude=41.0, longitude=29.0)
    assert not p.check(Action(stage="purchase", **inside)).allowed
    assert p.check(Action(stage="settlement", **inside)).allowed
    # Izmir is on another fault system, and drought is another peril.
    assert p.check(Action(stage="purchase", peril="earthquake", countries=("TR",), latitude=38.4, longitude=27.1)).allowed
    assert p.check(Action(stage="purchase", peril="drought", countries=("TR",), latitude=41.0, longitude=29.0)).allowed
    # A circle cannot refuse a policy that has no place.
    assert p.check(Action(stage="purchase", peril="earthquake", countries=("TR",))).allowed


def test_entries_are_normalised_so_a_match_is_a_comparison() -> None:
    p = PolicyPipeline()
    p.deny(match="wallet", value="0xAbC0000000000000000000000000000000000001", reason="reported", by="r")
    p.deny(match="destination", value="tr33 0006 1005 1978 6457 8413 26", reason="court order", by="r")
    assert not p.check(Action(stage="link", wallet="0xabc0000000000000000000000000000000000001")).allowed
    assert not p.check(Action(stage="cashout", destination=TR_IBAN)).allowed
    assert p.check(Action(stage="cashout", destination="TR330006100519786457841399")).allowed
    with pytest.raises(PolicyError, match="not an address"):
        p.deny(match="address", value="nobody", reason="x y z", by="r")
    with pytest.raises(PolicyError, match="two letter"):
        p.deny(match="country", value="Turkey", reason="x y z", by="r")
    with pytest.raises(PolicyError, match="say why"):
        p.deny(match="country", value="KP", reason="", by="r")
    with pytest.raises(PolicyError, match="already refused"):
        p.deny(match="wallet", value="0xABC0000000000000000000000000000000000001", reason="twice", by="r")
    with pytest.raises(PolicyError, match="unknown stage"):
        Action(stage="borrow")


def test_lifting_keeps_the_entry_and_who_lifted_it() -> None:
    p = PolicyPipeline()
    entry = p.deny(match="address", value=ADDRESS, reason="sanctions notice", by="reviewer", now=1000.0)
    assert not p.check(Action(stage="funding", address=ADDRESS), now=1001.0).allowed
    lifted = p.lift(entry.entry_id, by="another", note="delisted", now=2000.0)
    assert lifted.lifted_by == "another" and lifted.lift_note == "delisted" and not lifted.live(now=2001.0)
    assert p.check(Action(stage="funding", address=ADDRESS), now=2001.0).allowed
    with pytest.raises(PolicyError, match="already lifted"):
        p.lift(entry.entry_id, by="x")
    timed = p.deny(match="country", value="XX", reason="for a week", by="r", until=5000.0, now=1000.0)
    assert not p.check(Action(stage="purchase", countries=("XX",)), now=4999.0).allowed
    assert p.check(Action(stage="purchase", countries=("XX",)), now=5000.0).allowed
    assert [e.entry_id for e in p.live(now=6000.0)] == []
    assert timed.entry_id in p.entries


def test_what_is_public_and_what_is_not() -> None:
    p = PolicyPipeline()
    p.deny(match="address", value=ADDRESS, reason="sanctions notice", by="reviewer")
    p.pause(peril="drought", country="TR", reason="the season is already known", by="reviewer")
    public = p.describe()
    text = str(public)
    assert ADDRESS not in text and "sanctions notice" not in text
    assert public["moratoria"][0]["peril"] == "drought" and public["moratoria"][0]["country"] == "TR"
    assert [r["live"] for r in public["rules"]] == [1, 1]
    book = p.book()
    assert any(e.get("value") == ADDRESS and e["added_by"] == "reviewer" for e in book["entries"])
    for entry in p.entries.values():
        assert decode(encode(entry)) == entry


# ---------------------------------------------------------------------------
# In the path of money
# ---------------------------------------------------------------------------


def app_with(store_path=None):
    return create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                      settings=Settings(faucet=True, operator_token=TOKEN),
                      store_path=store_path)


def register(client):
    device = Device()
    address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
    return device, address


def buy(client, device, address, **overrides):
    terms = buy_terms(**{k: v for k, v in overrides.items() if k in ("peril", "subject", "limit")})
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms}).json()
    return client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]), client=client, **overrides))


def test_a_refused_address_cannot_buy_and_the_refusal_names_the_rule() -> None:
    with TestClient(app_with()) as client:
        device, address = register(client)
        made = client.post("/api/operator/policy/deny", headers=OP, json={
            "match": "address", "value": address, "reason": "named in a sanctions notice"})
        assert made.status_code == 200, made.text
        reply = buy(client, device, address)
        assert reply.status_code == 451, reply.text
        detail = reply.json()["detail"]
        assert detail["policy"]["denied_by"]["rule"] == "denylist"
        assert "refused by the operator's policy" in detail["reasons"][0]
        # Applying is the same path.
        assert client.post("/api/operator/policy/" + made.json()["entry"]["entry_id"] + "/lift",
                           headers=OP, json={"note": "delisted"}).status_code == 200
        assert buy(client, device, address).status_code == 200


def test_a_moratorium_refuses_new_cover_on_the_fault_and_nothing_else() -> None:
    with TestClient(app_with()) as client:
        device, address = register(client)
        paused = client.post("/api/operator/policy/pause", headers=OP, json={
            "peril": "earthquake", "reason": "M7.1 this morning; the sequence has not settled",
            "latitude": 40.99, "longitude": 29.03, "radius_km": 120, "until": time.time() + 7 * 86400})
        assert paused.status_code == 200, paused.text
        reply = buy(client, device, address)
        assert reply.status_code == 451
        assert "no new earthquake cover" in reply.json()["detail"]["reasons"][0]
        # Anyone can read that nothing is being written here this week.
        public = client.get("/api/policy").json()
        assert public["moratoria"][0]["place"]["radius_km"] == 120
        # Ankara is outside the circle.
        reply = buy(client, device, address, subject={"location": "ANK-CANKAYA", "radius_km": 25},
                    interest={"what": "a flat in Ankara", "country": "TR", "inside_trigger_area": True,
                              "value_at_risk": 90_000, "size": {"kind": "home", "building": "flat", "area_m2": 150}})
        assert reply.status_code == 200, reply.text
        assert client.post("/api/operator/policy/pause", headers=OP, json={
            "peril": "hail", "reason": "no such peril"}).status_code == 422


def test_asking_for_a_decision_without_acting() -> None:
    with TestClient(app_with()) as client:
        device, address = register(client)
        other_device, other = register(client)
        client.post("/api/operator/policy/deny", headers=OP, json={
            "match": "address", "value": other, "reason": "named in a sanctions notice"})
        # Anonymous: nobody hears one bit about anyone.
        assert client.post("/api/policy/check", json={"stage": "purchase", "address": other}).status_code == 401
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        mine = client.post("/api/policy/check", headers=auth, json={"stage": "purchase", "peril": "earthquake"}).json()
        assert mine["allowed"] and mine["action"]["address"] == address and mine["evaluated"] == ["denylist", "moratorium"]
        assert client.post("/api/policy/check", headers=auth,
                           json={"stage": "purchase", "address": other}).status_code == 403
        # The operator may ask about anyone, and hears the refusal.
        theirs = client.post("/api/policy/check", headers=OP, json={"stage": "purchase", "address": other}).json()
        assert theirs["decision"] == "deny" and theirs["denied_by"]["rule"] == "denylist"
        assert client.post("/api/policy/check", headers=OP, json={"stage": "borrow"}).status_code == 422
        # Every decision, allowed or refused, is on the operator's page.
        book = client.get("/api/operator/policy", headers=OP).json()
        assert book["refused"] >= 1 and book["live"] == 1
        assert any(d["decision"] == "allow" for d in book["decisions"])


def test_an_address_refused_mid_term_is_not_paid_and_gets_the_premium_back() -> None:
    app = app_with()
    with TestClient(app) as client:
        device, address = register(client)
        bought = buy(client, device, address)
        assert bought.status_code == 200, bought.text
        policy_id = bought.json()["policy"]["policy_id"]
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        after_premium = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]
        client.post("/api/operator/policy/deny", headers=OP, json={
            "match": "address", "value": address, "reason": "named in a sanctions notice"})
        chain, pool = app.state.chain, app.state.pool
        policy = pool.policies[policy_id]
        cover_has_started(policy)
        chain.attest(policy.data_reference, "max_magnitude", 7.4)
        for _ in range(chain.confirm_blocks(policy) + 3):
            chain.produce_block()
        policy = pool.policies[policy_id]
        assert policy.status is PolicyStatus.EXPIRED, policy.status
        assert "operator's policy" in policy.settlement_note
        balance = client.get("/api/wallet", headers=auth).json()["wallet"]["balance"]
        assert after_premium < balance < after_premium + policy.limit


def test_money_does_not_leave_for_a_refused_destination() -> None:
    with TestClient(app_with()) as client:
        device, address = register(client)
        terms = {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"}
        challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "payout", "terms": terms}).json()
        chosen = client.post("/api/payouts/preference", json={
            "account": address, "nonce": challenge["nonce"], "signature": device.sign(challenge["message"]), **terms})
        assert chosen.status_code == 200, chosen.text
        client.post("/api/operator/policy/deny", headers=OP, json={
            "match": "destination", "value": TR_IBAN, "reason": "account named in a court order"})
        challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "cashout", "terms": {"amount": 500.0}}).json()
        reply = client.post("/api/payouts/cashout", json={
            "account": address, "amount": 500, "nonce": challenge["nonce"], "signature": device.sign(challenge["message"])})
        assert reply.status_code == 451, reply.text
        assert reply.json()["detail"]["policy"]["denied_by"]["rule"] == "denylist"
        # Choosing that destination afresh is refused too, and nothing is kept.
        another_device, another = register(client)
        challenge = client.post("/api/auth/challenge", json={"address": another, "purpose": "payout", "terms": terms}).json()
        refused = client.post("/api/payouts/preference", json={
            "account": another, "nonce": challenge["nonce"], "signature": another_device.sign(challenge["message"]), **terms})
        assert refused.status_code == 451
        auth = {"authorization": f"Bearer {session_for(client, another_device, another)}"}
        assert client.get("/api/payouts", headers=auth).json()["preference"]["method"] == "wallet"


def test_a_payout_to_a_refused_destination_stays_at_the_address() -> None:
    from test_payouts import book, quake

    wallets, pool, payouts = book()
    pipeline = PolicyPipeline()
    payouts.gate = lambda account, destination, amount: pipeline.refusal(
        Action(stage="cashout", address=account, destination=destination, amount=amount))
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"})
    pipeline.deny(match="destination", value=TR_IBAN, reason="account named in a court order", by="r")
    policy = quake(pool)
    before = wallets.require("holder").balance
    pool.pay(policy, 7.0)
    assert payouts.open_orders() == []
    assert wallets.require("holder").balance > before
    with pytest.raises(Exception, match="refused by the operator's policy"):
        payouts.cashout("holder", 500)


def test_a_refused_wallet_cannot_be_linked_or_announced() -> None:
    from test_links import MetaMask

    with TestClient(app_with()) as client:
        device, address = register(client)
        wallet = MetaMask()
        client.post("/api/operator/policy/deny", headers=OP, json={
            "match": "wallet", "value": wallet.address.upper().replace("0X", "0x"), "reason": "reported by a partner"})
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        start = client.post("/api/profile/links/start", headers=auth, json={"kind": "evm", "address": wallet.address}).json()
        challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "link-wallet",
                                                             "terms": {"kind": "evm", "address": wallet.address}}).json()
        made = client.post("/api/profile/links", json={
            "account": address, "kind": "evm", "address": wallet.address,
            "wallet_nonce": start["nonce"], "wallet_signature": wallet.sign(start["message"]),
            "nonce": challenge["nonce"], "signature": device.sign(challenge["message"])})
        assert made.status_code == 451, made.text
        asked = client.post("/api/funding", headers=auth, json={"method": "evm", "amount": 100, "sender": wallet.address})
        assert asked.status_code == 451, asked.text


def test_the_book_survives_a_restart(tmp_path) -> None:
    path = tmp_path / "clause.sqlite"
    with TestClient(app_with(store_path=path)) as client:
        entry = client.post("/api/operator/policy/deny", headers=OP, json={
            "match": "country", "value": "KP", "reason": "embargo"}).json()["entry"]
        client.post("/api/operator/policy/pause", headers=OP, json={"peril": "drought", "reason": "season known"})
    assert len(Store(path).docs("rule")) == 2
    with TestClient(app_with(store_path=path)) as client:
        book = client.get("/api/operator/policy", headers=OP).json()
        assert {e["entry_id"] for e in book["entries"]} >= {entry["entry_id"]}
        assert book["live"] == 2
        assert client.post("/api/policy/check", headers=OP, json={"stage": "purchase", "country": "kp"}).json()["decision"] == "deny"
