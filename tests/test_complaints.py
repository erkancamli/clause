"""Complaints: raised on the policy, answered by the company on a clock,
and taken to the ombudsman with everything in one file when they are not."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol import complaints as cm
from test_api_security import session_for
from test_commerce import TOKEN, register
from test_desk import buy_quake

DAY = 86400.0
OP = {"x-operator-token": TOKEN}


class P:
    def __init__(self, pid="CLS-1", country="TR", carrier="c1"):
        self.policy_id = pid; self.holder = "holder-a"
        self.metadata = {"interest": {"country": country}, "carrier": carrier}


def test_the_clock_the_answer_and_the_way_to_the_ombudsman() -> None:
    book = cm.Complaints()
    t0 = 1_800_000_000.0
    c = book.open(P(), subject="settlement", text="The reading was 6.1 and nothing was paid.", now=t0)
    assert c.deadline_at == t0 + 15 * DAY and c.status == "open" and cm.route_for("TR").body == "Sigorta Tahkim Komisyonu"
    with pytest.raises(cm.ComplaintError):
        book.open(P(), subject="payment", text="A second one on the same policy.", now=t0)   # one at a time
    with pytest.raises(cm.ComplaintError):
        book.escalate(c.complaint_id, now=t0 + DAY)                                          # not yet
    # The holder writes again: the clock runs on. The company answers: it stops.
    book.reply(c.complaint_id, who="holder", text="Any news?", now=t0 + 2 * DAY)
    assert c.status == "open"
    book.reply(c.complaint_id, who="company", text="We read 5.9 at the station; see the proof page.", now=t0 + 3 * DAY)
    assert c.status == "answered" and c.answered_at == t0 + 3 * DAY and not c.overdue(t0 + 20 * DAY)
    # Not settled: to the ombudsman.
    book.escalate(c.complaint_id, now=t0 + 4 * DAY)
    assert c.status == "escalated" and c.messages[-1]["text"].startswith("taken to Sigorta")
    # Silence for fifteen days is overdue, and enough on its own.
    d = book.open(P(pid="CLS-2"), subject="payment", text="Decided on the 3rd, nothing arrived.", now=t0)
    assert d.overdue(t0 + 16 * DAY) and d.to_dict(t0 + 16 * DAY)["can_escalate"]
    book.escalate(d.complaint_id, now=t0 + 16 * DAY)
    # Closed by the company, with a resolution; nothing more can be written on it.
    e = book.open(P(pid="CLS-3"), subject="service", text="Nobody answered my email for a week.", now=t0)
    book.close(e.complaint_id, by="company", resolution="apologised and paid a goodwill sum", now=t0 + DAY)
    with pytest.raises(cm.ComplaintError):
        book.reply(e.complaint_id, who="holder", text="Thanks.", now=t0 + 2 * DAY)
    s = book.summary(book.for_carrier("c1"), now=t0 + 16 * DAY)
    assert s == {"total": 3, "open": 0, "overdue": 0, "due_soon": 0, "answered": 0, "escalated": 2, "closed": 1}
    # Elsewhere the route differs; unknown places get the protocol's own rule.
    assert cm.route_for("GB").answer_days == 56 and cm.route_for("XX").answer_days == 15


def test_a_complaint_runs_from_the_policy_to_the_file_for_tahkim(tmp_path) -> None:
    app = create_app(trials=300, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, specimens=True),
                     store_path=tmp_path / "book.sqlite")
    with TestClient(app) as client:
        device, address = register(client)
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        policy = buy_quake(client, device, address, 20_000)
        pid, carrier_id = policy["policy_id"], policy["metadata"]["carrier"]
        # Too short a complaint is refused; a real one opens the thread with the clock.
        assert client.post(f"/api/policies/{pid}/complaints", headers=auth, json={"subject": "settlement", "text": "bad"}).status_code == 422
        opened = client.post(f"/api/policies/{pid}/complaints", headers=auth,
                             json={"subject": "settlement", "text": "The shaking here was intensity VII and nothing was paid."})
        assert opened.status_code == 200, opened.text
        c = opened.json()["complaint"]
        assert c["status"] == "open" and 14 < c["days_left"] <= 15 and c["route"]["body"] == "Sigorta Tahkim Komisyonu"
        assert any("sigortatahkim" in l["url"] for l in c["route"]["links"]) and c["carrier"]
        cid = c["complaint_id"]
        # A stranger sees nothing; the holder sees their list.
        stranger, s_addr = register(client)
        s_auth = {"authorization": f"Bearer {session_for(client, stranger, s_addr)}"}
        assert client.get(f"/api/complaints/{cid}", headers=s_auth).status_code == 404
        assert client.post(f"/api/policies/{pid}/complaints", headers=s_auth, json={"subject": "other", "text": "not my policy at all"}).status_code == 404
        assert [x["complaint_id"] for x in client.get("/api/complaints", headers=auth).json()["complaints"]] == [cid]
        # Not yet for the ombudsman: the company's time has not run out.
        assert client.post(f"/api/complaints/{cid}/escalate", headers=auth, json={}).status_code == 409
        # The company takes its desk and answers; its first message stops the clock.
        desk_device, desk_addr = register(client)
        desk = {"authorization": f"Bearer {session_for(client, desk_device, desk_addr)}"}
        assert client.post("/api/company/specimen", json={"carrier_id": carrier_id}, headers=desk).status_code == 200
        mine = client.get("/api/company/complaints", params={"carrier_id": carrier_id}, headers=desk).json()
        assert mine["summary"]["open"] == 1 and mine["complaints"][0]["complaint_id"] == cid
        answered = client.post(f"/api/complaints/{cid}/messages", headers=desk, json={"text": "The station read intensity V; the proof page shows the rounds."})
        assert answered.status_code == 200 and answered.json()["complaint"]["status"] == "answered"
        assert answered.json()["complaint"]["messages"][-1]["who"] == "company"
        # The holder is not satisfied and takes it on: the file comes with it.
        taken = client.post(f"/api/complaints/{cid}/escalate", headers=auth, json={})
        assert taken.status_code == 200, taken.text
        package = taken.json()["package"]
        assert package["policy"]["policy_id"] == pid and package["insurer"]["carrier_id"] == carrier_id
        assert package["route"]["answer_days"] == 15 and [m["who"] for m in package["complaint"]["messages"]] == ["holder", "company", "holder"]
        text = client.get(f"/api/complaints/{cid}/package", params={"format": "text"}, headers=auth)
        assert text.status_code == 200 and "attachment" in text.headers["content-disposition"]
        assert "COMPLAINT FILE" in text.text and pid in text.text and "sigortatahkim.org" in text.text
        # The company and the operator can read the file too; the holder cannot close.
        assert client.get(f"/api/complaints/{cid}/package", headers=desk).status_code == 200
        assert client.get(f"/api/complaints/{cid}/package", headers=OP).status_code == 200
        assert client.post(f"/api/complaints/{cid}/close", headers=auth, json={"resolution": "x"}).status_code == 409
        closed = client.post(f"/api/complaints/{cid}/close", headers=OP, json={"resolution": "paid in full after the hearing"})
        assert closed.status_code == 200 and closed.json()["complaint"]["status"] == "closed"
        everything = client.get("/api/operator/complaints", headers=OP).json()
        assert everything["summary"]["closed"] == 1
    # It survives a restart.
    with TestClient(create_app(trials=300, seed=11, run_chain=False, seed_book=True,
                               settings=Settings(faucet=True, operator_token=TOKEN, specimens=True),
                               store_path=tmp_path / "book.sqlite")) as client:
        assert client.get("/api/operator/complaints", headers=OP).json()["complaints"][0]["status"] == "closed"
