"""The papers a buyer is given, and what makes the record worth anything.

This protocol asks for no name, no email address and no telephone number, so
it cannot send anybody anything. What it must still do is give them the
confirmation of their order, the terms they agreed to and the reminder of
their right to withdraw — and be able to show it did.

Each test here names a way such a record stops being evidence: a page that
can go missing, a moment that gets rewritten, or a file that opens for
somebody it does not belong to.
"""

from __future__ import annotations

import pytest

from clause.protocol.papers import KINDS, PaperError, Papers

MINE = "clause1qmine"
YOURS = "clause1qyours"


def test_a_paper_can_never_be_taken_out_or_rewritten() -> None:
    """A file that can quietly lose a page proves nothing about what was in
    it, so there is no way to remove one and no way to edit one."""
    book = Papers()
    for name in dir(book):
        assert not name.startswith(("remove", "delete", "drop", "purge", "edit", "amend")), \
            f"Papers.{name} would let the record be changed after the fact"
    given = book.give(MINE, "confirmation", "Your order", "text", now=1000.0)
    assert book.mine(MINE) == [given]
    # Writing more does not disturb what is already there.
    book.give(MINE, "terms", "The contract", "text", now=2000.0)
    assert [p.paper_id for p in book.mine(MINE)][-1] == given.paper_id
    assert book.papers[given.paper_id].given_at == 1000.0


def test_the_moment_it_was_first_opened_is_written_once() -> None:
    """When somebody first had it in front of them is the fact that matters;
    a later visit must not move it."""
    book = Papers()
    paper = book.give(MINE, "withdrawal", "Your right to withdraw", "text", now=1000.0)
    assert paper.opened_at == 0.0
    assert book.unread(MINE) == 1

    book.open(MINE, paper.paper_id, now=1500.0)
    assert book.papers[paper.paper_id].opened_at == 1500.0
    assert book.unread(MINE) == 0

    book.open(MINE, paper.paper_id, now=9999.0)
    assert book.papers[paper.paper_id].opened_at == 1500.0, "a second reading moved the first"


def test_a_paper_opens_for_its_own_address_and_nobody_else() -> None:
    book = Papers()
    mine = book.give(MINE, "confirmation", "Your order", "text")
    assert book.mine(YOURS) == []
    with pytest.raises(PaperError, match="no such paper"):
        book.open(YOURS, mine.paper_id)
    # Refused the same way as a paper that does not exist: whether somebody
    # else's paper is there is not a thing to tell them.
    with pytest.raises(PaperError, match="no such paper"):
        book.open(YOURS, "PAP-000000000000")
    assert book.papers[mine.paper_id].opened_at == 0.0, "the refusal marked it read"


def test_only_the_papers_the_law_asks_for_can_be_given() -> None:
    book = Papers()
    for kind in KINDS:
        assert book.give(MINE, kind, "t", "b").kind == kind
    with pytest.raises(PaperError, match="no such paper"):
        book.give(MINE, "advertisement", "Buy more cover", "text")
    with pytest.raises(PaperError, match="an address"):
        book.give("", "confirmation", "t", "b")


def test_the_papers_about_one_purchase_can_be_found_together() -> None:
    book = Papers()
    book.give(MINE, "confirmation", "Your order", "a", about="CLS-1", now=1.0)
    book.give(MINE, "terms", "The contract", "b", about="CLS-1", terms_hash="0xabc", now=2.0)
    book.give(MINE, "confirmation", "Another order", "c", about="CLS-2", now=3.0)
    assert [p.kind for p in book.about(MINE, "CLS-1")] == ["terms", "confirmation"]
    assert book.about(YOURS, "CLS-1") == []


def test_the_list_does_not_carry_the_text_of_every_paper() -> None:
    """The box is drawn from a list; the words are fetched when one is opened,
    which is also the moment worth writing down."""
    book = Papers()
    paper = book.give(MINE, "terms", "The contract", "a very long contract", terms_hash="0xabc")
    row = paper.summary()
    assert "body" not in row
    assert row["terms_hash"] == "0xabc" and row["opened_at"] is None
    assert paper.to_dict()["body"] == "a very long contract"


# -- through a real purchase ------------------------------------------------


def test_buying_cover_confirms_the_order_and_gives_the_right_to_withdraw() -> None:
    """There is no address to send anything to, so the giving happens here."""
    from fastapi.testclient import TestClient
    from clause.api.app import create_app
    from clause.api.security import Settings
    from test_api_security import Device, session_for, buy_body, buy_terms

    app = create_app(trials=200, run_chain=False, seed_book=True, settings=Settings(faucet=True))
    with TestClient(app) as client:
        device = Device()
        address = client.post("/api/auth/register", json={"public_key": device.public}).json()["address"]
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        assert client.get("/api/papers").status_code == 401
        assert client.get("/api/papers", headers=auth).json() == {"papers": [], "unread": 0}

        challenge = client.post("/api/auth/challenge", json={
            "address": address, "purpose": "buy", "terms": buy_terms()}).json()
        bought = client.post("/api/policies", json=buy_body(
            address, challenge["nonce"], device.sign(challenge["message"]), client=client))
        assert bought.status_code == 200, bought.text
        policy_id = bought.json()["policy"]["policy_id"]

        box = client.get("/api/papers", headers=auth).json()
        kinds = [p["kind"] for p in box["papers"]]
        assert "confirmation" in kinds, "the order was never confirmed"
        assert "withdrawal" in kinds, "nothing told them they could withdraw"
        # This purchase accepted no contract, so there is no copy of one to
        # keep. A paper saying otherwise would be a paper about nothing.
        assert "terms" not in kinds
        assert box["unread"] == len(box["papers"]) > 0
        assert all(p["about"] == policy_id for p in box["papers"])
        assert all("body" not in p for p in box["papers"])

        # Opening one writes down the moment, and only the first one.
        first = box["papers"][0]["paper_id"]
        opened = client.get(f"/api/papers/{first}", headers=auth).json()["paper"]
        assert opened["body"] and opened["opened_at"]
        again = client.get(f"/api/papers/{first}", headers=auth).json()["paper"]
        assert again["opened_at"] == opened["opened_at"]
        assert client.get("/api/papers", headers=auth).json()["unread"] == len(box["papers"]) - 1

        # Somebody else's box is empty and their paper does not open.
        other = Device()
        other_address = client.post("/api/auth/register", json={"public_key": other.public}).json()["address"]
        other_auth = {"authorization": f"Bearer {session_for(client, other, other_address)}"}
        assert client.get("/api/papers", headers=other_auth).json()["papers"] == []
        assert client.get(f"/api/papers/{first}", headers=other_auth).status_code == 404
