"""Payouts leaving the protocol for a bank account or a mobile wallet."""

from __future__ import annotations

import json

import pytest

from clause.pricing import PricingEngine
from clause.protocol import Pool, Wallets
from clause.protocol.payouts import (
    HttpRail,
    PayoutError,
    Payouts,
    clean_iban,
)

# A structurally valid IBAN (it passes the mod 97 check) built for tests.
TR_IBAN = "TR330006100519786457841326"


def book():
    wallets = Wallets(demo_balance=0.0)
    pool = Pool(engine=PricingEngine(trials=500, seed=2), wallets=wallets)
    wallets.connect("lp", fund=False)
    wallets.credit("lp", 5_000_000, "seed", kind="faucet")
    pool.deposit("lp", 5_000_000)
    wallets.connect("holder", fund=False)
    wallets.credit("holder", 10_000, "seed", kind="faucet")
    payouts = Payouts(wallets)
    pool.listeners.append(payouts.route)
    return wallets, pool, payouts


def quake(pool: Pool):
    return pool.write(peril_key="earthquake",
                      subject={"location": "IST-KADIKOY", "radius_km": 50},
                      limit=40_000, term_days=365, holder="holder")


def test_ibans_are_checked_not_trusted() -> None:
    assert clean_iban("tr33 0006 1005 1978 6457 8413 26") == TR_IBAN
    with pytest.raises(PayoutError, match="does not check out"):
        clean_iban(TR_IBAN[:-1] + "7")
    with pytest.raises(PayoutError, match="26 characters"):
        clean_iban("TR33000610051978645784132")
    with pytest.raises(PayoutError):
        clean_iban("not an iban")


def test_a_payout_to_a_wallet_holder_stays_at_the_address() -> None:
    wallets, pool, payouts = book()
    policy = quake(pool)
    before = wallets.require("holder").balance
    pool.pay(policy, 7.3)
    assert wallets.require("holder").balance == pytest.approx(before + policy.payout)
    assert payouts.orders == {}


def test_a_payout_to_a_bank_holder_becomes_an_order() -> None:
    wallets, pool, payouts = book()
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"})
    policy = quake(pool)
    before = wallets.require("holder").balance
    pool.pay(policy, 7.3)
    # The money went through the address and on into the order.
    assert wallets.require("holder").balance == pytest.approx(before)
    (order,) = payouts.orders.values()
    assert order.amount == pytest.approx(policy.payout)
    assert order.currency == "TRY" and order.status == "queued" and order.rail == "manual"
    assert TR_IBAN not in json.dumps(order.to_dict()), "the owner sees it masked"
    assert order.destination.startswith("TR33 ••••")


def test_the_operator_marks_it_paid_or_returns_it() -> None:
    wallets, pool, payouts = book()
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"})
    a, b = quake(pool), quake(pool)
    pool.pay(a, 7.3)
    pool.pay(b, 7.3)
    first, second = sorted(payouts.orders.values(), key=lambda o: o.reference)
    payouts.settle(first.order_id, "paid", reference="SPECIMEN-EFT-1")
    assert first.status == "paid" and first.rail_reference == "SPECIMEN-EFT-1"
    before = wallets.require("holder").balance
    payouts.settle(second.order_id, "failed", note="account closed")
    assert wallets.require("holder").balance == pytest.approx(before + second.amount)
    with pytest.raises(PayoutError, match="already"):
        payouts.settle(second.order_id, "paid")


def test_mobile_money_needs_a_provider_where_it_operates() -> None:
    _, _, payouts = book()
    pref = payouts.set_preference("holder", {"method": "mobile_money", "provider": "mpesa",
                                             "country": "KE", "phone": "+254 712 345 678"})
    assert pref.currency == "KES" and pref.phone == "+254712345678"
    assert "712" not in pref.masked()[:8]
    with pytest.raises(PayoutError, match="not offered in that country"):
        payouts.set_preference("holder", {"method": "mobile_money", "provider": "gcash",
                                          "country": "KE", "phone": "+254712345678"})
    with pytest.raises(PayoutError, match="country code"):
        payouts.set_preference("holder", {"method": "mobile_money", "provider": "mpesa",
                                          "country": "KE", "phone": "0712345678"})


def test_a_partner_rail_is_sent_the_order_and_signs_nothing_it_did_not_see() -> None:
    wallets, pool, payouts = book()
    seen = {}

    def fetch(url, body, headers):
        seen["body"], seen["headers"] = json.loads(body), headers
        return b'{"reference": "SPECIMEN-RAIL-9"}'

    rail = HttpRail("https://rail.example/payouts", "specimen-secret", fetcher=fetch)
    payouts.rail = rail
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"})
    policy = quake(pool)
    pool.pay(policy, 7.3)
    (order,) = payouts.orders.values()
    assert order.status == "sent" and order.rail_reference == "SPECIMEN-RAIL-9"
    assert seen["body"]["destination"].startswith(TR_IBAN)
    raw = json.dumps(seen["body"], separators=(",", ":")).encode()
    assert seen["headers"]["x-clause-signature"] == rail.signature(raw)


def test_a_rail_that_is_down_leaves_the_order_waiting() -> None:
    wallets, pool, payouts = book()

    def down(url, body, headers):
        raise OSError("connection refused")

    payouts.rail = HttpRail("https://rail.example/payouts", "s", fetcher=down)
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"})
    pool.pay(quake(pool), 7.3)
    (order,) = payouts.orders.values()
    assert order.status == "queued" and "could not be reached" in order.note
    payouts.rail.fetcher = lambda url, body, headers: b'{"reference": "R2"}'
    # Not straight away: each failure waits longer than the last, so the
    # second attempt is due half a minute after the first.
    assert payouts.retry() == 0, "a retry inside the back off is not due"
    import time as _time

    assert payouts.retry(now=_time.time() + 31.0) == 1 and order.status == "sent"


def test_a_slow_partner_is_not_sent_the_same_payout_twice() -> None:
    """The retry loop runs every thirty seconds and the partner is given
    twenty to answer. Nothing recorded that an attempt was already in the air,
    so a partner that took longer than thirty seconds was handed the same
    payout again, and again, for as long as it stayed slow."""
    import time as _time

    wallets, pool, payouts = book()
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN,
                                      "holder_name": "Specimen Holder"})

    calls: list[str] = []

    def slow(url, body, headers):
        calls.append(headers["idempotency-key"])
        raise OSError("still thinking")

    payouts.rail = HttpRail("https://rail.example/payouts", "s", fetcher=slow)
    pool.pay(quake(pool), 7.3)
    (order,) = payouts.orders.values()
    assert order.attempts == 1 and len(calls) == 1

    # An attempt that has not come back yet is left alone, however long the
    # loop runs.
    order.in_flight = True
    for minute in range(1, 6):
        payouts.retry(now=_time.time() + minute * 60.0)
    assert len(calls) == 1, f"the rail was called again while in flight: {calls}"

    # And the partner is given what it needs to collapse a retry that crosses
    # with a slow success of its own.
    assert calls[0] == order.order_id


def test_a_payout_nobody_acknowledges_stops_and_waits_for_a_person() -> None:
    """A loop that will retry the same payment for ever is not resilience."""
    import time as _time

    from clause.protocol.payouts import MAX_ATTEMPTS

    wallets, pool, payouts = book()
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN,
                                      "holder_name": "Specimen Holder"})
    calls: list[str] = []

    def down(url, body, headers):
        calls.append(headers["idempotency-key"])
        raise OSError("connection refused")

    payouts.rail = HttpRail("https://rail.example/payouts", "s", fetcher=down)
    pool.pay(quake(pool), 7.3)
    (order,) = payouts.orders.values()

    at = _time.time()
    for _ in range(40):
        at += 1800.0                     # well past any back off
        payouts.retry(now=at)
    assert order.attempts == MAX_ATTEMPTS
    assert len(calls) == MAX_ATTEMPTS
    assert order.needs_a_person
    assert order.status == "queued", "the money is still held, not lost"


def test_a_refund_follows_the_same_route() -> None:
    wallets, pool, payouts = book()
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"})
    policy = quake(pool)
    pool.expire(policy)
    (order,) = payouts.orders.values()
    # To the cent: an order carries money somebody will actually send, so it is
    # rounded, and the premium it refunds is not.
    assert order.kind == "refund"
    assert order.amount == pytest.approx(policy.premium, abs=0.01)


RIALO = "HddrYhoVi2UAGXvJuCCZMECGGcdjK6FfwHB9cb9vpCJV"     # a playground style public key
EVM = "0x52908400098527886E0F7030069857D2E4169EE7"


def test_a_payout_can_go_to_a_rialo_solana_or_ethereum_wallet() -> None:
    from clause.protocol.payouts import clean_evm_address, clean_rialo_address
    assert clean_rialo_address(RIALO) == RIALO
    assert clean_evm_address(EVM) == EVM
    for bad in ("HddrYho", RIALO + "1", "0x1234", "not-an-address", RIALO.replace("H", "0")):
        with pytest.raises(PayoutError):
            clean_rialo_address(bad)
    with pytest.raises(PayoutError):
        clean_evm_address(RIALO)

    wallets, pool, payouts = book()
    pref = payouts.set_preference("holder", {"method": "rialo", "rialo_address": RIALO})
    assert pref.currency == "USDC" and pref.to_dict()["destination"] == "Hddr…pCJV"
    assert pref.to_dict()["rialo_address"] == RIALO and pref.destination() == RIALO
    policy = quake(pool)
    pool.pay(policy, 7.3)
    (order,) = payouts.orders.values()
    assert order.method == "rialo" and order.currency == "USDC" and order.status == "queued"

    evm = payouts.set_preference("other", {"method": "evm", "rialo_address": EVM})
    assert evm.method == "evm" and evm.destination() == EVM
    sol = payouts.set_preference("third", {"method": "solana", "rialo_address": RIALO})
    assert sol.method == "solana"


def test_a_cashout_leaves_the_address_and_comes_back_if_it_fails() -> None:
    from clause.protocol.wallet import WalletError
    wallets, pool, payouts = book()
    with pytest.raises(PayoutError, match="say where"):
        payouts.cashout("holder", 500)
    payouts.set_preference("holder", {"method": "bank", "iban": TR_IBAN, "holder_name": "Specimen Holder"})
    with pytest.raises(PayoutError, match="between"):
        payouts.cashout("holder", 1)
    with pytest.raises(WalletError):
        payouts.cashout("holder", 50_000)
    order = payouts.cashout("holder", 2_500)
    assert order.kind == "withdrawal" and order.status == "queued" and order.reference == "balance"
    assert wallets.require("holder").balance == pytest.approx(7_500)
    assert payouts.open_orders() == [order]
    payouts.settle(order.order_id, "failed", note="account closed")
    assert wallets.require("holder").balance == pytest.approx(10_000)
    again = payouts.cashout("holder", 1_000)
    payouts.settle(again.order_id, "paid", reference="BANK-1")
    assert wallets.require("holder").balance == pytest.approx(9_000)
    assert again.rail_reference == "BANK-1"


def test_no_more_than_three_cashouts_wait_at_once() -> None:
    wallets, pool, payouts = book()
    payouts.set_preference("holder", {"method": "evm", "rialo_address": "0x" + "ab" * 20})
    for _ in range(3):
        payouts.cashout("holder", 100)
    with pytest.raises(PayoutError, match="three"):
        payouts.cashout("holder", 100)
