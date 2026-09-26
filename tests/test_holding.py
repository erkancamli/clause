"""A price promised for ten minutes, and what a restart used to do to it.

The promise is on the screen in words: this price is yours for ten minutes. It
was held in a dictionary in the process, so the promise was only as durable as
the process — and replacing the service is something an operator does on
purpose, in the afternoon, while somebody is part way through buying. That buyer
pressed the button and was told the price had moved.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from clause.api import holding
from clause.protocol.auth import Authenticator
from clause.pricing import Quote


WHERE = {"latitude": 41.0, "longitude": 28.8, "radius_km": 50.0}
SECRET = b"a-key-that-outlives-the-process"


def a_quote(premium: float = 6203.15) -> Quote:
    return Quote(peril_key="earthquake", limit=50_000.0, term_days=365.0,
                 expected_loss=1105.9, risk_load=5008.77, expense_load=88.47,
                 premium=premium, trigger_probability=0.056621, expected_share=0.022118,
                 marginal_capital=41768.35, standalone_capital=48882.92,
                 diversification="standalone", diversification_ratio=0.8545,
                 notes=["the fault beneath the circle"], risk_basis="capital",
                 capital_cost=5008.77)


def build(*, peril_key: str, limit: float, term_days: float,
          diversification: str, risk_basis: str, **numbers: float) -> Quote:
    return Quote(peril_key=peril_key, limit=limit, term_days=term_days, notes=[],
                 diversification=diversification, risk_basis=risk_basis, **numbers)


def promise(quoted=None, **over):
    terms = {"peril": "earthquake", "subject": WHERE, "limit": 50_000.0, "term_days": 365.0}
    terms.update(over)
    return holding.issue(SECRET, quoted=quoted or a_quote(), **terms)


def honoured(token, *, secret=SECRET, now=None, **over):
    terms = {"peril": "earthquake", "subject": WHERE, "limit": 50_000.0, "term_days": 365.0}
    terms.update(over)
    return holding.honoured(secret, token, build=build, now=now, **terms)


# ---------------------------------------------------------------------------
# What the promise is worth
# ---------------------------------------------------------------------------


def test_the_price_comes_back_whole() -> None:
    """Not just the premium: the pool reads five figures off a locked quote when
    it writes the policy, and a policy built from four of them and a guess is
    not the policy that was priced."""
    back = honoured(promise()["id"])
    assert back is not None
    original = a_quote()
    for field in ("premium", "expected_loss", "risk_load", "expense_load", "marginal_capital"):
        assert getattr(back, field) == pytest.approx(getattr(original, field))


def test_nothing_is_stored_so_a_restart_cannot_lose_it() -> None:
    """The whole point. Nothing but the key is shared between the process that
    promised and the one that honours."""
    token = promise()["id"]
    # A different process: no dictionary, nothing in common but the key.
    assert honoured(token) is not None


def test_the_promise_is_for_the_cover_it_was_made_about() -> None:
    token = promise()["id"]
    assert honoured(token, limit=60_000.0) is None
    assert honoured(token, term_days=180.0) is None
    assert honoured(token, peril="storm") is None
    assert honoured(token, subject={**WHERE, "radius_km": 100.0}) is None


def test_ten_minutes_is_ten_minutes() -> None:
    made = promise()
    token = made["id"]
    assert honoured(token, now=made["expires_at"] - 1) is not None
    assert honoured(token, now=made["expires_at"] + 1) is None


def test_a_promise_nobody_made_is_not_honoured() -> None:
    token = promise()["id"]
    assert honoured(token, secret=b"another service") is None
    # Tampered: the price raised inside the payload, the signature left alone.
    prefix, payload, tag = token.split(".", 2)
    assert honoured(prefix + "." + payload[:-4] + "AAAA" + "." + tag) is None
    assert honoured("PQ1.nonsense.nonsense") is None
    assert honoured("PQ-0123456789abcdef") is None
    assert honoured("") is None
    assert honoured(None) is None


def test_an_older_shape_is_refused_rather_than_misread() -> None:
    """A token's first field is the shape it is in. A later shape gets a
    different prefix, and this one must not try to read it."""
    assert holding.PREFIX == "PQ1"
    made = promise()["id"]
    assert honoured(made.replace("PQ1.", "PQ2.", 1)) is None


def test_the_identifier_fits_what_the_request_may_carry() -> None:
    """It travels in a request body field with a length limit, and a promise
    longer than the limit is refused as malformed rather than honoured."""
    from clause.api.app import BuyRequest

    field = BuyRequest.model_fields["quote_id"]
    longest = max(getattr(m, "max_length", 0) or 0 for m in field.metadata)
    assert len(promise()["id"]) < longest


# ---------------------------------------------------------------------------
# The key it is signed with
# ---------------------------------------------------------------------------


def test_the_key_comes_from_the_one_secret_that_outlives_a_restart() -> None:
    """There is no second secret. The store already keeps the authenticator's
    own and puts it back, which is what makes a ten minute promise survive the
    service being replaced; a key arranged separately would not have been
    arranged to be kept."""
    root = Authenticator(secret=b"the-root")
    same = Authenticator(secret=b"the-root")
    assert root.derived("price-lock/v1") == same.derived("price-lock/v1")
    assert Authenticator(secret=b"another").derived("price-lock/v1") != root.derived("price-lock/v1")


def test_a_key_for_one_purpose_does_not_verify_another_purpose() -> None:
    """Derived, not reused: a weakness in either must not be carried across."""
    root = Authenticator(secret=b"the-root")
    assert root.derived("price-lock/v1") != root.derived("session")
    token = holding.issue(root.derived("price-lock/v1"), peril="earthquake", subject=WHERE,
                          limit=50_000.0, term_days=365.0, quoted=a_quote())["id"]
    assert honoured(token, secret=root.derived("session")) is None
    assert honoured(token, secret=root.derived("price-lock/v1")) is not None


# ---------------------------------------------------------------------------
# Through the door a buyer uses, across a restart
# ---------------------------------------------------------------------------


HOME = {"kind": "home", "building": "flat", "area_m2": 120, "built": 2010}
PLACE = {"location": "IST-KADIKOY", "radius_km": 50}


def a_service(directory):
    """A service whose store is where a deployment cannot reach it: the state
    directory lives outside the release the deployment swaps."""
    from fastapi.testclient import TestClient

    from clause.api.app import Settings, create_app

    os.environ["CLAUSE_STATE_DIR"] = str(directory)
    return create_app(trials=400, seed=11, run_chain=False, seed_book=True,
                      settings=Settings(faucet=True)), TestClient


def test_a_price_promised_before_a_restart_is_still_the_price_after_it() -> None:
    """The promise is made in writing on the screen: ten minutes, whatever the
    book does. Replacing the service used to break it, and the buyer who had
    read the price and pressed the button was told it had moved.

    The promise carries a price the pool would not give now, because it has to.
    A fresh service on the same seed prices identically, so a test that promised
    the live price and then compared two numbers passed whether or not the
    promise was honoured. It was written that way first, and it did: breaking
    the token reader on purpose left it green.

    Here the promised price is below the pool's own, so there are two outcomes
    and they cannot be confused. Honoured, the policy costs what was promised.
    Not honoured, the pool prices again, finds more than the buyer agreed to,
    and refuses.
    """
    from test_repeat import body_for, joins

    before = os.environ.get("CLAUSE_STATE_DIR")
    with tempfile.TemporaryDirectory() as directory:
        try:
            terms = {"peril": "earthquake", "limit": 50_000.0, "term_days": 365.0,
                     "subject": PLACE, "country": "TR", "value_at_risk": 60_000.0,
                     "size": HOME}
            app, Client = a_service(directory)
            with Client(app) as client:
                quoted = client.post("/api/quote", json=terms)
                assert quoted.status_code == 200, quoted.text
                live = quoted.json()
                assert live["lock"]["id"].startswith(holding.PREFIX + ".")

            # The price as it stood when the buyer read it, which the book has
            # since moved away from. Signed with the key the first service used,
            # which the store kept and the second one will put back: that key is
            # the only thing the two processes share.
            was = a_quote(premium=round(live["premium"] * 0.8, 2))
            key = app.state.auth.derived("price-lock/v1")
            # Over the subject as the route reads it, not as the reply prints
            # it: the reply adds the place name for the screen, and hashing that
            # would promise a price for cover nobody asked about.
            from clause.api.app import clean_subject

            lock = holding.issue(key, peril="earthquake",
                                 subject=clean_subject(PLACE), limit=50_000.0,
                                 term_days=365.0, quoted=was)

            # The service is replaced: a new process, a new book, the same state
            # directory -- outside the release the deployment swapped.
            fresh, Client = a_service(directory)
            with Client(fresh) as client:
                device, me = joins(client)
                body = body_for(client, me, device, quote_id=lock["id"])
                # The price the buyer read, and no more.
                body["max_premium"] = lock["premium"]
                answer = client.post("/api/applications", json=body)
                assert answer.status_code == 200, answer.text
                assert answer.json()["application"]["premium"] == pytest.approx(
                    lock["premium"], abs=0.01), (
                    "the promised price must be the price after a restart")

                # And the same purchase without the promise is refused, which is
                # what the buyer used to get.
                plain = body_for(client, me, device)
                plain["max_premium"] = lock["premium"]
                assert client.post("/api/applications", json=plain).status_code == 409
        finally:
            if before is None:
                os.environ.pop("CLAUSE_STATE_DIR", None)
            else:
                os.environ["CLAUSE_STATE_DIR"] = before


def test_the_rebuilt_quote_is_a_price_for_the_cover_it_was_asked_about() -> None:
    """It used to come back claiming a limit of zero for no peril, which is not
    a price for anything. The cover is not in the token -- it is already checked
    against it -- but a quote that does not know what it is a price for is a
    quote waiting to be read by mistake."""
    back = honoured(promise()["id"])
    assert back.peril_key == "earthquake"
    assert back.limit == 50_000.0
    assert back.term_days == 365.0
    assert back.rate_on_line == pytest.approx(back.premium / 50_000.0)


def test_even_the_largest_cover_promise_fits_the_field_it_travels_in() -> None:
    """The identifier grew from eighteen characters to a few hundred, and it
    travels in a request field with a length limit. A promise that did not fit
    would be refused as malformed, which reads to the buyer as the price having
    moved — so the headroom is asserted rather than assumed."""
    from clause.api.app import BuyRequest, MAX_LIMIT

    field = BuyRequest.model_fields["quote_id"]
    longest = max(getattr(m, "max_length", 0) or 0 for m in field.metadata)
    wide = Quote(peril_key="earthquake", limit=float(MAX_LIMIT), term_days=3650.0,
                 expected_loss=123456789.123456, risk_load=987654321.654321,
                 expense_load=12345678.987654, premium=1111111111.111111,
                 trigger_probability=0.123456, expected_share=0.987654,
                 marginal_capital=999999999.999999, standalone_capital=888888888.888888,
                 diversification="standalone", diversification_ratio=0.123456,
                 notes=[], risk_basis="reinsurance", capital_cost=777777777.777777)
    biggest = holding.issue(SECRET, peril="earthquake",
                            subject={"latitude": 41.123456, "longitude": 28.987654,
                                     "radius_km": 250.0, "location": "IST-KADIKOY"},
                            limit=float(MAX_LIMIT), term_days=3650.0, quoted=wide)
    assert len(biggest["id"]) < longest
