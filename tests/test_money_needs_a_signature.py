"""A session is for reading, and one route was spending with it.

clause/protocol/auth.py says it in its own words:

    session    a short lived token follows, for reads only

    Writes are not covered by the session. A transaction carries its own
    signature over its own terms, so a captured session cannot buy a
    different policy than the one the holder approved.

Every money-touching route in the API holds to that except one.
POST /api/applications/{id}/withdraw released the escrow on a session alone,
with no signature anywhere and no rate limit either: measured against the
running app, 4,925.39 USDC came back to the wallet on a bare session. A
stolen session was a stolen view everywhere else and a stolen refund here.

The second half of this file is the other route the same sweep found with no
limit on it: POST /api/policies/{id}/anchor/claim, where each call can put a
burn and a mint on the issuer's key.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from test_api_security import Device, session_for
from test_documents import TOKEN, pending_application

APP = Path(__file__).resolve().parent.parent / "clause" / "api" / "app.py"


@pytest.fixture
def client():
    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN,
                                       specimens=True))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def balance(client, device, address) -> float:
    return client.get("/api/wallet", headers={
        "authorization": f"Bearer {session_for(client, device, address)}"
    }).json()["wallet"]["balance"]


# -- the escrow ------------------------------------------------------------

def test_a_session_alone_cannot_release_the_escrow(client) -> None:
    device, address, application = pending_application(client)
    app_id = application["app_id"]
    before = balance(client, device, address)
    session = {"authorization": f"Bearer {session_for(client, device, address)}"}

    bare = client.post(f"/api/applications/{app_id}/withdraw", headers=session,
                       json={})
    assert bare.status_code == 422, bare.text
    forged = client.post(f"/api/applications/{app_id}/withdraw", headers=session,
                         json={"account": address, "nonce": "nope",
                               "signature": "nope"})
    assert forged.status_code == 401, forged.text
    assert balance(client, device, address) == pytest.approx(before, abs=0.01)


def test_a_signature_over_the_application_releases_it(client) -> None:
    """The legitimate path, and the same figure as before the signature was
    required, so the fix did not quietly change the refund."""
    device, address, application = pending_application(client)
    app_id = application["app_id"]
    before = balance(client, device, address)

    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "withdraw-application",
        "terms": {"app_id": app_id}}).json()
    done = client.post(f"/api/applications/{app_id}/withdraw", json={
        "account": address, "nonce": challenge["nonce"],
        "signature": device.sign(challenge["message"])})
    assert done.status_code == 200, done.text
    assert balance(client, device, address) > before
    assert done.json()["application"]["status"] == "withdrawn"


def test_a_signature_for_one_application_does_not_release_another(client) -> None:
    device, address, first = pending_application(client)
    _d2, _a2, second = pending_application(client)
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "withdraw-application",
        "terms": {"app_id": first["app_id"]}}).json()
    wrong = client.post(f"/api/applications/{second['app_id']}/withdraw", json={
        "account": address, "nonce": challenge["nonce"],
        "signature": device.sign(challenge["message"])})
    assert wrong.status_code == 401, wrong.text


def test_somebody_elses_signature_does_not_release_it(client) -> None:
    _device, _address, application = pending_application(client)
    other = Device()
    theirs = client.post("/api/auth/register",
                         json={"public_key": other.public}).json()["address"]
    challenge = client.post("/api/auth/challenge", json={
        "address": theirs, "purpose": "withdraw-application",
        "terms": {"app_id": application["app_id"]}}).json()
    reply = client.post(f"/api/applications/{application['app_id']}/withdraw",
                        json={"account": theirs, "nonce": challenge["nonce"],
                              "signature": other.sign(challenge["message"])})
    assert reply.status_code == 404, reply.text


def test_the_nonce_is_spent(client) -> None:
    device, address, application = pending_application(client)
    app_id = application["app_id"]
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "withdraw-application",
        "terms": {"app_id": app_id}}).json()
    body = {"account": address, "nonce": challenge["nonce"],
            "signature": device.sign(challenge["message"])}
    assert client.post(f"/api/applications/{app_id}/withdraw", json=body).status_code == 200
    again = client.post(f"/api/applications/{app_id}/withdraw", json=body)
    assert again.status_code == 401, again.text


# -- the shape of the rule, across the file --------------------------------

def money_routes_on_a_session_alone() -> list[str]:
    """Every write route that can move money with a session and no signature.

    What counts as moving money is a balance changing or an escrow being
    released, which is "wallets.credit", "wallets.debit", the pool's own
    deposit and withdraw, a payout, an escrow refund or a cashout. Not
    "wallets.require", which reads a balance, and not "links.wallets_of",
    which reads the addresses somebody has linked: the first version of this
    matched the word "wallets" and flagged the token-claim route, which spends
    the issuer's gas rather than anybody's balance.

    The faucet is excluded: it exists only where the demonstration switch is
    on, and giving yourself pretend money is not a loss. /api/funding is
    excluded because it announces a transfer and moves nothing.
    """
    src = APP.read_text(encoding="utf-8")
    allowed = {"/api/wallet/faucet", "/api/funding"}
    out = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if getattr(func, "attr", None) not in ("post", "put", "patch", "delete"):
                continue
            path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else "?"
            body = ast.get_source_segment(src, node) or ""
            if path in allowed:
                continue
            moves = any(w in body for w in ("wallets.credit", "wallets.debit",
                                            "refund_escrow", "pool.deposit",
                                            "pool.withdraw", "payouts.", "cashout("))
            if not moves:
                continue
            if "signed(" in body or "x-operator-token" in body or "require_admin" in body:
                continue
            if "Depends(bearer)" in body[:700]:
                out.append(f"app.py:{node.lineno} {path}")
    return out


def test_no_money_route_is_satisfied_by_a_session(client) -> None:
    found = money_routes_on_a_session_alone()
    assert not found, "\n".join(found)


# -- the issuer's key ------------------------------------------------------

def test_the_claim_route_is_behind_a_limit() -> None:
    """Each call can put a burn and a mint on the issuer's key. It was the
    only route touching the key with nothing to slow it down."""
    src = APP.read_text(encoding="utf-8")
    at = src.index('@app.post("/api/policies/{policy_id}/anchor/claim")')
    body = src[at:src.index("\n    @app.", at + 10)]
    assert 'guard(http, "anchor"' in body
    assert "http: Request" in body


def test_a_token_cannot_be_moved_without_end() -> None:
    """Twelve alternations between two linked wallets queued twelve burn and
    mint pairs, about 8.4 million gas, before this was counted."""
    from types import SimpleNamespace

    from clause.anchor import Anchor, AnchorError

    first, second = "0x" + "a" * 40, "0x" + "b" * 40
    anchor = Anchor(pool=SimpleNamespace(policies={}), links=None)
    policy = SimpleNamespace(policy_id="CLS-TEST", holder="H",
                             metadata={"token": {"terms_hash": "0x" + "11" * 32}})

    def sent(intents):
        for intent in intents:
            intent.status, intent.tx_hash = "sent", "0x" + "cc" * 32

    sent(anchor.claim(policy, first))
    pairs = 0
    refused = None
    for turn in range(12):
        try:
            queued = anchor.claim(policy, second if turn % 2 == 0 else first)
        except AnchorError as error:
            refused = str(error)
            break
        sent(queued)
        pairs += sum(1 for i in queued if i.kind == "burn")

    assert refused, f"it never refused; {pairs} pairs queued"
    assert pairs == anchor.REISSUE_LIMIT == 3
    assert anchor.reissues("CLS-TEST") == 3
    assert "ask the operator" in refused


def test_asking_for_the_wallet_it_is_already_at_costs_nothing() -> None:
    """So the cap is not spent by a page that asks twice."""
    from types import SimpleNamespace

    from clause.anchor import Anchor

    wallet = "0x" + "a" * 40
    anchor = Anchor(pool=SimpleNamespace(policies={}), links=None)
    policy = SimpleNamespace(policy_id="CLS-TWICE", holder="H",
                             metadata={"token": {"terms_hash": "0x" + "11" * 32}})
    for intent in anchor.claim(policy, wallet):
        intent.status, intent.tx_hash = "sent", "0x" + "cc" * 32
    assert anchor.claim(policy, wallet) == []
    assert anchor.reissues("CLS-TWICE") == 0


# -- and the cap that stopped a claim being minted at all ------------------

def test_the_enhanced_statement_can_be_minted(client) -> None:
    """ChallengeRequest.purpose was capped at sixteen characters and
    /api/eligibility/demo reuses that model, where the purposes are claims:
    "identity_enhanced" is seventeen, so the enhanced statement could not be
    issued and a buyer above the enhanced threshold could not finish."""
    device = Device()
    address = client.post("/api/auth/register",
                          json={"public_key": device.public}).json()["address"]
    for claim in ("sanctions_clear", "identity_basic", "identity_enhanced"):
        reply = client.post("/api/eligibility/demo",
                            json={"address": address, "purpose": claim})
        assert reply.status_code == 200, (claim, reply.text)
