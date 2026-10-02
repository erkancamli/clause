"""Signing out ends the session, rather than forgetting it in one tab.

clause/protocol/auth.py describes the model: a session token is a signed
claim, checked without a lookup, which is what makes it cheap. The cost was
that nothing could end one. Signing out dropped the token from the tab and
left it valid for the rest of its thirty minutes, and DELETE
/api/operator/session closed only operator sessions:

    DELETE /api/operator/session with the buyer's token -> 200 {"signed_out": true}
    the buyer's token still works: 200

So somebody with reason to think a token had got out had no way to act on
the thought. ASVS V3.3.1 and V3.3.4.

Two records close it, both bounded by the session's own length: the digests
of tokens handed back, and, for signing out everywhere, the moment it was
asked, read against the issue time the expiry carries. Neither can be used
as a session, and both are forgotten when what they end would have expired.

The session id in the token came out of this. Without it the token is a pure
function of the address and the expiry, so two tabs signing in within one
second held the same token: ending one ended the other, and signing out and
straight back in handed back a token that had already been given up and was
refused for the rest of its half hour. Measured: 401 on every read after a
sign out and a fresh sign in.
"""

from __future__ import annotations

import time

import pytest

from clause.protocol.auth import (SESSION_SECONDS, AuthError, Authenticator,
                                  session_digest)


@pytest.fixture
def auth() -> Authenticator:
    return Authenticator(secret=b"a" * 32)


ADDRESS = "CLSsomebodysaddress"


def test_a_session_ends_when_it_is_given_back(auth) -> None:
    token = auth.issue_session(ADDRESS)["token"]
    assert auth.session_address(token) == ADDRESS
    assert auth.end_session(token) is True
    with pytest.raises(AuthError, match="session ended"):
        auth.session_address(token)


def test_two_sessions_are_two_sessions(auth) -> None:
    """Which they were not: one second, one address, one token."""
    first = auth.issue_session(ADDRESS)["token"]
    second = auth.issue_session(ADDRESS)["token"]
    assert first != second
    auth.end_session(first)
    assert auth.session_address(second) == ADDRESS


def test_signing_out_and_straight_back_in_works(auth) -> None:
    """The failure the session id was added for, at the same moment in time."""
    now = time.time()
    first = auth.issue_session(ADDRESS, now=now)["token"]
    auth.end_session(first, now=now)
    again = auth.issue_session(ADDRESS, now=now)["token"]
    assert auth.session_address(again, now=now) == ADDRESS


def test_signing_out_everywhere_ends_the_ones_never_seen(auth) -> None:
    held = [auth.issue_session(ADDRESS)["token"] for _ in range(3)]
    auth.end_sessions(ADDRESS)
    for token in held:
        with pytest.raises(AuthError, match="session ended"):
            auth.session_address(token)


def test_it_ends_nobody_elses(auth) -> None:
    mine = auth.issue_session(ADDRESS)["token"]
    theirs = auth.issue_session("CLSsomebodyelse")["token"]
    auth.end_sessions(ADDRESS)
    auth.end_session(mine)
    assert auth.session_address(theirs) == "CLSsomebodyelse"


def test_a_session_issued_after_signing_out_everywhere_still_works(auth) -> None:
    """Otherwise the address could never sign in again."""
    now = time.time()
    auth.end_sessions(ADDRESS, now=now)
    later = auth.issue_session(ADDRESS, now=now + 2)["token"]
    assert auth.session_address(later, now=now + 2) == ADDRESS


def test_what_is_written_down_cannot_be_used_as_a_session(auth) -> None:
    token = auth.issue_session(ADDRESS)["token"]
    auth.end_session(token)
    digest = session_digest(token)
    assert digest in auth._given_up
    assert token not in auth._given_up
    with pytest.raises(AuthError):
        auth.session_address(digest)


def test_both_records_are_forgotten_when_they_stop_mattering(auth) -> None:
    now = time.time()
    token = auth.issue_session(ADDRESS, now=now)["token"]
    auth.end_session(token, now=now)
    auth.end_sessions("CLSsomebodyelse", now=now)
    assert auth._given_up and auth._signed_out_at
    auth.forget_ended_sessions(now=now + SESSION_SECONDS + 2)
    assert not auth._given_up, "a digest kept past the token's own expiry"
    assert not auth._signed_out_at


def test_giving_back_something_that_is_not_a_session_changes_nothing(auth) -> None:
    for rubbish in ("", "x", "a.b.c.d", "CLS.1.2.3"):
        assert auth.end_session(rubbish) is False
    assert not auth._given_up


def test_an_expired_session_cannot_be_given_back(auth) -> None:
    now = time.time()
    token = auth.issue_session(ADDRESS, now=now - SESSION_SECONDS - 10)["token"]
    assert auth.end_session(token, now=now) is False


# -- through the API, and across a restart ---------------------------------

def test_the_route_ends_this_session_and_optionally_the_rest() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fastapi.testclient import TestClient

    from clause.api.app import create_app
    from clause.api.security import Settings
    from test_api_security import Device, session_for

    app = create_app(trials=50, seed=3, run_chain=False, seed_book=False,
                     settings=Settings(faucet=True))
    with TestClient(app) as client:
        device = Device()
        address = client.post("/api/auth/register",
                              json={"public_key": device.public}).json()["address"]
        first = session_for(client, device, address)
        second = session_for(client, device, address)
        head = lambda token: {"Authorization": f"Bearer {token}"}

        assert client.get("/api/wallet", headers=head(first)).status_code == 200
        assert client.get("/api/wallet", headers=head(second)).status_code == 200

        said = client.delete("/api/auth/session", headers=head(first))
        assert said.status_code == 200 and said.json()["signed_out"] is True
        assert client.get("/api/wallet", headers=head(first)).status_code == 401
        assert client.get("/api/wallet", headers=head(second)).status_code == 200, (
            "ending one session ended another")

        third = session_for(client, device, address)
        said = client.delete("/api/auth/session?everywhere=true", headers=head(third))
        assert said.json() == {"signed_out": True, "everywhere": True}
        assert client.get("/api/wallet", headers=head(second)).status_code == 401
        assert client.get("/api/wallet", headers=head(third)).status_code == 401

        # And it is somebody's own session or nothing.
        assert client.delete("/api/auth/session").status_code == 401
        assert client.delete("/api/auth/session",
                             headers=head("not.a.session.at.all")).json()["signed_out"] is False


def test_the_page_tells_the_protocol_when_it_signs_out() -> None:
    """A token only forgotten by the tab is still a token."""
    from pathlib import Path

    identity = (Path(__file__).resolve().parent.parent / "site" / "app"
                / "25-identity.js").read_text(encoding="utf-8")
    at = identity.index("function signOut(")
    said = identity[at:identity.index("\n}", at)]
    assert '"/api/auth/session"' in said
    assert 'method:"DELETE"' in said
    at = identity.index("function forgetDevice(")
    forgotten = identity[at:identity.index("\n}", at)]
    assert "everywhere=true" in forgotten, (
        "forgetting the device is the strongest of the three")


def test_a_restart_does_not_bring_an_ended_session_back() -> None:
    """The secret survives a restart, so the tokens it signed would too."""
    from clause.protocol.auth import Authenticator

    first = Authenticator(secret=b"b" * 32)
    token = first.issue_session(ADDRESS)["token"]
    first.end_session(token)
    first.end_sessions("CLSsomebodyelse")

    after = Authenticator(secret=b"b" * 32)
    assert after.session_address(token) == ADDRESS, "the same secret, so the same tokens"
    # What the book carries across, as clause/store.py writes and reads it.
    after._given_up.update(first._given_up)
    after._signed_out_at.update(first._signed_out_at)
    with pytest.raises(AuthError, match="session ended"):
        after.session_address(token)
