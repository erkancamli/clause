"""The right to withdraw as the distance selling rules shape it: counted
from the day the contract reached the buyer, a year when it never did,
the money back within thirty days of the notice, and the buyer's own copy
of the contract as the durable medium."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol import cancellation
from clause.protocol.policy import PolicyStatus
from test_api_security import buy_body, buy_terms, session_for
from test_commerce import TOKEN, register, signed_post
from test_desk import KADIKOY


def buy_with_contract(client, device, address, limit):
    """As the page buys: the contract read first, its hash signed into the terms."""
    interest = {"what": "a flat in Kadıköy", "country": "TR", "inside_trigger_area": True,
                "value_at_risk": 300_000, "size": {"kind": "home", "building": "flat", "area_m2": 100, "built": 2005}}
    preview = client.post("/api/contract", json={"peril": "earthquake", "subject": KADIKOY, "limit": limit, "term_days": 365,
                                                 "interest": interest, "settlement": "fiat", "holder": address})
    assert preview.status_code == 200, preview.text
    digest = preview.json()["hash"]
    terms = buy_terms(peril="earthquake", subject=KADIKOY, limit=float(limit), value_at_risk=300_000.0,
                      size=interest["size"], contract_hash=digest)
    challenge = client.post("/api/auth/challenge", json={"address": address, "purpose": "buy", "terms": terms}).json()
    reply = client.post("/api/policies", json=buy_body(address, challenge["nonce"], device.sign(challenge["message"]),
                                                       client=client, peril="earthquake", subject=KADIKOY,
                                                       limit=limit, interest=interest, contract_hash=digest))
    assert reply.status_code == 200, reply.text
    return reply.json()["policy"], preview.json()["text"]

DAY = 86400.0


class P:
    def __init__(self, *, bought_days_ago=1.0, term_days=365.0, country="TR", metadata=None):
        now = time.time()
        self.policy_id = "CLS-TEST"; self.peril_key = "earthquake"
        self.bought_at = now - bought_days_ago * DAY; self.starts_at = self.bought_at
        self.ends_at = self.bought_at + term_days * DAY; self.term_days = term_days
        self.premium = 100.0; self.status = PolicyStatus.ACTIVE
        self.metadata = {"interest": {"country": country}, **(metadata or {})}

    @property
    def is_open(self):
        return True


def test_the_days_run_from_the_day_the_contract_reached_the_buyer() -> None:
    read_first = P(metadata={"contract_hash": "abc"})
    right = cancellation.withdrawal(read_first)
    assert right["basis"] == "informed" and right["days"] == 14 and right["refund_within_days"] == 30
    assert abs(right["until"] - (read_first.bought_at + 14 * DAY)) < 1
    # Never given the document: a year, and the assessment says why.
    never = P(bought_days_ago=100)
    right = cancellation.withdrawal(never)
    assert right["basis"] == "not_informed" and right["days"] == 365 and right["open"]
    assessed = cancellation.assess(never)
    assert assessed["allowed"] and assessed["basis"] == "cooling_off" and "durable medium" in assessed["reason"]
    # Given it later, by downloading a copy: fourteen days from that day.
    later = P(bought_days_ago=100, metadata={"disclosure": {"kept_at": time.time() - 2 * DAY}})
    right = cancellation.withdrawal(later)
    assert right["basis"] == "informed" and abs(right["until"] - (time.time() + 12 * DAY)) < 5
    # Short cover has none, whatever was delivered.
    assert cancellation.withdrawal(P(term_days=2, metadata={"contract_hash": "abc"}))["basis"] == "short_cover"


def test_the_copy_the_buyer_downloads_is_noted_and_the_notice_is_recorded(tmp_path) -> None:
    app = create_app(trials=300, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, specimens=True),
                     store_path=tmp_path / "book.sqlite")
    with TestClient(app) as client:
        device, address = register(client)
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        policy, read = buy_with_contract(client, device, address, 20_000)
        pid = policy["policy_id"]
        assert policy["metadata"]["contract_hash"] and policy["metadata"]["disclosure"]["served_at"]
        terms = client.get(f"/api/policies/{pid}/cancellation", headers=auth).json()
        assert terms["withdrawal"]["basis"] == "informed" and terms["withdrawal"]["kept_at"] is None
        assert terms["allowed"] and terms["basis"] == "mistake"
        # The buyer takes their copy: an attachment, and the day is noted.
        copy = client.get(f"/api/policies/{pid}/contract", params={"download": "1"}, headers=auth)
        assert copy.status_code == 200 and "attachment" in copy.headers.get("content-disposition", "")
        assert "durable medium" in copy.text and "within 30 days" in copy.text
        assert copy.text == read                                  # the very text the buyer accepted
        assert "contract" not in client.get(f"/api/policies/{pid}").json()["policy"]["metadata"]   # not public
        kept = client.get(f"/api/policies/{pid}/cancellation", headers=auth).json()["withdrawal"]["kept_at"]
        assert kept and time.time() - kept < 5
        # A stranger gets nothing.
        assert client.get(f"/api/policies/{pid}/contract").status_code == 404
        # Cancelling records the notice, the refund and when it was due and paid.
        reply = signed_post(client, device, address, "cancel", {"policy_id": pid},
                            f"/api/policies/{pid}/cancel", {"account": address})
        assert reply.status_code == 200, reply.text
        note = reply.json()["withdrawal"]
        assert note["refund"] > 0 and note["refunded_at"] <= note["refund_due_by"]
        assert abs(note["refund_due_by"] - note["notified_at"] - 30 * DAY) < 1
        assert client.get(f"/api/policies/{pid}/cancellation", headers=auth).json()["withdrawn"]["basis"] == "mistake"
