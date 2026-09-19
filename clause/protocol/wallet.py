"""Identity, which is an address and nothing else.

There is no account to open in this protocol. No email, no password, no user
row, no profile. Whoever holds the key to an address is the holder of what that
address owns. That is not a shortcut taken to save building a login; it is the
only design that makes the rest of the protocol's claims true.

Two doors, one protocol
-----------------------
Requiring a browser extension and a seed phrase would put this product out of
reach of the people who need parametric cover most, and would contradict the
premise that a chain should be usable by someone who has never heard of one. So
an address can be reached two ways, and the protocol cannot tell them apart:

  PASSKEY   The ordinary way in. The buyer signs in with a phone number or an
            email and authorises with the fingerprint or face their device
            already uses. A key is generated on that device and never leaves
            it. They are never shown a seed phrase, never install anything, and
            the word wallet does not appear on screen.

  WALLET    For someone who already has one. They connect it, and their address
            is their identity in the usual way.

What makes the first door workable here is a property of the product rather
than of the plumbing. The hard part of using a chain is not holding a key, it
is being asked to approve something over and over. A parametric policy asks for
exactly one signature, at purchase. Settlement asks for none, because the
predicate pays without being told to. Someone can therefore buy cover once,
never open the application again, and still be paid the day the index moves.

A passkey account is not a lesser account. It is the same address, it holds the
same objects, and it can be exported to a wallet of the holder's choosing at
any time. Custody below records which door was used, because an interface
should speak to a person in the terms they arrived in, not because the protocol
treats them differently.

Note what is still absent in both cases: the phone number or email is used to
derive the address and is not stored. This module holds addresses, balances and
movements. It never holds a person.

Consider what a conventional insurer's user table is actually for. It exists
because the insurer holds the record of what you bought, and you have to prove
you are the person that record belongs to in order to argue with it. Every
claims dispute in history is a dispute about the contents of that table.

Here the policy is an object on the chain, owned by an address, carrying its
own terms: the index, the source, the trigger, the limit, the deadline. The
protocol does not need to remember who you are, because it is not holding
anything of yours that it could lose or misreport. What this module keeps is
the counterparty side of the money: how much the address holds, and what moved.

Three consequences worth stating, because they are what a buyer actually gets:

  Nothing to claim. A payout lands at the address in the block the predicate
  turned true. The buyer does not have to open anything, sign anything, or know
  the event happened.

  Nothing to lose. If this server is deleted, no policy is affected. The index
  it keeps is a cache and rebuilds from the chain.

  Nothing to take on faith. The buyer's own history is readable from the chain
  without this interface at all: get_subscription for what is armed,
  get_triggered_transactions for what has paid, and get_workflow_lineage for
  why a given payment fired, down to the reading and the block. An insurer that
  can be audited by its customer without its own cooperation is a different
  kind of institution from the one that exists today.

Balances here are in whole units of the settlement asset. In a deployment they
are the asset's own balances and this module is a read through to the chain;
holding them locally is what makes the simulator self contained.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Iterable


class WalletError(RuntimeError):
    """A movement that would leave an address short."""


# What a freshly connected demo address is funded with, so the interface can be
# operated without a faucet step. A deployment funds nothing.
DEMO_BALANCE = 250_000.0


def derive_address(seed: str | None = None) -> str:
    """An address, in the chain's display form.

    Rialo accounts are 32 byte keys shown in base58, and this produces that
    shape (see protocol/address.py); nothing depends on its internals.
    """
    from .address import from_material
    material = seed or secrets.token_hex(16)
    return from_material(material.encode())


def shorten(address: str) -> str:
    """How an address is shown in an interface: enough to recognise, no more."""
    return address if len(address) <= 13 else f"{address[:6]}…{address[-4:]}"


@dataclass(slots=True)
class Movement:
    """One change in an address's balance, and what caused it."""

    at: float
    kind: str          # premium, payout, refund, deposit, withdrawal, faucet
    amount: float      # signed, from the address's point of view
    reference: str     # the policy or the counterparty
    balance_after: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "kind": self.kind,
            "amount": round(self.amount, 2),
            "reference": self.reference,
            "balance_after": round(self.balance_after, 2),
        }


@dataclass(slots=True)
class Account:
    """An address and what it holds. There is no name here, by design."""

    address: str
    balance: float = 0.0
    custody: str = "wallet"   # wallet or passkey: how the holder reaches it
    connected_at: float = field(default_factory=time.time)
    movements: list[Movement] = field(default_factory=list)

    @property
    def short(self) -> str:
        return shorten(self.address)

    @property
    def self_custodied(self) -> bool:
        """True for both doors. A passkey account is not held by the protocol."""
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "short": self.short,
            "balance": round(self.balance, 2),
            "custody": self.custody,
            "connected_at": self.connected_at,
            "movements": [m.as_dict() for m in reversed(self.movements[-40:])],
        }


class Wallets:
    """The counterparty ledger, addressed rather than identified.

    Every method takes an address. None of them takes a user, because there is
    no such thing here.
    """

    def __init__(self, *, demo_balance: float = DEMO_BALANCE) -> None:
        self.accounts: dict[str, Account] = {}
        self.demo_balance = demo_balance

    # -- connecting -------------------------------------------------------

    def connect(
        self, address: str | None = None, *, fund: bool | None = None,
        custody: str = "wallet",
    ) -> Account:
        """Connect an address, creating the local record if it is new.

        Connecting is not registering. It creates no identity, asks for no
        detail, and an address that has never connected is in exactly the same
        position as one that has: its policies are on the chain either way.
        """
        address = address or derive_address()
        existing = self.accounts.get(address)
        if existing is not None:
            return existing

        account = Account(address=address, custody=custody)
        self.accounts[address] = account
        if fund is None:
            fund = self.demo_balance > 0
        if fund:
            self._move(account, "faucet", self.demo_balance, "demo funding")
        return account

    def sign_in(self, handle: str, *, fund: bool | None = None) -> Account:
        """The ordinary door: a phone number or an email, and the device's own key.

        The handle derives the address and is then discarded. Nothing here maps
        an address back to a person, so this module cannot leak one, and a
        subpoena served on it returns addresses.

        In a deployment the device's passkey holds the signing key and this
        derivation is replaced by the account the passkey controls. What does
        not change is the part that matters to the buyer: no seed phrase, no
        extension, no new vocabulary, and after purchase nothing to sign ever
        again.
        """
        handle = handle.strip().lower()
        if not handle:
            raise WalletError("a phone number or email is needed to sign in")
        return self.connect(
            derive_address(f"clause/passkey/{handle}"),
            fund=fund, custody="passkey",
        )

    def get(self, address: str) -> Account | None:
        return self.accounts.get(address)

    def require(self, address: str) -> Account:
        account = self.accounts.get(address)
        if account is None:
            raise WalletError(f"unknown address {shorten(address)}")
        return account

    # -- movement ---------------------------------------------------------

    def debit(self, address: str, amount: float, reference: str, *, kind: str = "premium") -> Account:
        """Take funds from an address, refusing rather than going negative."""
        if amount < 0:
            raise WalletError("a debit cannot be negative")
        account = self.require(address)
        if amount > account.balance + 1e-9:
            raise WalletError(
                f"{shorten(address)} holds {account.balance:,.2f} "
                f"against a required {amount:,.2f}"
            )
        return self._move(account, kind, -amount, reference)

    def credit(self, address: str, amount: float, reference: str, *, kind: str = "payout") -> Account:
        """Put funds at an address. Settlement uses this and asks nobody."""
        if amount < 0:
            raise WalletError("a credit cannot be negative")
        account = self.accounts.get(address)
        if account is None:
            # A payout to an address that never used this interface is still a
            # payout. The chain does not require anyone to have logged in.
            account = self.connect(address, fund=False)
        return self._move(account, kind, amount, reference)

    def _move(self, account: Account, kind: str, amount: float, reference: str) -> Account:
        account.balance = round(account.balance + amount, 6)
        account.movements.append(
            Movement(
                at=time.time(), kind=kind, amount=amount,
                reference=reference, balance_after=account.balance,
            )
        )
        return account

    # -- reading ----------------------------------------------------------

    def portfolio(self, address: str, policies: Iterable[Any]) -> dict[str, Any]:
        """Everything this address holds, assembled the way the chain would.

        The equivalent calls on a live chain are get_subscription for the armed
        predicates and get_triggered_transactions for what has settled. This
        assembles the same two sets from the local index, which is a cache of
        exactly that.
        """
        account = self.accounts.get(address)
        mine = [p for p in policies if p.holder == address]
        open_ = [p for p in mine if p.is_open]
        settled = [p for p in mine if not p.is_open]

        paid = sum(p.payout for p in mine)
        spent = sum(p.premium for p in mine)
        refunded = sum(p.premium for p in settled if p.status.value == "expired")

        return {
            "address": address,
            "short": shorten(address),
            "balance": round(account.balance, 2) if account else 0.0,
            "connected": account is not None,
            "custody": account.custody if account else None,
            "cover_in_force": round(sum(p.limit for p in open_), 2),
            "policies_open": len(open_),
            "policies_settled": len(settled),
            "premium_paid": round(spent, 2),
            "claims_received": round(paid, 2),
            "premium_refunded": round(refunded, 2),
            "net": round(paid + refunded - spent, 2),
            "movements": [m.as_dict() for m in reversed(account.movements[-40:])] if account else [],
        }
