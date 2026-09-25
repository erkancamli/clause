"""Where a payout goes after it reaches an address.

A payout lands at the holder's address the moment the index settles. For many
people that is not where money is useful: a farmer in Konya needs lira in a
bank account, a smallholder in Kenya needs shillings on M-Pesa. This module
is the step after settlement that takes it there.

What it does
------------
A holder chooses, by signing it, where their money should go:

    wallet          it stays at the address (the default, and the only choice
                    that needs nobody else)
    bank            an IBAN and the name on the account
    mobile_money    a mobile money provider and a phone number
    rialo           a Rialo wallet (a base58 public key, such as the custodial
                    keypair the Rialo playground gives every account)
    solana          a Solana wallet, USDC on Solana
    evm             an Ethereum style wallet (0x…), USDC on the chain the
                    operator's rail pays on

A payout to another chain is a transfer of USDC across a bridge or an
exchange, which is a payment partner's job like a bank transfer is; until a
rail is connected it is a manual order like the others.

When a payout or a refund arrives at an address whose holder chose a bank or a
mobile wallet, the amount is moved off the address into a payout order and
handed to a payment rail. The order records every step: queued, sent, paid, or
failed and returned to the address. Nothing is lost if the rail is down: the
order waits, and a failed order puts the money back where it was.

What it is not
--------------
The protocol does not move fiat money itself and does not pretend to. Money
reaches a bank account through the carrier that issued the policy or a
licensed payment partner, in the currency that partner pays in (in Türkiye,
lira). Until a partner's rail is connected the rail is manual: the order is
shown to the operator with the destination, the operator makes the transfer
and marks it paid with the bank's reference. That is slower and entirely
honest; an automatic rail replaces it without changing anything else here.

Bank and phone details are personal data. They are kept because a payment
cannot be made without them, shown back to their owner only masked, and shown
in full only to whoever has to make the transfer.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable
import logging

logger = logging.getLogger("clause.payouts")

METHODS = ("wallet", "bank", "mobile_money", "rialo", "solana", "evm")
MIN_CASHOUT = 10.0
MAX_CASHOUT = 1_000_000.0

# The currency each country's rail pays in. A rail converts from the unit of
# account at its own rate on the day; the order records what it was told.
CURRENCY = {
    "TR": "TRY", "DE": "EUR", "FR": "EUR", "ES": "EUR", "IT": "EUR", "NL": "EUR",
    "GR": "EUR", "PT": "EUR", "IE": "EUR", "AT": "EUR", "BE": "EUR", "FI": "EUR",
    "GB": "GBP", "CH": "CHF", "JP": "JPY", "MX": "MXN", "CL": "CLP", "NZ": "NZD",
    "TW": "TWD", "KE": "KES", "TZ": "TZS", "UG": "UGX", "GH": "GHS", "NG": "NGN",
    "PH": "PHP", "BD": "BDT", "ID": "IDR", "SN": "XOF", "CI": "XOF", "RW": "RWF",
    "ZM": "ZMW", "CM": "XAF", "US": "USD",
}

# IBAN lengths for the countries a holder is likely to name. A country not
# here is refused rather than guessed at.
IBAN_LENGTH = {
    "TR": 26, "DE": 22, "FR": 27, "ES": 24, "IT": 27, "NL": 18, "GR": 27,
    "PT": 25, "IE": 22, "AT": 20, "BE": 16, "FI": 18, "GB": 22, "CH": 21,
}

# Mobile money providers, and the countries each is offered in.
MOBILE_PROVIDERS: dict[str, dict[str, Any]] = {
    "mpesa": {"name": "M-Pesa", "countries": ("KE", "TZ")},
    "mtn_momo": {"name": "MTN MoMo", "countries": ("GH", "UG", "RW", "ZM", "CM", "CI")},
    "airtel_money": {"name": "Airtel Money", "countries": ("KE", "UG", "TZ", "RW", "ZM")},
    "orange_money": {"name": "Orange Money", "countries": ("SN", "CI", "CM")},
    "gcash": {"name": "GCash", "countries": ("PH",)},
    "bkash": {"name": "bKash", "countries": ("BD",)},
}

PHONE = re.compile(r"^\+[1-9]\d{7,14}$")


class PayoutError(ValueError):
    """A destination this module will not pay to. The message is safe to show."""


def clean_iban(value: str) -> str:
    iban = re.sub(r"\s+", "", str(value or "")).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", iban):
        raise PayoutError("that is not an IBAN")
    country = iban[:2]
    if country not in IBAN_LENGTH:
        raise PayoutError("payouts to a bank in that country are not offered yet")
    if len(iban) != IBAN_LENGTH[country]:
        raise PayoutError(f"an IBAN in {country} has {IBAN_LENGTH[country]} characters")
    moved = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in moved)
    if int(digits) % 97 != 1:
        raise PayoutError("that IBAN does not check out; a character is probably wrong")
    return iban


def mask_iban(iban: str) -> str:
    return f"{iban[:4]} •••• {iban[-4:]}"


_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def clean_rialo_address(value: str) -> str:
    """A Rialo public key: base58, decoding to 32 bytes, as Solana's do."""
    text = str(value or "").strip()
    if not 32 <= len(text) <= 44 or any(ch not in _B58 for ch in text):
        raise PayoutError("a Rialo address is 32 to 44 base58 characters")
    number = 0
    for ch in text:
        number = number * 58 + _B58.index(ch)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    raw = b"\x00" * (len(text) - len(text.lstrip("1"))) + raw
    if len(raw) != 32:
        raise PayoutError("that is not a Rialo address: it does not decode to 32 bytes")
    return text


def clean_evm_address(value: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", text):
        raise PayoutError("an Ethereum style address is 0x followed by 40 hex characters")
    return text


def mask_rialo(address: str) -> str:
    return f"{address[:4]}…{address[-4:]}"


def mask_phone(phone: str) -> str:
    return f"{phone[:4]} ••• {phone[-3:]}"


logger = logging.getLogger("clause.payouts")

#: How many times one payout is offered to the rail before it stops and waits
#: for a person. A loop that retries for ever is a way to send somebody the
#: same money a hundred times while nobody is watching.
MAX_ATTEMPTS = 6
#: The wait after the first failure, and the longest wait between attempts.
RETRY_FLOOR = 30.0
RETRY_CEILING = 900.0


@dataclass(slots=True)
class PayoutPreference:
    """Where one address wants its money to go."""

    account: str
    method: str = "wallet"
    country: str = ""
    currency: str = ""
    holder_name: str = ""
    iban: str = ""
    provider: str = ""
    phone: str = ""
    rialo_address: str = ""
    set_at: float = 0.0

    def destination(self) -> str:
        """In full, for whoever has to make the transfer."""
        if self.method == "bank":
            return f"{self.iban} ({self.holder_name})"
        if self.method == "mobile_money":
            return f"{MOBILE_PROVIDERS[self.provider]['name']} {self.phone}"
        if self.method in ("rialo", "solana", "evm"):
            return self.rialo_address
        return self.account

    def key(self) -> str:
        """The destination alone, the way a policy entry names it: the IBAN,
        the phone number or the wallet, with nothing else attached."""
        if self.method == "bank":
            return self.iban
        if self.method == "mobile_money":
            return self.phone
        if self.method in ("rialo", "solana", "evm"):
            return self.rialo_address
        return ""

    def masked(self) -> str:
        if self.method == "bank":
            return f"{mask_iban(self.iban)}, {self.holder_name}"
        if self.method == "mobile_money":
            return f"{MOBILE_PROVIDERS[self.provider]['name']} {mask_phone(self.phone)}"
        if self.method in ("rialo", "solana", "evm"):
            # A public key is not a secret; shown short so it fits, whole on request.
            return mask_rialo(self.rialo_address)
        return "your address"

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "country": self.country, "currency": self.currency,
                "destination": self.masked(), "provider": self.provider or None,
                "rialo_address": self.rialo_address or None,
                "set_at": self.set_at}


@dataclass(slots=True)
class PayoutOrder:
    """One payout on its way off the protocol."""

    order_id: str
    account: str
    amount: float
    method: str
    currency: str
    destination: str        # masked
    reference: str          # the policy it came from
    kind: str               # payout | refund | withdrawal
    created_at: float
    # One attempt at a time, and a record of them. The retry loop runs every
    # thirty seconds and the partner is given twenty to answer, so without
    # this a slow partner was handed the same payout over and over.
    in_flight: bool = False
    attempts: int = 0
    last_attempt_at: float = 0.0
    needs_a_person: bool = False
    status: str = "queued"  # queued | sent | paid | failed
    rail: str = "manual"
    rail_reference: str = ""
    note: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"order_id": self.order_id, "amount": round(self.amount, 2), "method": self.method,
                "currency": self.currency, "destination": self.destination,
                "reference": self.reference, "kind": self.kind, "created_at": self.created_at,
                "status": self.status, "rail": self.rail, "rail_reference": self.rail_reference,
                "note": self.note, "history": list(self.history)}


# ---------------------------------------------------------------------------
# Rails
# ---------------------------------------------------------------------------


class ManualRail:
    """No partner connected: the operator makes the transfer by hand."""

    name = "manual"

    def send(self, order: PayoutOrder, destination: str) -> str | None:
        return None


class HttpRail:
    """A payment partner's API: one POST per order, a reference back.

    The partner reports the outcome later to /api/payouts/callback, signed
    with the same shared secret, so a payout is marked paid on the partner's
    word and nobody else's.
    """

    name = "partner"

    def __init__(self, url: str, secret: str, fetcher: Callable[..., bytes] | None = None) -> None:
        self.url = url
        self.secret = secret
        self.fetcher = fetcher or self._post

    def _post(self, url: str, body: bytes, headers: dict[str, str]) -> bytes:
        request = urllib.request.Request(url, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(request, timeout=20) as reply:  # noqa: S310
            return reply.read()

    def signature(self, body: bytes) -> str:
        return hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()

    def send(self, order: PayoutOrder, destination: str) -> str | None:
        body = json.dumps({
            "order_id": order.order_id, "amount": round(order.amount, 2), "unit": "USDC",
            "currency": order.currency, "method": order.method, "destination": destination,
            "reference": order.reference,
        }, separators=(",", ":")).encode()
        reply = self.fetcher(self.url, body, {
            "content-type": "application/json",
            "x-clause-signature": self.signature(body),
            # The order id was in the body and nowhere a partner's own
            # middleware would look. This is the header every payment API
            # documents, so a retry that crosses with a slow success is the
            # partner's to collapse rather than ours to hope about.
            "idempotency-key": order.order_id})
        data = json.loads(reply or b"{}")
        reference = str(data.get("reference") or "")[:80]
        if not reference:
            raise RuntimeError("the payment partner did not return a reference")
        return reference


def rail_from_env(environ: dict[str, str]) -> Any:
    url = (environ.get("CLAUSE_OFFRAMP_URL") or "").strip()
    secret = (environ.get("CLAUSE_OFFRAMP_SECRET") or "").strip()
    if url and secret:
        return HttpRail(url, secret)
    return ManualRail()


# ---------------------------------------------------------------------------
# The book of payouts
# ---------------------------------------------------------------------------


class Payouts:
    def __init__(self, wallets: Any, rail: Any = None, lock: Any = None,
                 *, background: bool = False) -> None:
        import threading

        self.wallets = wallets
        # Settlement calls route() while holding the lock every movement of
        # value holds. A partner's API can take seconds, so in a server the
        # send happens on its own thread, after the lock is released.
        self.background = background
        self.rail = rail or ManualRail()
        self.lock = lock or threading.RLock()
        self.preferences: dict[str, PayoutPreference] = {}
        self.orders: dict[str, PayoutOrder] = {}
        # The operator's policy, asked before money leaves for a destination:
        # (account, destination, amount) -> a reason to refuse, or None. A
        # refused payout stays at the address; a refused cashout is an error.
        self.gate: Callable[[str, str, float], str | None] | None = None

    # -- choosing ----------------------------------------------------------

    def set_preference(self, account: str, body: dict[str, Any], *, now: float | None = None) -> PayoutPreference:
        method = str(body.get("method") or "wallet")
        if method not in METHODS:
            raise PayoutError("a payout goes to your address, a bank account, a mobile wallet, or a Rialo, Solana or Ethereum wallet")
        now = time.time() if now is None else now
        pref = PayoutPreference(account=account, method=method, set_at=now)
        if method == "bank":
            iban = clean_iban(body.get("iban", ""))
            name = " ".join(str(body.get("holder_name") or "").split())[:80]
            if len(name) < 3:
                raise PayoutError("give the name on the bank account")
            pref.iban, pref.holder_name, pref.country = iban, name, iban[:2]
            pref.currency = CURRENCY.get(iban[:2], "EUR")
        elif method == "mobile_money":
            provider = str(body.get("provider") or "")
            if provider not in MOBILE_PROVIDERS:
                raise PayoutError("that mobile money provider is not offered")
            country = str(body.get("country") or "").upper()
            if country not in MOBILE_PROVIDERS[provider]["countries"]:
                raise PayoutError(f"{MOBILE_PROVIDERS[provider]['name']} is not offered in that country")
            phone = re.sub(r"[\s()-]", "", str(body.get("phone") or ""))
            if not PHONE.fullmatch(phone):
                raise PayoutError("give the phone number with its country code, like +254712345678")
            pref.provider, pref.phone, pref.country = provider, phone, country
            pref.currency = CURRENCY.get(country, "USD")
        elif method in ("rialo", "solana"):
            pref.rialo_address = clean_rialo_address(body.get("rialo_address", ""))
            pref.currency = "USDC"
        elif method == "evm":
            pref.rialo_address = clean_evm_address(body.get("rialo_address", ""))
            pref.currency = "USDC"
        with self.lock:
            self.preferences[account] = pref
        return pref

    def preference(self, account: str) -> PayoutPreference:
        return self.preferences.get(account) or PayoutPreference(account=account)

    # -- routing -----------------------------------------------------------

    def route(self, account: str, amount: float, reference: str, kind: str,
              *, now: float | None = None) -> PayoutOrder | None:
        """Called when money has just arrived at an address from the pool."""
        pref = self.preferences.get(account)
        if pref is None or pref.method == "wallet" or amount <= 0:
            return None
        refused = self.gate(account, pref.key(), amount) if self.gate else None
        if refused:
            # The money has landed at the address and stays there: nothing
            # leaves the protocol for a destination the policy refuses.
            logger.warning("payout of %.2f for %s kept at the address: %s", amount, account, refused)
            return None
        return self._order(account, pref, amount, reference, kind, now)

    def cashout(self, account: str, amount: float, *, now: float | None = None) -> PayoutOrder:
        """Balance leaving of its own accord: the person asks for part of what
        their address holds to be sent where their payouts go. Capital taken
        back from the pool and returns on it come out this way, as does a
        payout that landed at the address before a bank was chosen. The
        amount is taken off the address at once and comes back if the
        transfer fails."""
        pref = self.preferences.get(account)
        if pref is None or pref.method == "wallet":
            raise PayoutError("say where the money should go first: a bank account, "
                              "a mobile wallet or a wallet on another chain")
        try:
            amount = round(float(amount), 2)
        except (TypeError, ValueError) as error:
            raise PayoutError("say how much") from error
        if not MIN_CASHOUT <= amount <= MAX_CASHOUT:
            raise PayoutError(f"an amount between {MIN_CASHOUT:,.0f} and {MAX_CASHOUT:,.0f}")
        refused = self.gate(account, pref.key(), amount) if self.gate else None
        if refused:
            raise PayoutError(refused)
        with self.lock:
            waiting = [o for o in self.orders.values()
                       if o.account == account and o.kind == "withdrawal" and o.status in ("queued", "sent")]
            if len(waiting) >= 3:
                raise PayoutError("three withdrawals are already on their way; wait for them")
        return self._order(account, pref, amount, "balance", "withdrawal", now)

    def _order(self, account: str, pref: PayoutPreference, amount: float, reference: str,
               kind: str, now: float | None) -> PayoutOrder:
        now = time.time() if now is None else now
        with self.lock:
            order = PayoutOrder(
                order_id="PO-" + secrets.token_hex(5).upper(), account=account, amount=amount,
                method=pref.method, currency=pref.currency, destination=pref.masked(),
                reference=reference, kind=kind, created_at=now, rail=self.rail.name,
            )
            # Off the address and into the order, so the same money cannot be
            # spent on a premium while it is on its way to a bank.
            self.wallets.debit(account, amount, order.order_id, kind="payout_order")
            order.history.append({"at": now, "status": "queued"})
            self.orders[order.order_id] = order
        if self.rail.name == "manual":
            return order
        if self.background:
            import threading
            threading.Thread(target=self._send, args=(order, pref, now), daemon=True).start()
        else:
            self._send(order, pref, now)
        return order

    def _send(self, order: PayoutOrder, pref: PayoutPreference, now: float) -> None:
        """One attempt at the rail. Never two at once, for the same order.

        The order stays ``queued`` until the rail answers, and the retry loop
        runs every thirty seconds while the partner is given twenty to reply.
        There was nothing recording that an attempt was already in the air, so
        a partner that took longer than thirty seconds was sent the same
        payout again, and again, for as long as it stayed slow. The partner's
        own idempotency is the last line, not the first, and it was being
        asked to carry the whole thing on an ``order_id`` in a body.
        """
        with self.lock:
            if order.in_flight or order.status != "queued":
                return
            order.in_flight = True
            order.attempts += 1
            order.last_attempt_at = now
            attempt = order.attempts
        try:
            reference = self.rail.send(order, pref.destination())
        except Exception as error:  # the order waits and is retried
            with self.lock:
                order.in_flight = False
                order.note = (f"attempt {attempt}: the payment partner could not "
                              f"be reached: {str(error)[:120]}")
            return
        with self.lock:
            order.in_flight = False
            if reference:
                order.status, order.rail_reference = "sent", reference
                order.history.append({"at": now, "status": "sent",
                                      "reference": reference, "attempt": attempt})

    def retry(self, *, now: float | None = None) -> int:
        """Try again the orders that are due for it. Returns how many went.

        Due, not merely queued: an attempt already in the air is left alone,
        each failure waits longer than the last, and after ``MAX_ATTEMPTS`` the
        order stops being retried and waits for a person. A loop that will
        retry the same payment for ever is not resilience, it is a way to send
        somebody the same money a hundred times while nobody is watching.
        """
        now = time.time() if now is None else now
        sent = 0
        for order in list(self.orders.values()):
            if order.status != "queued" or order.rail == "manual":
                continue
            if order.in_flight:
                continue
            if order.attempts >= MAX_ATTEMPTS:
                if not order.needs_a_person:
                    order.needs_a_person = True
                    order.history.append({
                        "at": now, "status": "stalled",
                        "note": f"{order.attempts} attempts, none acknowledged"})
                    logger.error("payout %s stopped after %s attempts: %s",
                                 order.order_id, order.attempts, order.note)
                continue
            if now - order.last_attempt_at < self._backoff(order.attempts):
                continue
            pref = self.preferences.get(order.account)
            if pref is not None:
                self._send(order, pref, now)
                sent += order.status == "sent"
        return sent

    @staticmethod
    def _backoff(attempts: int) -> float:
        """How long to wait before trying again, after so many attempts.

        Doubling from half a minute, capped. The docstring on the old loop
        described a back off; the code had none and ran every thirty seconds
        for ever.
        """
        return min(RETRY_CEILING, RETRY_FLOOR * (2 ** max(0, attempts - 1)))

    def settle(self, order_id: str, status: str, *, reference: str = "", note: str = "",
               by: str = "operator", now: float | None = None) -> PayoutOrder:
        """The rail or the operator says what happened."""
        if status not in ("paid", "failed"):
            raise PayoutError("an order is marked paid or failed")
        now = time.time() if now is None else now
        with self.lock:
            order = self.orders.get(order_id)
            if order is None:
                raise PayoutError("no such payout order")
            if order.status in ("paid", "failed"):
                raise PayoutError(f"that order is already {order.status}")
            order.status = status
            order.note = note[:200]
            if reference:
                order.rail_reference = reference[:80]
            order.history.append({"at": now, "status": status, "by": by,
                                  "reference": order.rail_reference})
            if status == "failed":
                # Back where it came from, and said so.
                self.wallets.credit(order.account, order.amount, order.order_id, kind="payout_returned")
        return order

    def for_account(self, account: str) -> list[PayoutOrder]:
        return sorted((o for o in self.orders.values() if o.account == account),
                      key=lambda o: -o.created_at)

    def open_orders(self) -> list[PayoutOrder]:
        return sorted((o for o in self.orders.values() if o.status in ("queued", "sent")),
                      key=lambda o: o.created_at)

    def describe(self) -> dict[str, Any]:
        return {
            "methods": list(METHODS),
            "rail": self.rail.name,
            "mobile_providers": {k: {"name": v["name"], "countries": list(v["countries"])}
                                 for k, v in MOBILE_PROVIDERS.items()},
            "bank_countries": sorted(IBAN_LENGTH),
            "min_cashout": MIN_CASHOUT, "max_cashout": MAX_CASHOUT,
        }
