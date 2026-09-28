"""The property register: who proved a home is theirs, and what that allows.

The hole this closes is not at the edge. This cover pays on an index rather
than on a loss, so two policies on one flat pay twice for one earthquake and
nobody has to file a claim for it to happen. An indemnity policy is protected
from that by the loss itself — you cannot be paid twice for one roof — and a
parametric one has to write the rule down.
"""

from __future__ import annotations

import pytest

from clause.protocol.property import Register, key_for


FLAT = {"street": "Atakent Mah 223 Cadde", "number": "A2", "flat": "49",
        "postcode": "34307", "city": "Istanbul"}
NEIGHBOUR = {**FLAT, "flat": "50"}
BLOCK = {k: v for k, v in FLAT.items() if k != "flat"}
AT = {"latitude": 41.0, "longitude": 28.8}


def key(address, building="flat"):
    return key_for(address, country="TR", building=building, **AT)


class Fake:
    """A policy, as the register reads one off the book.

    It carries the property identifier and not the address, which is what a
    real policy carries: the address is kept off the record on purpose and the
    register does not put it back.
    """

    def __init__(self, holder, address, limit, peril="earthquake", policy_id="P1", open_=True):
        self.holder, self.limit, self.peril_key = holder, limit, peril
        self.policy_id, self.is_open = policy_id, open_
        self.subject = dict(AT)
        place = key(address)
        self.metadata = {"property": {"id": place.property_id, "unit": place.unit_level}}


# ---------------------------------------------------------------------------
# What counts as one property
# ---------------------------------------------------------------------------


def test_one_flat_spelled_two_ways_is_one_property() -> None:
    """A register that made "Atatürk Cad." and "ATATURK CAD" two properties
    would enforce none of its rules."""
    other = {"street": "ATAKENT MAH 223 CADDE", "number": "a2", "flat": "49",
             "postcode": "34307", "city": "İstanbul"}
    assert key(FLAT).property_id == key(other).property_id


def test_two_flats_in_one_block_are_two_properties() -> None:
    assert key(FLAT).property_id != key(NEIGHBOUR).property_id


def test_an_address_with_no_flat_is_the_building_and_not_a_home_in_it() -> None:
    """The trap this avoids: treating a block's address as one person's home
    would lock out every neighbour who gave the same street and number."""
    assert key(FLAT).unit_level is True
    assert key(BLOCK).unit_level is False


def test_an_address_too_thin_to_identify_anything_has_no_key() -> None:
    assert key_for({"city": "Istanbul"}, country="TR") is None
    assert key_for(None, country="TR") is None


# ---------------------------------------------------------------------------
# The three rules
# ---------------------------------------------------------------------------


def test_a_second_cover_on_the_same_home_for_the_same_peril_is_refused() -> None:
    register = Register()
    register.reconcile([Fake("holder-a", FLAT, 50_000, policy_id="CLS-FIRST")])
    allowed, why = register.may_write(key(FLAT), "holder-a", peril="earthquake",
                                      limit=50_000, declared=200_000)
    assert not allowed
    assert "CLS-FIRST" in why[0] and "pay twice" in why[0]


def test_a_second_peril_on_the_same_home_is_not_a_second_cover() -> None:
    """An earthquake policy and a storm policy on one flat are two covers
    against two different things, which is ordinary and right — as long as
    they come to no more than the flat between them."""
    register = Register()
    register.reconcile([Fake("holder-a", FLAT, 50_000)])
    allowed, why = register.may_write(key(FLAT), "holder-a", peril="storm",
                                      limit=50_000, declared=200_000)
    assert allowed, why


def test_two_perils_together_still_cannot_pass_what_is_at_risk() -> None:
    """A sum insured is a sum insured. Forty thousand of earthquake beside
    forty thousand of storm is eighty thousand on a fifty thousand flat,
    whichever of the two arrives."""
    register = Register()
    register.reconcile([Fake("holder-a", FLAT, 40_000, peril="earthquake")])
    allowed, why = register.may_write(key(FLAT), "holder-a", peril="storm",
                                      limit=40_000, declared=50_000)
    assert not allowed
    assert "more than the 50,000 you have at risk" in why[0]


def test_a_neighbour_is_not_stopped_by_the_flat_next_door() -> None:
    register = Register()
    register.reconcile([Fake("holder-a", FLAT, 50_000)])
    allowed, why = register.may_write(key(NEIGHBOUR), "holder-b", peril="earthquake",
                                      limit=50_000, declared=200_000)
    assert allowed, why


def test_everybody_together_cannot_insure_it_for_more_than_it_is_worth() -> None:
    """Rule (b): a landlord and a tenant hold different interests in one flat
    and both may insure it, but not for two whole flats between them."""
    register = Register()
    register.reconcile([Fake("landlord", FLAT, 90_000)])
    allowed, why = register.may_write(key(FLAT), "tenant", peril="storm",
                                      limit=40_000, declared=100_000,
                                      property_value=100_000)
    assert not allowed
    assert "more than it is worth" in why[-1]


# ---------------------------------------------------------------------------
# What verification binds
# ---------------------------------------------------------------------------


def test_a_proved_home_is_not_another_address_to_insure() -> None:
    register = Register()
    register.verify(key(FLAT), "holder-a", value_at_risk=200_000, by="specimen-tr-one")
    register.reconcile([])
    allowed, why = register.may_write(key(FLAT), "stranger", peril="earthquake",
                                      limit=10_000, declared=200_000)
    assert not allowed
    assert "belong to somebody else" in why[0]


def test_a_block_is_never_exclusive() -> None:
    """Somebody who gave no flat number has proved a building, not a home in
    it, and a neighbour must not be locked out by that."""
    register = Register()
    register.verify(key(BLOCK), "holder-a", value_at_risk=200_000, by="specimen-tr-one")
    register.reconcile([])
    allowed, why = register.may_write(key(BLOCK), "holder-b", peril="earthquake",
                                      limit=10_000, declared=200_000)
    assert allowed, why


def test_what_was_proved_caps_what_can_be_claimed_later() -> None:
    """Rule (c) is only worth something if the number was checked. A holder
    who proved a flat worth 60,000 cannot come back and declare 500,000."""
    register = Register()
    register.verify(key(FLAT), "holder-a", value_at_risk=60_000, by="specimen-tr-one")
    register.reconcile([])
    allowed, why = register.may_write(key(FLAT), "holder-a", peril="earthquake",
                                      limit=100_000, declared=500_000)
    assert not allowed
    assert "60,000" in why[0]


def test_the_holding_says_who_accepted_it_and_how() -> None:
    register = Register()
    held = register.verify(key(FLAT), "holder-a", value_at_risk=60_000,
                           by="specimen-tr-one", application_id="APP-1", country="tr")
    assert held.verified_by == "specimen-tr-one" and held.application_id == "APP-1"
    assert held.country == "TR" and held.by_register is False
    assert register.holding(key(FLAT).property_id, "holder-a") is held
    assert [h.holder for h in register.holders_of(key(FLAT).property_id)] == ["holder-a"]


def test_the_book_is_read_by_identifier_and_never_by_address() -> None:
    """The address is kept off the policy record on purpose — only a
    fingerprint of it is there — and closing this hole must not put it back.
    A policy written before the identifier existed names no property; it is
    not counted, and it cannot make the register wrong about the ones that do.
    """
    class Older:
        holder, limit, peril_key, policy_id, is_open = "holder-a", 50_000, "earthquake", "CLS-OLD", True
        subject = dict(AT)
        metadata = {"interest": {"country": "TR"}, "address_hash": "deadbeef"}

    register = Register()
    register.reconcile([Older()])
    assert register.in_force == []
    allowed, _ = register.may_write(key(FLAT), "holder-a", peril="earthquake",
                                    limit=50_000, declared=200_000)
    assert allowed


# ---------------------------------------------------------------------------
# Through the door a buyer actually uses
# ---------------------------------------------------------------------------


ADDRESS = {"street": "Atakent Mah 223 Cadde", "number": "A2", "flat": "49",
           "postcode": "34307", "city": "Istanbul"}
HOME = {"kind": "home", "building": "flat", "area_m2": 120, "built": 2010}
WHERE = {"location": "IST-KADIKOY", "radius_km": 50, "built": 2010}


def buy(client, device, address, *, limit=50_000, at=ADDRESS, peril="earthquake", risk=60_000):
    from test_api_security import statements

    terms = {"peril": peril, "limit": float(limit), "term_days": 365.0, "subject": WHERE,
             "country": "TR", "value_at_risk": float(risk), "size": HOME}
    challenge = client.post("/api/auth/challenge", json={
        "address": address, "purpose": "buy", "terms": terms}).json()
    return client.post("/api/policies", json={
        "peril": peril, "subject": WHERE, "limit": limit, "term_days": 365, "holder": address,
        "nonce": challenge["nonce"], "signature": device.sign(challenge["message"]),
        "interest": {"what": "evim", "country": "TR", "inside_trigger_area": True,
                     "value_at_risk": risk, "size": HOME, "address": at},
        "settlement": "fiat",
        "attestations": statements(client, address, "sanctions_clear", "identity_basic")})


@pytest.fixture()
def buying():
    from fastapi.testclient import TestClient

    from clause.api.app import Settings, create_app

    app = create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token="devtoken"))
    with TestClient(app) as client:
        yield client, app


def joins(client):
    from test_api_security import Device

    device = Device()
    address = client.post("/api/auth/register",
                          json={"public_key": device.public}).json()["address"]
    return device, address


def test_the_rules_hold_at_the_door_a_buyer_uses(buying) -> None:
    """The register is only worth what it stops, and it has to stop it at
    every door: a deployment that writes home cover directly and one that
    applies for it are two ways in, and a rule enforced on one is not
    enforced."""
    client, app = buying
    device, me = joins(client)
    assert buy(client, device, me).status_code == 200

    again = buy(client, device, me)
    assert again.status_code == 409
    assert "pay twice for one event" in again.json()["detail"]

    other, stranger = joins(client)
    theirs = buy(client, other, stranger, limit=20_000)
    assert theirs.status_code == 409
    assert "more than it is worth" in theirs.json()["detail"]

    # The flat next door is a different property and is not caught by any of it.
    assert buy(client, other, stranger, limit=20_000,
               at={**ADDRESS, "flat": "50"}).status_code == 200


def test_the_policy_carries_the_property_and_not_the_address(buying) -> None:
    """Closing this hole must not undo the reason the address is kept off the
    record in the first place."""
    client, app = buying
    device, me = joins(client)
    written = buy(client, device, me)
    assert written.status_code == 200
    policy = app.state.pool.policies[written.json()["policy"]["policy_id"]]
    assert policy.metadata["property"]["id"].startswith("PRP-")

    # Structurally, not by substring. This used to flatten the record to a
    # string and look for "A2" in it, and the record carries hashes and a
    # PRP- id: two characters of uppercase hex turn up in one sooner or later,
    # so the test failed on the luck of the run rather than on a leaked
    # address. What it is actually asserting is that no field of an address
    # rode along, which is worth saying exactly.
    ADDRESS_FIELDS = {"street", "number", "flat", "postcode", "post_code",
                      "city", "district", "province", "address", "line1", "line2"}

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in ADDRESS_FIELDS or not value, (
                    f"the address must not be on the policy record: "
                    f"{path}.{key} = {value!r}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(policy.metadata)
    # And the distinctive parts, which are long enough not to collide with an
    # id, are not anywhere in it either.
    flat = str(policy.metadata)
    for part in ("Atakent", "34307"):
        assert part not in flat, "the address must not be on the policy record"
