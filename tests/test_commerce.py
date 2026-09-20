"""Partners selling cover, Rider buying under a mandate, payouts to a bank.

All three add a way for value to move, so each is tested against the real
application for the thing that would go wrong: a partner writing cover a
person could not buy, a mandate stretched past its terms, a payout sent
somewhere its owner never signed for.
"""

from __future__ import annotations

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from test_api_security import Device, session_for, statements
from conftest import FLIGHT_DATE

TOKEN = "operator-token-for-tests"
OP = {"x-operator-token": TOKEN}
RIDER_KEY = "specimen-rider-purchase-key"
TR_IBAN = "TR330006100519786457841326"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CLAUSE_RIDER_PURCHASE_KEY_SHA256", hashlib.sha256(RIDER_KEY.encode()).hexdigest())
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN))
    with TestClient(app) as c:
        yield c


def register(client):
    device = Device()
    address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
    return device, address


def signed_post(client, device, address, purpose, terms, path, body):
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": purpose, "terms": terms}).json()
    return client.post(path, json={**body, "nonce": challenge["nonce"],
                                   "signature": device.sign(challenge["message"])})


def flight(**kw):
    body = {"peril": "flight_delay",
            "subject": {"route": "TK-IST-LHR", "flight_number": "TK1979", "departure_date": FLIGHT_DATE},
            "limit": 800, "term_days": 2}
    body.update(kw)
    return body


def trip_interest(value=1200):
    return {"what": "a return trip to London", "country": "TR", "inside_trigger_area": True,
            "value_at_risk": value, "size": {"kind": "trip", "value": value}}


# ---------------------------------------------------------------------------
# Partners
# ---------------------------------------------------------------------------


def make_partner(client, **kw):
    body = {"name": "Specimen Travel (not a real company)", "commission": 0.1,
            "perils": ["flight_delay"], "countries": ["TR"], "fund": 50_000}
    body.update(kw)
    reply = client.post("/api/operator/partners", json=body, headers=OP)
    assert reply.status_code == 200, reply.text
    return reply.json()


def test_only_the_operator_admits_a_partner(client) -> None:
    assert client.post("/api/operator/partners", json={"name": "x"}).status_code == 401
    made = make_partner(client)
    assert made["api_key"].startswith("ck_live_")
    listed = client.get("/api/operator/partners", headers=OP).json()["partners"]
    assert made["api_key"] not in str(listed), "the key is shown once, then only its hash is kept"


def test_a_partner_binds_cover_that_belongs_to_the_customer(client) -> None:
    made = make_partner(client)
    key = {"x-clause-key": made["api_key"]}
    price = client.post("/api/partner/v1/quote", json=flight(), headers=key).json()
    assert price["partner"]["commission"] <= price["expense_load"] + 1e-6

    customer_device, customer = register(client)
    reply = client.post("/api/partner/v1/policies", headers=key, json={
        **flight(), "external_ref": "SPECIMEN-BOOKING-1", "interest": trip_interest(),
        "beneficiary": {"address": customer}})
    assert reply.status_code == 200, reply.text
    policy = reply.json()["policy"]
    assert policy["holder"] == customer and policy["external_ref"] == "SPECIMEN-BOOKING-1"
    assert policy["commission"] > 0

    # The partner paid the premium and the issuer's fee, and was paid its
    # commission back out of the premium.
    me = client.get("/api/partner/v1/me", headers=key).json()
    fee = policy["metadata"].get("fronting_fee", 0.0)
    assert me["balance"] == pytest.approx(50_000 - policy["premium"] - fee + policy["commission"], abs=0.02)
    assert me["partner"]["sold"] == 1

    # Idempotent on the reference: a retry does not buy twice.
    again = client.post("/api/partner/v1/policies", headers=key, json={
        **flight(), "external_ref": "SPECIMEN-BOOKING-1", "interest": trip_interest(),
        "beneficiary": {"address": customer}})
    assert again.json()["replayed"] is True
    assert client.get("/api/partner/v1/me", headers=key).json()["partner"]["sold"] == 1


def test_a_customer_without_an_address_is_paid_at_their_bank(client) -> None:
    made = make_partner(client)
    key = {"x-clause-key": made["api_key"]}
    reply = client.post("/api/partner/v1/policies", headers=key, json={
        **flight(), "external_ref": "SPECIMEN-BOOKING-2", "interest": trip_interest(),
        "beneficiary": {"payout": {"method": "bank", "iban": TR_IBAN,
                                   "holder_name": "Specimen Customer"}}})
    assert reply.status_code == 200, reply.text
    assert client.post("/api/partner/v1/policies", headers=key, json={
        **flight(), "external_ref": "SPECIMEN-BOOKING-3", "interest": trip_interest(),
        "beneficiary": {}}).status_code == 422


def test_a_partner_cannot_sell_what_it_was_not_admitted_for(client) -> None:
    made = make_partner(client)
    key = {"x-clause-key": made["api_key"]}
    _, customer = register(client)
    reply = client.post("/api/partner/v1/policies", headers=key, json={
        "peril": "earthquake", "subject": {"location": "IST-KADIKOY", "radius_km": 50},
        "limit": 5_000, "term_days": 365, "external_ref": "SPECIMEN-4",
        "interest": {"what": "a flat", "country": "TR", "inside_trigger_area": True,
                     "value_at_risk": 50_000, "size": {"kind": "home", "building": "flat", "area_m2": 90}},
        "beneficiary": {"address": customer}})
    assert reply.status_code == 403


def test_a_partners_screening_does_not_stand_in_for_an_identity_check(client) -> None:
    made = make_partner(client, perils=["flight_delay", "earthquake"])
    key = {"x-clause-key": made["api_key"]}
    _, customer = register(client)
    reply = client.post("/api/partner/v1/policies", headers=key, json={
        "peril": "earthquake", "subject": {"location": "IST-KADIKOY", "radius_km": 50},
        "limit": 40_000, "term_days": 365, "external_ref": "SPECIMEN-5",
        "interest": {"what": "a flat", "country": "TR", "inside_trigger_area": True,
                     "value_at_risk": 60_000, "size": {"kind": "home", "building": "flat", "area_m2": 120}},
        "beneficiary": {"address": customer}})
    assert reply.status_code == 451
    assert "sanctions clear" in str(reply.json()) or "identity" in str(reply.json())


def test_a_suspended_or_unknown_key_is_refused(client) -> None:
    made = make_partner(client)
    assert client.get("/api/partner/v1/me", headers={"x-clause-key": "ck_live_nope"}).status_code == 401
    pid = made["partner"]["partner_id"]
    client.post(f"/api/operator/partners/{pid}/suspend", headers=OP)
    assert client.get("/api/partner/v1/me", headers={"x-clause-key": made["api_key"]}).status_code == 401


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------


def test_a_payout_destination_is_signed_by_its_owner(client) -> None:
    device, address = register(client)
    body = {"account": address, "method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"}
    terms = {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"}
    # Signed for one IBAN, sent with another: refused.
    other = dict(body, iban="TR320010009999901234567890")
    assert signed_post(client, device, address, "payout", terms,
                       "/api/payouts/preference", other).status_code == 401
    reply = signed_post(client, device, address, "payout", terms, "/api/payouts/preference", body)
    assert reply.status_code == 200, reply.text
    shown = reply.json()["preference"]["destination"]
    assert TR_IBAN not in shown and shown.startswith("TR33 ••••")
    token = session_for(client, device, address)
    mine = client.get("/api/payouts", headers={"authorization": f"Bearer {token}"}).json()
    assert mine["preference"]["method"] == "bank" and mine["rail"] == "manual"


def test_a_bad_iban_is_refused_before_it_is_stored(client) -> None:
    device, address = register(client)
    bad = TR_IBAN[:-1] + "7"
    terms = {"method": "bank", "iban": bad, "holder_name": "Specimen Holder"}
    reply = signed_post(client, device, address, "payout", terms, "/api/payouts/preference",
                        {"account": address, **terms})
    assert reply.status_code == 422


# ---------------------------------------------------------------------------
# Rider's mandate
# ---------------------------------------------------------------------------


MANDATE = {"max_premium_per_policy": 150.0, "max_premium_total": 300.0,
           "max_limit_per_policy": 1_000.0, "perils": "flight_delay", "days": 30}


def sign_mandate(client, device, address, **over):
    terms = {**MANDATE, **over}
    body = {"account": address, **terms, "country": "TR",
            "attestations": statements(client, address, "sanctions_clear")}
    return signed_post(client, device, address, "mandate", terms, "/api/mandate", body)


def rider_buy(client, token, key=RIDER_KEY, **kw):
    body = {**flight(), "mandate_token": token, "interest": trip_interest(), "max_premium": 150}
    body.update(kw)
    return client.post("/api/rider/purchase", json=body, headers={"x-clause-rider-key": key})


def test_rider_buys_only_through_the_latch_key_and_inside_the_mandate(client) -> None:
    device, address = register(client)
    reply = sign_mandate(client, device, address)
    assert reply.status_code == 200, reply.text
    token = reply.json()["token"]

    # Without the key only the Latch holds, nothing.
    assert rider_buy(client, token, key="guess").status_code == 401
    # With it, inside the terms: bought, for the mandate's owner.
    bought = rider_buy(client, token)
    assert bought.status_code == 200, bought.text
    policy = bought.json()["policy"]
    assert policy["holder"] == address and policy["metadata"]["bought_by"] == "rider"
    # Outside them: refused, whatever the model asked for.
    assert rider_buy(client, token, limit=5_000).status_code == 403
    assert rider_buy(client, token, peril="earthquake",
                     subject={"location": "IST-KADIKOY", "radius_km": 50}).status_code == 403
    assert rider_buy(client, "rm_forged").status_code == 403


def test_the_mandate_total_is_a_hard_ceiling(client) -> None:
    device, address = register(client)
    price = client.post("/api/quote", json=flight()).json()["premium"]
    total = round(price * 1.5, 2)
    token = sign_mandate(client, device, address, max_premium_per_policy=total,
                         max_premium_total=total).json()["token"]
    first = rider_buy(client, token)
    assert first.status_code == 200, first.text
    second = rider_buy(client, token)
    # Half a premium is left: the ceiling passed to the pool refuses the bind.
    assert second.status_code == 409, second.text
    token_s = session_for(client, device, address)
    mandate = client.get("/api/mandate", headers={"authorization": f"Bearer {token_s}"}).json()["mandate"]
    assert mandate["spent"] <= total + 0.01


def test_a_mandate_is_signed_over_its_exact_terms(client) -> None:
    device, address = register(client)
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "mandate", "terms": MANDATE}).json()
    body = {"account": address, **MANDATE, "max_premium_total": 300_00.0, "country": "TR",
            "attestations": statements(client, address, "sanctions_clear"),
            "nonce": challenge["nonce"], "signature": device.sign(challenge["message"])}
    assert client.post("/api/mandate", json=body).status_code == 401


def test_cover_rider_bought_can_be_cancelled_for_a_day(client) -> None:
    device, address = register(client)
    token = sign_mandate(client, device, address).json()["token"]
    policy = rider_buy(client, token).json()["policy"]
    before = client.get("/api/wallet", headers={
        "authorization": f"Bearer {session_for(client, device, address)}"}).json()["wallet"]["balance"]
    reply = signed_post(client, device, address, "cancel", {"policy_id": policy["policy_id"]},
                        f"/api/policies/{policy['policy_id']}/cancel", {"account": address})
    assert reply.status_code == 200, reply.text
    assert reply.json()["policy"]["status"] == "cancelled"
    # The token leaves the wallet: burned on chain, no owner, the burn on record.
    burned = reply.json()["policy"]["metadata"]["token"]
    assert burned["owner"] is None and burned["burned_from"] == address and burned["burned_at"]
    assert burned["burned_block"] >= burned["minted_block"]
    card = client.get(f"/api/policies/{policy['policy_id']}/token").json()
    assert card["burned"] and card["token"]["owner"] is None
    after = client.get("/api/wallet", headers={
        "authorization": f"Bearer {session_for(client, device, address)}"}).json()["wallet"]["balance"]
    # Within the day, the premium and the issuer's fee both come back.
    assert after == pytest.approx(before + policy["premium"] + policy["metadata"].get("fronting_fee", 0.0), abs=0.02)
    # The price went back to the mandate too.
    token_s = session_for(client, device, address)
    mandate = client.get("/api/mandate", headers={"authorization": f"Bearer {token_s}"}).json()["mandate"]
    assert mandate["spent"] == pytest.approx(0, abs=0.01)


def test_a_token_cancelled_before_burning_existed_is_burned_on_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUSE_RIDER_PURCHASE_KEY_SHA256", hashlib.sha256(RIDER_KEY.encode()).hexdigest())
    monkeypatch.setenv("CLAUSE_STATE_DIR", str(tmp_path))
    settings = Settings(faucet=True, operator_token=TOKEN)
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True, settings=settings)
    with TestClient(app) as c:
        device, address = register(c)
        token = sign_mandate(c, device, address).json()["token"]
        policy = rider_buy(c, token).json()["policy"]
        reply = signed_post(c, device, address, "cancel", {"policy_id": policy["policy_id"]},
                            f"/api/policies/{policy['policy_id']}/cancel", {"account": address})
        assert reply.status_code == 200, reply.text
        # As the earlier build left it: cancelled, token still owned.
        kept = app.state.pool.policies[policy["policy_id"]].metadata["token"]
        for key in ("burned_at", "burned_block", "burned_from", "burned_because"):
            kept.pop(key, None)
        kept["owner"] = address
    again = create_app(trials=400, seed=11, run_chain=False, seed_book=True, settings=settings)
    with TestClient(again) as c:
        card = c.get(f"/api/policies/{policy['policy_id']}/token").json()
        assert card["burned"] and card["token"]["owner"] is None and card["token"]["burned_from"] == address


def test_cover_bought_by_a_person_is_not_cancellable_here(client) -> None:
    device, address = register(client)
    token = sign_mandate(client, device, address).json()["token"]
    policy = rider_buy(client, token).json()["policy"]
    other_device, other = register(client)
    reply = signed_post(client, other_device, other, "cancel", {"policy_id": policy["policy_id"]},
                        f"/api/policies/{policy['policy_id']}/cancel", {"account": other})
    assert reply.status_code == 404


def test_revoking_ends_the_mandate(client) -> None:
    device, address = register(client)
    token = sign_mandate(client, device, address).json()["token"]
    reply = signed_post(client, device, address, "mandate", {"revoke": True},
                        "/api/mandate/revoke", {"account": address})
    assert reply.json()["revoked"] == 1
    assert rider_buy(client, token).status_code == 403


def test_the_model_never_holds_the_mandate(monkeypatch) -> None:
    """The token is added to the purchase by Rider's own code, not the model."""
    from clause.agent import rider as rider_mod

    seen = {}
    r = rider_mod.Rider(authority=rider_mod.Authority(latch=None, buy_latch="lat_specimen"),
                        anthropic_key="k")
    monkeypatch.setattr(r.buy_latch, "may", lambda m, p, b: (True, ""))
    monkeypatch.setattr(r.buy_latch, "_call", lambda path, **kw: seen.update(kw["body"]) or {"policy": {}})
    calls = iter([
        {"content": [{"type": "tool_use", "id": "1", "name": "buy_cover", "input": {
            "peril": "flight_delay", "subject": {}, "limit": 800, "term_days": 2,
            "interest": {}, "max_premium": 50}},
            {"type": "tool_use", "id": "2", "name": "buy_cover", "input": {
            "peril": "flight_delay", "subject": {}, "limit": 800, "term_days": 2,
            "interest": {}, "max_premium": 50}}]},
        {"content": [{"type": "text", "text": "done"}]},
    ])
    sent = []

    def model(conversation, system, tools):
        sent.append((conversation, tools))
        return next(calls)

    monkeypatch.setattr(r, "_model", model)
    out = r.answer([{"role": "user", "content": "buy it"}], mandate_token="rm_secret")
    assert seen["mandate_token"] == "rm_secret"
    assert "rm_secret" not in str(sent)
    assert out["bought"] == 1, "one purchase per request"
    # Without a mandate the tool is not even offered.
    sent.clear()
    calls = iter([{"content": [{"type": "text", "text": "ok"}]}])
    r.answer([{"role": "user", "content": "buy it"}])
    assert all(t["name"] != "buy_cover" for t in sent[0][1])


def test_webhooks_are_signed_and_retried() -> None:
    from clause.protocol.partners import Partners

    got = []
    state = {"up": False}

    def fetch(url, body, headers):
        if not state["up"]:
            raise OSError("down")
        got.append((body, headers))
        return 200

    book = Partners(fetcher=fetch)
    partner, _ = book.create(name="Specimen Travel (not a real company)", commission=0.1,
                             perils=["flight_delay"], countries=["TR"],
                             webhook_url="https://hooks.example/clause")
    delivery = book.notify(partner, {"type": "policy.settled", "policy_id": "CLS-1"}, now=1000.0)
    assert not delivery["delivered"] and "down" in delivery["last_error"]
    state["up"] = True
    assert book.retry(now=1000.0 + 61) == 1
    body, headers = got[0]
    assert headers["x-clause-signature"] == Partners.sign(
        partner.webhook_secret, headers["x-clause-timestamp"], body)
    with pytest.raises(Exception):
        book.create(name="x y", commission=0.1, perils=[], countries=[], webhook_url="http://insecure")


def test_a_partner_policy_refund_goes_back_to_the_partner_net_of_commission() -> None:
    from clause.pricing import PricingEngine
    from clause.protocol import Pool, Wallets

    wallets = Wallets(demo_balance=0.0)
    pool = Pool(engine=PricingEngine(trials=500, seed=2), wallets=wallets)
    for who, amount in (("lp", 5_000_000), ("partner", 10_000)):
        wallets.connect(who, fund=False)
        wallets.credit(who, amount, "seed", kind="faucet")
    pool.deposit("lp", 5_000_000)
    policy = pool.write(peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
                        limit=5_000, term_days=365, holder="customer", payer="partner")
    paid = pool.pay_commission(policy, "partner", 0.1 * policy.premium)
    assert wallets.require("partner").balance == pytest.approx(10_000 - policy.premium + paid)
    pool.expire(policy)
    assert wallets.require("partner").balance == pytest.approx(10_000)
    assert pool.tranches["senior"].balance == pytest.approx(5_000_000)
    pool.check_ledger()
