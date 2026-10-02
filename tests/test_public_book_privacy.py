"""What a stranger reading the public book is told about the person who bought.

Measured against the live deployment, unauthenticated, before any of this was
written:

    GET /api/policies?limit=200
      holder                     null       in 200 of 200 rows
      metadata.token.owner       the same address, in full, in 199 of 200
      metadata.property.id       an unsalted hash of the postal address
      subject.place              "222. Cadde, Atakent Mahallesi,
                                  Küçükçekmece, İstanbul"

    GET /api/policies/CLS-EDE2DF07C9DA/token        (what tokenURI points at)
      description  "...on shaking at the address: 222. Cadde, Atakent
                    Mahallesi, Küçükçekmece, İstanbul..."
      Where        the same, in full
      token.owner  the holder

The redaction that removed ``holder`` came from an earlier audit, and the
docstring on the route says so. It removed one copy of the address and left
another one key deeper, and the policy token -- which a block explorer reaches
from the chain, beside the wallet that holds it -- carried the buyer's street
and house number as a trait.

These tests buy a policy whose place is a street address and then read the
book the way a stranger does.
"""

from __future__ import annotations

import base64
import json

import pytest

from test_api_security import (Device, buy_body, buy_terms, client, buyer,  # noqa: F401
                               session_for)

STREET = "222. Cadde, Atakent Mahallesi, Küçükçekmece, İstanbul"
# 41.0453, 28.7827 -- the coordinate the live site resolved that address to.
AT = {"latitude": 41.0453, "longitude": 28.7827, "place": STREET,
      "radius_km": 50, "built": 2005}


@pytest.fixture
def bought(client, buyer):
    """One policy on a street address, and the address that holds it."""
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy",
        "terms": buy_terms(subject=dict(AT, radius_km=50.0)),
    }).json()
    body = buy_body(address, challenge["nonce"],
                    device.sign(challenge["message"]), client=client, subject=AT)
    # With an address on it, so the policy carries metadata.property: the
    # fingerprint of the address, which is what the public row was publishing.
    body["interest"] = dict(body["interest"], address={
        "street": "222. Cadde", "number": "14", "flat": "7",
        "postcode": "34303", "city": "Küçükçekmece",
    })
    reply = client.post("/api/policies", json=body)
    assert reply.status_code == 200, reply.text
    return device, address, reply.json()["policy"]["policy_id"]


def anonymous_row(client, policy_id):
    rows = client.get("/api/policies?limit=200").json()["items"]
    found = [row for row in rows if row["policy_id"] == policy_id]
    assert found, "the policy should still be in the public book"
    return found[0]


# -- the person ------------------------------------------------------------

def test_the_holder_is_not_published_under_another_name(client, bought) -> None:
    _device, address, policy_id = bought
    row = anonymous_row(client, policy_id)
    assert row["holder"] is None
    assert "owner" not in (row["metadata"].get("token") or {})
    # Whatever else the row grows, the address is not in it.
    assert address not in json.dumps(row), (
        "the holder's address is published somewhere in the row")


def test_the_address_hash_is_not_published(client, bought) -> None:
    """Unsalted blake2b over country, town, postcode, street, number, flat and
    the coordinate -- and the coordinate is in the same row, so what is left to
    guess is a street and a house number."""
    device, address, policy_id = bought
    token = session_for(client, device, address)
    rows = client.get("/api/policies?limit=200",
                      headers={"Authorization": f"Bearer {token}"}).json()["items"]
    mine = [row for row in rows if row["policy_id"] == policy_id][0]
    assert mine["metadata"]["property"]["id"], (
        "this policy carries no fingerprint, so the test proves nothing")
    assert "property" not in anonymous_row(client, policy_id)["metadata"]


# -- the place -------------------------------------------------------------

def test_the_street_is_not_published(client, bought) -> None:
    _device, _address, policy_id = bought
    row = anonymous_row(client, policy_id)
    body = json.dumps(row, ensure_ascii=False)
    assert "222. Cadde" not in body
    assert "Atakent" not in body


def test_the_locality_still_is(client, bought) -> None:
    """Cut back, not removed: the book's shape is the capital argument, and
    where the cover sits is part of it."""
    row = anonymous_row(client, policy_id=bought[2])
    assert row["subject"]["place"] == "Küçükçekmece, İstanbul"
    assert "Küçükçekmece" in row["subject_text"]


def test_the_token_an_explorer_reads_names_no_street(client, bought) -> None:
    """ClausePolicy.tokenURI points here, and nothing authenticates it."""
    _device, _address, policy_id = bought
    reply = client.get(f"/api/policies/{policy_id}/token")
    assert reply.status_code == 200
    token = reply.json()
    drawn = token.get("image", "")
    if drawn.startswith("data:image/svg+xml;base64,"):
        drawn = base64.b64decode(drawn.split(",", 1)[1]).decode("utf-8")
    body = json.dumps(token, ensure_ascii=False) + drawn
    assert "222. Cadde" not in body
    assert "Atakent" not in body
    where = [a["value"] for a in token["attributes"]
             if a["trait_type"] == "Where"]
    assert where and "Küçükçekmece" in where[0]


def test_one_policy_read_alone_is_redacted_the_same_way(client, bought) -> None:
    """Two routes serve a policy. The listing was the one that was audited."""
    _device, address, policy_id = bought
    row = client.get(f"/api/policies/{policy_id}").json()["policy"]
    assert row["holder"] is None
    assert address not in json.dumps(row)
    assert "222. Cadde" not in json.dumps(row, ensure_ascii=False)


# -- and what must not be lost ---------------------------------------------

def test_the_holder_still_sees_their_own_policy_whole(client, bought) -> None:
    device, address, policy_id = bought
    token = session_for(client, device, address)
    rows = client.get("/api/policies?limit=200",
                      headers={"Authorization": f"Bearer {token}"}).json()["items"]
    mine = [row for row in rows if row["policy_id"] == policy_id][0]
    assert mine["holder"] == address
    assert mine["subject"]["place"] == STREET
    assert "222. Cadde" in mine["subject_text"]


def test_the_public_row_still_carries_what_the_pages_read(client, bought) -> None:
    """The map filters minted policies on metadata.token, and the pool page
    reads the terms. Redacting is not the same as deleting."""
    row = anonymous_row(client, policy_id=bought[2])
    assert isinstance(row["metadata"].get("token"), dict)
    assert row["metadata"]["token"].get("token_id") == bought[2]
    for needed in ("peril", "limit", "premium", "status", "starts_at",
                   "ends_at", "subject", "structure", "predicate"):
        assert needed in row, needed


def test_a_place_with_no_street_in_it_is_left_alone(client, buyer) -> None:
    """The named places are "Kadıköy, İstanbul" and the like. Nothing to cut."""
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    policy_id = client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]),
        client=client,
    )).json()["policy"]["policy_id"]
    public = anonymous_row(client, policy_id)
    token = session_for(client, device, address)
    rows = client.get("/api/policies?limit=200",
                      headers={"Authorization": f"Bearer {token}"}).json()["items"]
    mine = [row for row in rows if row["policy_id"] == policy_id][0]
    assert public["subject"]["place"] == mine["subject"]["place"]
    assert public["subject_text"] == mine["subject_text"]

# -- the two copies the first fix missed -----------------------------------

def test_the_token_route_does_not_carry_the_owner(client, bought) -> None:
    """The first fix took the owner off the public listing and left it on the
    route a block explorer actually reads. Measured on the live deployment
    after that fix was written: token.owner, in full, unauthenticated."""
    _device, address, policy_id = bought
    token = client.get(f"/api/policies/{policy_id}/token").json()
    assert "owner" not in token["token"]
    assert address not in json.dumps(token)


def test_the_ledger_does_not_link_an_address_to_its_cover(client, bought) -> None:
    """One unauthenticated request gave which address bought which policy for
    how much: account, reference and amount on the same row."""
    _device, address, policy_id = bought
    rows = client.get("/api/pool/ledger?limit=500").json()["items"]
    assert rows, "the ledger should still be readable"
    assert any(row.get("reference") == policy_id for row in rows), (
        "this policy left no ledger entry, so the test proves nothing")
    assert all(row.get("account") is None for row in rows)
    # What the ledger is for is still there.
    row = [r for r in rows if r.get("reference") == policy_id][0]
    for needed in ("at", "kind", "amount", "balance_after"):
        assert needed in row and row[needed] is not None, needed


def test_the_ledger_still_shows_you_your_own_entries(client, bought) -> None:
    device, address, policy_id = bought
    session = session_for(client, device, address)
    rows = client.get("/api/pool/ledger?limit=500",
                      headers={"Authorization": f"Bearer {session}"}).json()["items"]
    ours = [row for row in rows if row.get("account") == address]
    assert ours, "the holder cannot see their own entries"
    assert any(row.get("reference") == policy_id for row in ours)

def test_the_burn_does_not_name_whose_token_it_was(client, bought) -> None:
    """burned_from is the holder's address, and the first redaction took only
    owner. Measured on the live book: one cancelled policy published it in the
    public listing and on the token card."""
    _device, address, policy_id = bought
    from clause.api.app import PUBLIC_TOKEN_KEYS, public_token
    assert "owner" not in PUBLIC_TOKEN_KEYS
    assert "burned_from" not in PUBLIC_TOKEN_KEYS
    pruned = public_token({"owner": address, "burned_from": address,
                           "token_id": policy_id, "burned_at": 1.0,
                           "a_key_added_later": address})
    assert pruned == {"token_id": policy_id, "burned_at": 1.0}, pruned


def test_both_public_views_prune_the_token_the_same_way(client, bought) -> None:
    """Two routes serve it and each one had its own idea of what to remove."""
    _device, _address, policy_id = bought
    listed = anonymous_row(client, policy_id)["metadata"]["token"]
    carded = client.get(f"/api/policies/{policy_id}/token").json()["token"]
    assert set(listed) == set(carded)

# -- the fourth outlet: who stands behind the book --------------------------

def test_the_pool_does_not_name_who_stands_behind_it(client, buyer) -> None:
    """The shape of the capital stack is what makes the solvency argument
    checkable. Whose it is, is not. Read with no credential the live
    deployment gave four addresses, each with its exact position."""
    device, address = buyer
    session = session_for(client, device, address)
    deposit = _deposit(client, device, address, 5_000.0)
    assert deposit.status_code == 200, deposit.text

    public = client.get("/api/pool").json()
    assert public["providers"], "the stack should still be readable"
    assert all(row["account"] is None for row in public["providers"])
    # The shape is all still there.
    for row in public["providers"]:
        for needed in ("tranche", "shares", "deposited", "withdrawn"):
            assert needed in row and row[needed] is not None, needed

    ours = client.get("/api/pool", headers={
        "Authorization": f"Bearer {session}"}).json()["providers"]
    assert any(row["account"] == address for row in ours), (
        "the holder cannot find their own capital")
    assert sum(1 for row in ours if row["account"] is not None) == 1


def _deposit(client, device, address, amount: float):
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "deposit", "terms": {"amount": amount},
    }).json()
    return client.post("/api/pool/deposit", json={
        "account": address, "amount": amount, "nonce": challenge["nonce"],
        "signature": device.sign(challenge["message"]),
    })
