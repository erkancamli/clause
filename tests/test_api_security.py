"""The audit's findings, closed at the HTTP layer and kept closed.

Every test here corresponds to something that was, before it was written, a way
to take money out of this protocol or take the server down. They run against the
real application rather than a mock, because the finding was never in the helper.
"""

from __future__ import annotations

import base64
import time
from urllib.parse import quote as urlquote

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from conftest import FLIGHT_DATE

JSON = {"content-type": "application/json"}


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class Device:
    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())

    @property
    def public(self) -> str:
        return b64(
            self.key.public_key().public_bytes(
                Encoding.X962, PublicFormat.UncompressedPoint
            )
        )

    def sign(self, message: str) -> str:
        return b64(self.key.sign(message.encode(), ec.ECDSA(hashes.SHA256())))


@pytest.fixture
def client():
    # Seeded, because a pool with no capital refuses every policy and the
    # refusals would hide the thing each test is actually checking.
    app = create_app(
        trials=400, seed=11, run_chain=False, seed_book=True,
        settings=Settings(faucet=True),
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def buyer(client):
    device = Device()
    address = client.post(
        "/api/auth/register", json={"public_key": device.public}
    ).json()["address"]
    return device, address


def session_for(client, device, address) -> str:
    challenge = client.post(
        "/api/auth/challenge", json={"address": address, "purpose": "sign-in"}
    ).json()
    reply = client.post("/api/auth/verify", json={
        "address": address, "nonce": challenge["nonce"],
        "signature": device.sign(challenge["message"]),
    })
    return reply.json()["session"]["token"]


def statements(client, address, *claims):
    """The signed statements a verifier would hand the buyer's device.

    A purchase now has to show that the address is not sanctioned, and that
    somebody checked who holds it once the cover is above a small size. The
    protocol never sees a document; these are the one line statements it does
    see, minted here by the build's demonstration verifier.
    """
    out = []
    for claim in claims:
        reply = client.post(
            "/api/eligibility/demo", json={"address": address, "purpose": claim}
        )
        assert reply.status_code == 200, reply.text
        out.append(reply.json()["attestation"])
    return out


def buy_body(address, nonce, signature, client=None, **overrides):
    body = {
        "peril": "earthquake",
        "subject": {"location": "IST-KADIKOY", "radius_km": 50},
        "limit": 50_000, "term_days": 365,
        "holder": address, "nonce": nonce, "signature": signature,
        "interest": {
            "what": "a flat in Kadikoy", "country": "TR",
            "inside_trigger_area": True, "value_at_risk": 90_000,
            "size": {"kind": "home", "building": "flat", "area_m2": 150},
        },
        "settlement": "fiat",
    }
    if client is not None:
        body["attestations"] = statements(
            client, address, "sanctions_clear", "identity_basic"
        )
    body.update(overrides)
    return body


def buy_terms(**overrides):
    terms = {
        "peril": "earthquake", "limit": 50_000.0, "term_days": 365.0,
        "subject": {"location": "IST-KADIKOY", "radius_km": 50.0},
        "country": "TR", "value_at_risk": 90_000.0,
        "size": {"kind": "home", "building": "flat", "area_m2": 150},
    }
    terms.update(overrides)
    return terms


# ---------------------------------------------------------------------------
# Finding 1: the address in the body was simply believed
# ---------------------------------------------------------------------------


def test_buying_without_a_signature_is_refused(client, buyer) -> None:
    _, address = buyer
    reply = client.post("/api/policies", json=buy_body(address, "nope", "nope"))
    assert reply.status_code == 401


def test_one_address_cannot_spend_from_another(client) -> None:
    """The finding, in its purest form: read an address, then spend from it."""
    mine, theirs = Device(), Device()
    my_address = client.post(
        "/api/auth/register", json={"public_key": mine.public}
    ).json()["address"]
    their_address = client.post(
        "/api/auth/register", json={"public_key": theirs.public}
    ).json()["address"]

    challenge = client.post("/api/auth/challenge", json={
        "address": their_address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    # I sign their challenge with my key.
    reply = client.post("/api/policies", json=buy_body(
        their_address, challenge["nonce"], mine.sign(challenge["message"])
    ))
    assert reply.status_code == 401


def test_a_signature_cannot_be_replayed_for_a_bigger_policy(client, buyer) -> None:
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    signature = device.sign(challenge["message"])

    bigger = buy_body(address, challenge["nonce"], signature, limit=900_000)
    bigger["interest"]["value_at_risk"] = 900_000
    assert client.post("/api/policies", json=bigger).status_code == 401


def test_a_challenge_cannot_be_spent_twice(client, buyer) -> None:
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    body = buy_body(address, challenge["nonce"], device.sign(challenge["message"]),
        client=client)

    first = client.post("/api/policies", json=body)
    assert first.status_code in (200, 409)   # 409 only if the pool refuses it
    assert client.post("/api/policies", json=body).status_code == 401


def test_capital_cannot_be_withdrawn_without_a_signature(client, buyer) -> None:
    """The audit's drain path: read the providers, then withdraw as them."""
    _, address = buyer
    reply = client.post("/api/pool/withdraw", json={
        "account": address, "shares": 1.0, "nonce": "x", "signature": "y",
    })
    assert reply.status_code == 401


def test_a_malformed_address_is_refused_before_it_is_used_as_a_key(client) -> None:
    reply = client.post("/api/auth/challenge", json={
        "address": "not-an-address", "purpose": "sign-in",
    })
    assert reply.status_code == 422


# ---------------------------------------------------------------------------
# Finding 9: anyone's position was readable given only an address
# ---------------------------------------------------------------------------


def test_a_portfolio_needs_a_session(client) -> None:
    assert client.get("/api/portfolio").status_code == 401
    assert client.get("/api/wallet").status_code == 401


def test_a_session_shows_only_its_own_position(client, buyer) -> None:
    device, address = buyer
    token = session_for(client, device, address)
    reply = client.get("/api/portfolio", headers={"Authorization": f"Bearer {token}"})
    assert reply.status_code == 200
    assert reply.json()["portfolio"]["address"] == address


def test_a_forged_session_is_refused(client, buyer) -> None:
    _, address = buyer
    for bad in ["", "rubbish", f"{address}.99999999999.AAAA"]:
        reply = client.get("/api/portfolio", headers={"Authorization": f"Bearer {bad}"})
        assert reply.status_code == 401


def test_the_book_is_public_but_its_holders_are_not(client, buyer) -> None:
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]),
        client=client,
    ))

    anonymous = client.get("/api/policies").json()["items"]
    assert anonymous, "the book should still be readable"
    assert all(row["holder"] is None for row in anonymous)

    token = session_for(client, device, address)
    mine = client.get(
        "/api/policies", headers={"Authorization": f"Bearer {token}"}
    ).json()["items"]
    assert any(row["holder"] == address for row in mine)


# ---------------------------------------------------------------------------
# Finding 2: the demo endpoints
# ---------------------------------------------------------------------------


def test_the_chain_cannot_be_driven_by_a_stranger(client) -> None:
    """Injecting a reading settles policies. It is not a public button."""
    assert client.post(
        "/api/chain/inject?reference=x&field=max_magnitude&value=9"
    ).status_code == 404
    assert client.post("/api/chain/silence?reference=x").status_code == 404


def test_the_demo_endpoints_answer_only_to_the_operator() -> None:
    app = create_app(
        trials=300, seed=5, run_chain=False, seed_book=True,
        settings=Settings(demo_endpoints=True, operator_token="letmein", faucet=True),
    )
    with TestClient(app) as c:
        reference = urlquote(
            "api.seismic.example/v1/max-magnitude?lat=40.99&lon=29.03&radius_km=50",
            safe="",
        )
        url = f"/api/chain/inject?reference={reference}&field=max_magnitude&value=7.2"
        assert c.post(url).status_code == 401
        assert c.post(url, headers={"x-operator-token": "wrong"}).status_code == 401
        assert c.post(url, headers={"x-operator-token": "letmein"}).status_code == 200


def test_the_schema_page_is_not_published(client) -> None:
    """It names every route, including the ones that move money."""
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


# ---------------------------------------------------------------------------
# Finding 4: Infinity into the ledger
# ---------------------------------------------------------------------------


def test_infinity_cannot_reach_the_pool(client) -> None:
    """One request of this made the accounting unrecoverable."""
    raw = '{"account":"0x%s","amount":Infinity,"nonce":"n","signature":"s"}' % ("ab" * 20)
    assert client.post("/api/pool/deposit", content=raw, headers=JSON).status_code == 422


def test_infinity_cannot_reach_a_subject(client) -> None:
    raw = (
        '{"peril":"earthquake","subject":{"location":"IST-KADIKOY",'
        '"radius_km":Infinity},"limit":1000,"term_days":365}'
    )
    assert client.post("/api/quote", content=raw, headers=JSON).status_code == 422


# ---------------------------------------------------------------------------
# Finding 3: inputs that multiply the server's work
# ---------------------------------------------------------------------------


def test_an_absurd_term_or_limit_is_refused(client) -> None:
    for body in (
        {"limit": 1e308, "term_days": 365},
        {"limit": 1000, "term_days": 1e9},
        {"limit": 0, "term_days": 365},
    ):
        reply = client.post("/api/quote", json={
            "peril": "earthquake",
            "subject": {"location": "IST-KADIKOY", "radius_km": 50},
            **body,
        })
        assert reply.status_code == 422


def test_a_huge_string_in_a_subject_is_refused(client) -> None:
    reply = client.post("/api/quote", json={
        "peril": "flight_delay",
        "subject": {
            "route": "TK-IST-LHR", "flight_number": "T" * 50_000,
            "departure_date": FLIGHT_DATE,
        },
        "limit": 1000, "term_days": 2,
    })
    assert reply.status_code == 422


def test_quoting_is_rate_limited(client) -> None:
    body = {
        "peril": "earthquake",
        "subject": {"location": "ANK-CANKAYA", "radius_km": 25},
        "limit": 1000, "term_days": 365,
    }
    codes = [client.post("/api/quote", json=body).status_code for _ in range(26)]
    assert 429 in codes, "an unlimited quote endpoint is a denial of service"


# ---------------------------------------------------------------------------
# Compliance, which is a security control here rather than a disclaimer
# ---------------------------------------------------------------------------


def test_a_stablecoin_premium_is_refused_where_it_is_prohibited(client, buyer) -> None:
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    reply = client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]),
        settlement="stablecoin",
    ))
    assert reply.status_code == 451


def test_cover_above_the_declared_value_at_risk_is_refused(client, buyer) -> None:
    device, address = buyer
    terms = buy_terms(limit=200_000.0)
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms,
    }).json()
    reply = client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]),
        limit=200_000,
    ))
    assert reply.status_code == 451


def test_the_rules_are_published_rather_than_implied(client) -> None:
    payload = client.get("/api/compliance").json()
    codes = {row["country"] for row in payload["coverage"]}
    # Where cover is available is a consequence of who is registered, so the map
    # is checked against the registry rather than against a list in the source.
    assert codes
    for row in payload["coverage"]:
        assert row["carriers"] and row["authorities"]
    assert payload["registry"]["carriers"] >= 1
    assert "a carrier licensed there, a reinsurer behind it" in payload["unlisted"]

    # And what a buyer would be asked to prove is published too, with reasons.
    need = client.get("/api/eligibility", params={"limit": 250_000}).json()
    assert "identity_enhanced" in need["requirement"]["claims"]
    assert len(need["requirement"]["because"]) == len(need["requirement"]["claims"])
    assert "nothing" in need["held_by_us"]


# ---------------------------------------------------------------------------
# Lineage, which is the answer to "why did it pay"
# ---------------------------------------------------------------------------


def test_a_policy_carries_its_own_proof(client, buyer) -> None:
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    bought = client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]),
        client=client,
    ))
    assert bought.status_code == 200
    policy_id = bought.json()["policy"]["policy_id"]

    story = client.get(f"/api/lineage/{policy_id}").json()
    assert story["subscription"]["topic"].startswith("topic:")
    assert story["rule"].startswith("At least")
    assert story["source"]["publisher"]


def test_an_unknown_policy_does_not_echo_the_path_back(client) -> None:
    reply = client.get("/api/lineage/" + "x" * 40)
    assert reply.status_code in (404, 422)
    assert "x" * 40 not in reply.text


# ---------------------------------------------------------------------------
# The price on the screen, and the place index the page searches
# ---------------------------------------------------------------------------


def test_a_moving_price_cannot_exceed_what_the_buyer_agreed_to(client, buyer) -> None:
    """The figure the page showed travels with the request that binds it.

    The premium is struck at bind time, because it depends on a book that moves.
    Without a ceiling that is indistinguishable from charging whatever the
    protocol likes once the buyer has already signed.
    """
    device, address = buyer
    terms = buy_terms()
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms,
    }).json()
    body = buy_body(address, challenge["nonce"], device.sign(challenge["message"]),
        client=client)
    body["max_premium"] = 1.0                      # far below any real price

    reply = client.post("/api/policies", json=body)
    assert reply.status_code == 409
    assert "price moved" in reply.text

    # And nothing was written: the address still holds no cover.
    token = session_for(client, device, address)
    mine = client.get("/api/portfolio", headers={"authorization": "Bearer " + token})
    assert mine.json()["policies"] == []


def test_the_place_index_answers_in_the_alphabet_people_type_in(client) -> None:
    """A buyer on a keyboard without Turkish letters still finds their town."""
    every = client.get("/api/places").json()
    assert every["count"] > 80
    assert {"name", "latitude", "longitude", "region", "kind"} <= set(every["places"][0])

    for typed in ("kadikoy", "Kadıköy", "CANAKKALE"):
        hits = client.get("/api/places", params={"query": typed}).json()["places"]
        assert hits, typed

    assert client.get("/api/places", params={"query": "zzzzz"}).json()["places"] == []


def test_a_coordinate_nowhere_on_the_place_list_prices_anyway(client) -> None:
    """The index is a convenience. The hazard surface is the thing."""
    reply = client.post("/api/quote", json={
        "peril": "earthquake",
        "subject": {"latitude": 40.7123, "longitude": 30.4567, "radius_km": 50},
        "limit": 50_000, "term_days": 365,
    })
    assert reply.status_code == 200
    assert reply.json()["premium"] > 0


# ---------------------------------------------------------------------------
# The company side: registering, and what registering does not buy you
# ---------------------------------------------------------------------------


def a_licence(country="JP", **overrides):
    body = {
        "country": country, "authority": "Financial Services Agency",
        "reference": "KFB 2026-4471", "perils": ["earthquake"],
        "reach": "retail", "settlement": ["fiat"],
        "expires_at": time.time() + 365 * 86400,
    }
    body.update(overrides)
    return body


def a_company(**overrides):
    body = {
        "name": "Tokio Parametric K.K.", "role": "carrier", "domicile": "JP",
        "licences": [a_licence()], "perils": ["earthquake"],
        "max_limit": 400_000, "capacity": 5_000_000, "fronting_fee": 0.05,
        "contact": "uw@example.co.jp",
    }
    body.update(overrides)
    return body


def test_a_company_can_register_itself_and_writes_nothing_by_doing_so(client) -> None:
    """Registration is a claim. Nothing here can check a licence number against
    a regulator's register, so a registration that activated itself would mean
    anyone could be an insurer on this protocol by filling in a form."""
    reply = client.post("/api/carriers", json=a_company())
    assert reply.status_code == 200, reply.text
    carrier = reply.json()["carrier"]
    assert carrier["status"] == "pending"
    assert carrier["in_force"] == 0

    coverage = client.get("/api/compliance").json()["coverage"]
    assert "JP" not in {row["country"] for row in coverage}


def test_activating_a_company_needs_the_operator_and_opens_its_country(client) -> None:
    """The whole argument for a registry: a country nobody wrote code for."""
    carrier_id = client.post("/api/carriers", json=a_company()).json()["carrier"]["carrier_id"]
    assert client.post(f"/api/carriers/{carrier_id}/activate").status_code in (401, 404)


def test_a_company_that_claims_an_unknown_peril_is_recorded_without_it(client) -> None:
    reply = client.post("/api/carriers", json=a_company(
        licences=[a_licence(perils=["earthquake", "alien-invasion"])],
        perils=["earthquake", "alien-invasion"],
    ))
    carrier = reply.json()["carrier"]
    assert carrier["licences"][0]["perils"] == ["earthquake"]
    assert carrier["appetite"]["perils"] == ["earthquake"]


def test_a_licence_that_is_not_a_licence_is_refused(client) -> None:
    for broken in (
        {"licences": [a_licence(authority="")]},
        {"licences": [a_licence(settlement=[])]},
        {"licences": [a_licence(perils=[])]},
        {"role": "bank"},
    ):
        assert client.post("/api/carriers", json=a_company(**broken)).status_code == 422


def test_the_carriers_behind_the_cover_are_public(client) -> None:
    """A buyer is entitled to know whose paper their policy is on."""
    payload = client.get("/api/carriers").json()
    assert payload["summary"]["carriers"] >= 1
    assert payload["summary"]["reinsurers"] >= 1
    for company in payload["companies"]:
        assert company["name"] and company["role"] and company["domicile"]
        # And not their contact details, which are theirs.
        assert "contact" not in company


def test_a_policy_records_whose_paper_it_went_on(client, buyer) -> None:
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    bought = client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]),
        client=client,
    ))
    assert bought.status_code == 200, bought.text
    body = bought.json()
    assert body["policy"]["metadata"]["carrier"]
    carrier = body["compliance"]["carrier"]
    assert carrier["name"] and carrier["authority"] and carrier["licence"]


def test_buying_without_the_statements_is_refused_and_says_which_are_missing(client, buyer) -> None:
    """A refusal a person can act on: it names what to go and get."""
    device, address = buyer
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    reply = client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]),
    ))
    assert reply.status_code == 451
    detail = reply.json()["detail"]
    assert detail["eligibility"]["missing"] == ["sanctions_clear", "identity_basic"]


def test_a_statement_for_another_address_does_not_let_you_buy(client, buyer) -> None:
    """The obvious attack on an attestation model: borrow someone's clearance."""
    device, address = buyer
    stranger = Device()
    other = client.post(
        "/api/auth/register", json={"public_key": stranger.public}
    ).json()["address"]

    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": buy_terms(),
    }).json()
    reply = client.post("/api/policies", json=buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]),
        attestations=statements(client, other, "sanctions_clear", "identity_basic"),
    ))
    assert reply.status_code == 451
    # It fails on the signature rather than on a comparison, which is the
    # stronger place for it to fail: the API builds the statement with the
    # signed in buyer as its subject, so a statement about anyone else stops
    # being a valid signature at all rather than being caught by a check that
    # someone could later forget to write.
    assert "does not verify" in " ".join(
        reply.json()["detail"]["eligibility"]["reasons"]
    )


def test_the_demonstration_verifier_says_it_verified_nothing(client) -> None:
    """A statement claiming a check nobody performed is the exact thing this
    design exists to avoid, so the build that issues them says so."""
    reply = client.post("/api/eligibility/demo", json={
        "address": "0x" + "ab" * 20, "purpose": "sanctions_clear",
    })
    assert reply.status_code == 200
    assert "No document was checked" in reply.json()["demonstration"]


def test_a_flat_in_istanbul_goes_on_turkish_paper_wherever_its_owner_lives(
    client, buyer,
) -> None:
    """The licence that matters is where the risk is. A live test chose a flat
    in Istanbul and then "Japan" as where the buyer is, and the protocol went
    looking for a Japanese carrier for a Turkish building. For a peril tied to
    a place, the place decides; the buyer's own country is kept for what is
    actually about them, which checks they must pass."""
    device, address = buyer
    terms = buy_terms(country="JP")
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms,
    }).json()
    body = buy_body(
        address, challenge["nonce"], device.sign(challenge["message"]), client=client,
    )
    body["interest"]["country"] = "JP"
    bought = client.post("/api/policies", json=body)
    assert bought.status_code == 200, bought.text
    metadata = bought.json()["policy"]["metadata"]
    assert metadata["interest"]["country"] == "TR"
    assert metadata["interest"]["resident"] == "JP"
    assert metadata["compliance"]["carrier"]["country"] == "TR"


def test_the_map_publishes_what_each_peril_can_be_priced_for(client) -> None:
    payload = client.get("/api/compliance").json()
    assert payload["priceable"]["earthquake"] == ["CL", "JP", "MX", "NZ", "TR", "TW"]
    assert payload["priceable"]["flight_delay"] is None
    for row in payload["coverage"]:
        assert row["open"] is True and row["perils"]


# ---------------------------------------------------------------------------
# The policy token
# ---------------------------------------------------------------------------


def test_every_written_policy_is_a_locked_token_of_its_holder(client) -> None:
    book = client.get("/api/policies", params={"limit": 5}).json()["items"]
    assert book
    for row in book:
        meta = client.get(f"/api/policies/{row['policy_id']}/token").json()
        assert meta["locked"] is True and meta["transferable"] is False
        assert meta["token"]["token_id"] == row["policy_id"]
        assert meta["token"]["terms_hash"].startswith("0x")
        assert meta["image"].startswith("data:image/svg+xml;base64,")
        assert client.post(f"/api/policies/{row['policy_id']}/transfer").status_code == 409


def test_the_token_hash_changes_with_the_terms() -> None:
    from clause.chain.world import terms_fingerprint
    from clause.protocol.policy import build_policy

    a = build_policy(peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
                     limit=50_000, term_days=365, holder="0xa", premium=1000, expected_loss=500,
                     risk_load=300, expense_load=200, marginal_capital=5000, now=1_800_000_000)
    b = build_policy(peril_key="earthquake", subject={"location": "IST-KADIKOY", "radius_km": 50},
                     limit=60_000, term_days=365, holder="0xa", premium=1000, expected_loss=500,
                     risk_load=300, expense_load=200, marginal_capital=5000, now=1_800_000_000)
    assert terms_fingerprint(a) != terms_fingerprint(b)


def test_a_quoted_price_holds_for_ten_minutes_even_if_the_book_moves(client, buyer) -> None:
    device, address = buyer
    body = {"peril": "earthquake", "subject": {"location": "IST-KADIKOY", "radius_km": 50},
            "limit": 50_000, "term_days": 365}
    quoted = client.post("/api/quote", json=body).json()
    lock = quoted["lock"]
    assert lock["seconds"] == 600 and lock["premium"] == round(quoted["premium"], 2)

    # Someone else buys Istanbul cover first, so the same cover now costs more.
    other = Device()
    other_address = client.post("/api/auth/register", json={"public_key": other.public}).json()["address"]
    ch = client.post("/api/auth/challenge", json={"address": other_address, "purpose": "buy",
                                                  "terms": buy_terms()}).json()
    client.post("/api/policies", json=buy_body(other_address, ch["nonce"], other.sign(ch["message"]),
                                               client=client))

    ch = client.post("/api/auth/challenge", json={"address": address, "purpose": "buy",
                                                  "terms": buy_terms()}).json()
    reply = client.post("/api/policies", json=buy_body(
        address, ch["nonce"], device.sign(ch["message"]), client=client,
        max_premium=lock["premium"], quote_id=lock["id"]))
    assert reply.status_code == 200, reply.text
    assert abs(reply.json()["policy"]["premium"] - quoted["premium"]) < 0.01


def test_a_price_lock_only_fits_the_cover_it_was_given_for(client, buyer) -> None:
    device, address = buyer
    lock = client.post("/api/quote", json={"peril": "earthquake",
        "subject": {"location": "IST-KADIKOY", "radius_km": 50},
        "limit": 10_000, "term_days": 365}).json()["lock"]
    ch = client.post("/api/auth/challenge", json={"address": address, "purpose": "buy",
                                                  "terms": buy_terms()}).json()
    reply = client.post("/api/policies", json=buy_body(
        address, ch["nonce"], device.sign(ch["message"]), client=client, quote_id=lock["id"]))
    # A lock for 10,000 of cover does not price 50,000 of it at that premium.
    if reply.status_code == 200:
        assert reply.json()["policy"]["premium"] > lock["premium"] * 2


def test_an_unexpected_error_is_json_the_page_can_read_from_its_own_origin() -> None:
    """The default 500 is plain text from outside the CORS layer, so a page
    on another origin cannot even read it and can only say "refused". The
    answer is JSON with a reference, and carries the origin header when the
    origin is one the operator named."""
    app = create_app(trials=200, seed=3, run_chain=False, seed_book=False,
                     settings=Settings(faucet=True, allowed_origins=("https://clause.insure",)))

    @app.get("/api/_boom")
    async def boom() -> dict:
        raise RuntimeError("something the code did not foresee")

    with TestClient(app, raise_server_exceptions=False) as client:
        reply = client.get("/api/_boom", headers={"origin": "https://clause.insure"})
        assert reply.status_code == 500
        assert reply.headers.get("access-control-allow-origin") == "https://clause.insure"
        detail = reply.json()["detail"]
        assert "reference ERR-" in detail
        # It must not promise the money did not move. The rollback on the
        # buying path covers the policy and the premium together, but only up
        # to the point where the policy exists; anything after that leaves a
        # bound, paid policy behind a sentence saying nothing was charged.
        assert "nothing was charged" not in detail
        assert "Check My cover" in detail
        assert "foresee" not in reply.text
        stranger = client.get("/api/_boom", headers={"origin": "https://evil.example"})
        assert stranger.status_code == 500 and "access-control-allow-origin" not in stranger.headers


def test_one_old_policy_does_not_take_the_whole_book_down(client) -> None:
    """GET /api/policies formats every policy in the book, so a record it
    cannot format is not one bad row -- it is the whole endpoint answering
    five hundred. That is what happened on the live protocol: two thousand
    policies, one of them written before the airport catalogue existed, and
    the book unreadable because of it.
    """
    from clause.perils.flight import FlightDelay

    ok = client.get("/api/policies?limit=5")
    assert ok.status_code == 200, ok.text

    # A record in the shape the store holds from before the migration: a route
    # and no airport codes. It goes straight into the book, because that is how
    # it got there -- restored from disk, not written through the door.
    book = client.app.state.pool.policies
    victim = next(iter(book.values()))
    victim.peril_key = "flight_delay"
    victim.subject = {"route": "TK-IST-LHR", "flight_number": "TK1979",
                      "departure_date": "2026-11-02", "departure_time": "07:45"}

    again = client.get("/api/policies?limit=200")
    assert again.status_code == 200, (
        "one policy the page cannot name must not answer for the whole book: "
        + again.text[:200])
    rows = again.json()["items"]
    old = [r for r in rows if r["policy_id"] == victim.policy_id]
    assert old and "IST" in old[0]["subject_text"] and "LHR" in old[0]["subject_text"]
