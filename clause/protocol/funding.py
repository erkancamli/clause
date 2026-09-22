"""How balance comes in from outside: the mirror of payouts.

A person who has no USDC at their address needs a way to put some there
that does not start with a crypto exchange. This module gives them the
two ways an insurer already offers for a premium: a bank transfer, and a
transfer from a wallet they hold elsewhere.

    bank        the operator's bank account, shown with a reference the
                person writes on the transfer
    rialo       USDC sent to the operator's Rialo address
    solana      USDC sent to the operator's Solana address
    evm         USDC sent to the operator's Ethereum style address

Each request records who is sending, how much they said they would, and
the reference that ties the incoming money to their address. Nothing is
credited by this module on its own: the operator sees the request beside
the bank statement or the chain explorer, confirms the amount that arrived,
and only then is the address credited, with the confirmation and the
operator's name on the ledger. A request nobody confirms in thirty days
closes itself; the person can make another.

A bank transfer takes a day or two in most countries and is always
confirmed by a person. A wallet deposit need not be: with an RPC endpoint
for the chain (CLAUSE_FUNDING_SOLANA_RPC, CLAUSE_FUNDING_EVM_RPC) the
Watcher below reads the USDC transfers into the receiving address every
half minute, matches each to a waiting request (by the reference in the
memo on Solana, by the sending address on Ethereum style chains, where a
token transfer carries no memo) and confirms it itself, crediting what
actually arrived. What it cannot match is left for the operator, who sees
the same list.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .payouts import clean_evm_address, clean_rialo_address, mask_rialo

METHODS = ("bank", "rialo", "solana", "evm")
MIN_AMOUNT = 10.0
MAX_AMOUNT = 1_000_000.0
EXPIRES_AFTER = 30 * 86400.0


class FundingError(ValueError):
    """A request this module refuses. Safe to show."""


@dataclass(frozen=True, slots=True)
class Destinations:
    """Where the operator receives money. From the environment; each is
    shown only if it is set.

    A wallet address is not an instruction on its own. The same twenty bytes
    exist on Ethereum, on Base, on every other EVM chain and on their test
    networks, and money sent to the right address on the wrong one is gone.
    So each wallet destination carries the name of the chain it is watched on,
    and that name is shown beside the address rather than assumed. ``testnet``
    is set by hand rather than guessed from the name: a deployment that means
    play money has to say so.
    """

    iban: str = ""
    account_name: str = ""
    bank: str = ""
    rialo: str = ""
    solana: str = ""
    evm: str = ""
    rialo_chain: str = ""
    solana_chain: str = ""
    evm_chain: str = ""
    testnet: bool = False

    @classmethod
    def from_env(cls) -> "Destinations":
        get = lambda key: os.environ.get(key, "").strip()  # noqa: E731
        rialo, solana, evm = get("CLAUSE_FUNDING_RIALO"), get("CLAUSE_FUNDING_SOLANA"), get("CLAUSE_FUNDING_EVM")
        for value, clean in ((rialo, clean_rialo_address), (solana, clean_rialo_address), (evm, clean_evm_address)):
            if value:
                clean(value)          # a mistyped address in the environment fails at start, loudly
        return cls(iban=get("CLAUSE_FUNDING_IBAN").replace(" ", "").upper(),
                   account_name=get("CLAUSE_FUNDING_NAME"), bank=get("CLAUSE_FUNDING_BANK"),
                   rialo=rialo, solana=solana, evm=evm,
                   rialo_chain=get("CLAUSE_FUNDING_RIALO_CHAIN")[:48],
                   solana_chain=get("CLAUSE_FUNDING_SOLANA_CHAIN")[:48],
                   evm_chain=get("CLAUSE_FUNDING_EVM_CHAIN")[:48],
                   testnet=get("CLAUSE_FUNDING_TESTNET") == "1")

    def offered(self) -> list[str]:
        out = []
        if self.iban:
            out.append("bank")
        for name in ("rialo", "solana", "evm"):
            # An address without the name of its chain is withheld rather than
            # shown: whoever reads it would have to guess, and a wrong guess
            # does not bounce.
            if getattr(self, name) and getattr(self, name + "_chain"):
                out.append(name)
        return out

    def networks(self) -> dict[str, str]:
        """The chain each wallet destination is watched on, by method."""
        return {name: getattr(self, name + "_chain")
                for name in ("rialo", "solana", "evm")
                if getattr(self, name) and getattr(self, name + "_chain")}

    def unnamed(self) -> list[str]:
        """Wallet destinations offered without saying which chain they are on.

        Refusing to offer these is the safe reading: an address with no chain
        beside it is an invitation to send money to the wrong one.
        """
        return [name for name in ("rialo", "solana", "evm")
                if getattr(self, name) and not getattr(self, name + "_chain")]

    def describe(self) -> dict[str, Any]:
        return {
            "methods": self.offered(),
            "bank": {"iban": self.iban, "account_name": self.account_name, "bank": self.bank} if self.iban else None,
            "rialo": self.rialo or None, "solana": self.solana or None, "evm": self.evm or None,
            "networks": self.networks(),
            "testnet": self.testnet,
            "min_amount": MIN_AMOUNT, "max_amount": MAX_AMOUNT,
        }


@dataclass(slots=True)
class FundingRequest:
    request_id: str
    account: str
    method: str
    amount: float                       # what the person said they would send
    reference: str                      # written on the transfer, ties it to the address
    created_at: float
    sender: str = ""                    # the sending wallet, for a chain deposit
    tx: str = ""                        # the transaction that paid it, when a watcher saw it
    status: str = "waiting"             # waiting | received | cancelled | expired
    received: float = 0.0               # what the operator confirmed arrived
    confirmed_by: str = ""
    confirmed_at: float | None = None
    note: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def open(self) -> bool:
        return self.status == "waiting"

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id, "method": self.method, "amount": round(self.amount, 2),
            "reference": self.reference, "created_at": self.created_at,
            "expires_at": self.created_at + EXPIRES_AFTER,
            "sender": mask_rialo(self.sender) if self.sender else "",
            "status": self.status, "received": round(self.received, 2),
            "confirmed_at": self.confirmed_at, "note": self.note, "tx": self.tx,
        }


class Funding:
    def __init__(self, wallets: Any, destinations: Destinations | None = None,
                 lock: threading.RLock | None = None, links: Any = None) -> None:
        self.wallets = wallets
        self.destinations = destinations or Destinations()
        self.lock = lock or threading.RLock()
        self.requests: dict[str, FundingRequest] = {}
        # Wallets people have linked to their accounts (protocol.links): a
        # deposit from one needs no announcement and no memo.
        self.links = links

    def unannounced(self, account: str, method: str, amount: float, *, sender: str, tx: str,
                    by: str, now: float | None = None) -> FundingRequest:
        """USDC that arrived from a wallet linked to an account, with nothing
        announced: recorded as a request and credited in one step."""
        now = time.time() if now is None else now
        with self.lock:
            req = FundingRequest(request_id="FR-" + secrets.token_hex(5).upper(), account=account,
                                 method=method, amount=round(amount, 2), reference="LINKED",
                                 created_at=now, sender=sender)
            req.history.append({"at": now, "status": "waiting", "note": "from a linked wallet"})
            self.requests[req.request_id] = req
            return self.confirm(req.request_id, amount, by=by, note=f"from a linked wallet: {tx[:40]}",
                                tx=tx, now=now)

    # -- asking ------------------------------------------------------------

    def request(self, account: str, body: dict[str, Any], *, now: float | None = None) -> FundingRequest:
        method = str(body.get("method") or "")
        if method not in METHODS:
            raise FundingError("balance comes in by bank transfer or from a Rialo, Solana or Ethereum wallet")
        if method not in self.destinations.offered():
            raise FundingError("that way of adding balance is not offered on this deployment")
        try:
            amount = round(float(body.get("amount") or 0.0), 2)
        except (TypeError, ValueError) as error:
            raise FundingError("say how much you will send") from error
        if not MIN_AMOUNT <= amount <= MAX_AMOUNT:
            raise FundingError(f"an amount between {MIN_AMOUNT:,.0f} and {MAX_AMOUNT:,.0f}")
        sender = ""
        if method in ("rialo", "solana"):
            sender = clean_rialo_address(body.get("sender", "")) if body.get("sender") else ""
        elif method == "evm":
            sender = clean_evm_address(body.get("sender", "")) if body.get("sender") else ""
        now = time.time() if now is None else now
        with self.lock:
            waiting = [r for r in self.requests.values() if r.account == account and r.open]
            if len(waiting) >= 5:
                raise FundingError("five requests are already waiting; cancel one or wait for the operator")
            reference = "CL-" + secrets.token_hex(3).upper()
            while any(r.reference == reference for r in self.requests.values()):
                reference = "CL-" + secrets.token_hex(3).upper()
            req = FundingRequest(request_id="FR-" + secrets.token_hex(5).upper(), account=account,
                                 method=method, amount=amount, reference=reference, created_at=now,
                                 sender=sender)
            req.history.append({"at": now, "status": "waiting"})
            self.requests[req.request_id] = req
        return req

    def mine(self, account: str) -> list[FundingRequest]:
        return sorted((r for r in self.requests.values() if r.account == account),
                      key=lambda r: -r.created_at)

    def cancel(self, account: str, request_id: str, *, now: float | None = None) -> FundingRequest:
        with self.lock:
            req = self.requests.get(request_id)
            if req is None or req.account != account:
                raise FundingError("no such request")
            if not req.open:
                raise FundingError(f"that request is already {req.status}")
            req.status = "cancelled"
            req.history.append({"at": time.time() if now is None else now, "status": "cancelled"})
        return req

    # -- confirming --------------------------------------------------------

    def waiting(self) -> list[FundingRequest]:
        return sorted((r for r in self.requests.values() if r.open), key=lambda r: r.created_at)

    def confirm(self, request_id: str, received: float, *, by: str, note: str = "",
                now: float | None = None, tx: str = "") -> FundingRequest:
        """The money arrived: credit the address with what actually came."""
        now = time.time() if now is None else now
        with self.lock:
            req = self.requests.get(request_id)
            if req is None:
                raise FundingError("no such request")
            if not req.open:
                raise FundingError(f"that request is already {req.status}")
            received = round(float(received), 2)
            if not 0 < received <= MAX_AMOUNT * 2:
                raise FundingError("the amount received must be positive")
            req.status = "received"
            req.received = received
            req.confirmed_by = by[:80]
            req.confirmed_at = now
            req.note = note[:200]
            req.tx = tx[:128]
            req.history.append({"at": now, "status": "received", "by": req.confirmed_by, "amount": received})
            self.wallets.connect(req.account, fund=False)
            self.wallets.credit(req.account, received, req.request_id, kind="funding")
        return req

    def reject(self, request_id: str, *, by: str, note: str, now: float | None = None) -> FundingRequest:
        now = time.time() if now is None else now
        with self.lock:
            req = self.requests.get(request_id)
            if req is None:
                raise FundingError("no such request")
            if not req.open:
                raise FundingError(f"that request is already {req.status}")
            if len(note.strip()) < 3:
                raise FundingError("say why; the person is told")
            req.status = "cancelled"
            req.confirmed_by = by[:80]
            req.confirmed_at = now
            req.note = note[:200]
            req.history.append({"at": now, "status": "cancelled", "by": req.confirmed_by})
        return req

    def expire(self, *, now: float | None = None) -> int:
        now = time.time() if now is None else now
        n = 0
        with self.lock:
            for req in self.requests.values():
                if req.open and now - req.created_at > EXPIRES_AFTER:
                    req.status = "expired"
                    req.history.append({"at": now, "status": "expired"})
                    n += 1
        return n


# ---------------------------------------------------------------------------
# Watching the chains
# ---------------------------------------------------------------------------

USDC_DECIMALS = 6
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
REFERENCE = re.compile(r"CL-[0-9A-F]{6}")
TRANSFER_TOPIC = "0x" + "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _rpc(url: str, method: str, params: list[Any], *, timeout: float = 12.0) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(url, data=body, headers={"content-type": "application/json",
                                                              "user-agent": "Clause/0.1 (+https://clause.insure)"})
    with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310
        answer = json.loads(reply.read(4_000_000))
    if "error" in answer:
        raise RuntimeError(str(answer["error"])[:200])
    return answer.get("result")


class Watcher:
    """Reads the receiving addresses and confirms what it can match.

    ``rpc`` is injectable so the tests hand it a fake chain."""

    def __init__(self, funding: Funding, *, solana_rpc: str = "", evm_rpc: str = "",
                 evm_usdc: str = "", solana_mint: str = SOLANA_USDC_MINT, rpc=None) -> None:
        self.funding = funding
        self.solana_rpc = solana_rpc
        self.evm_rpc = evm_rpc
        self.evm_usdc = evm_usdc.lower()
        self.solana_mint = solana_mint
        self.rpc = rpc or _rpc
        self.seen: set[str] = {r.tx for r in funding.requests.values() if r.tx}
        self.last_evm_block: int | None = None
        self.errors: dict[str, str] = {}

    @classmethod
    def from_env(cls, funding: Funding) -> "Watcher":
        get = lambda key: os.environ.get(key, "").strip()  # noqa: E731
        return cls(funding, solana_rpc=get("CLAUSE_FUNDING_SOLANA_RPC"), evm_rpc=get("CLAUSE_FUNDING_EVM_RPC"),
                   evm_usdc=get("CLAUSE_FUNDING_EVM_USDC"),
                   solana_mint=get("CLAUSE_FUNDING_SOLANA_USDC") or SOLANA_USDC_MINT)

    @property
    def active(self) -> bool:
        d = self.funding.destinations
        return bool((self.solana_rpc and d.solana) or (self.evm_rpc and d.evm and self.evm_usdc))

    def describe(self) -> dict[str, Any]:
        return {"solana": bool(self.solana_rpc and self.funding.destinations.solana),
                "evm": bool(self.evm_rpc and self.funding.destinations.evm and self.evm_usdc),
                "errors": dict(self.errors)}

    # -- one pass ----------------------------------------------------------

    def run(self) -> int:
        """One look at each chain; returns how many requests were confirmed."""
        n = 0
        if self.solana_rpc and self.funding.destinations.solana:
            try:
                n += self._solana()
                self.errors.pop("solana", None)
            except Exception as error:  # the watcher failing is a state the operator sees
                self.errors["solana"] = str(error)[:200]
        if self.evm_rpc and self.funding.destinations.evm and self.evm_usdc:
            try:
                n += self._evm()
                self.errors.pop("evm", None)
            except Exception as error:
                self.errors["evm"] = str(error)[:200]
        return n

    def _linked(self, sender: str, method: str, amount: float, tx: str,
                waiting: list[FundingRequest]) -> bool:
        """A deposit from a wallet somebody linked to their account: matched
        to their waiting request for this chain if they made one, credited
        without one otherwise."""
        links = self.funding.links
        account = links.account_of(method, sender) if (links is not None and sender) else None
        if account is None:
            return False
        req = next((r for r in waiting if r.account == account and r.open), None)
        chain = "solana" if method == "solana" else "ethereum"
        if req is not None:
            self._credit(req, amount, tx, chain)
        else:
            self.seen.add(tx)
            self.funding.unannounced(account, method, amount, sender=sender, tx=tx, by=f"{chain} watcher")
        return True

    def _credit(self, req: FundingRequest, amount: float, tx: str, chain: str) -> None:
        self.seen.add(tx)
        self.funding.confirm(req.request_id, amount, by=f"{chain} watcher", note=f"seen on chain: {tx[:40]}", tx=tx)

    # Solana: signatures for the receiving address, then each transaction's
    # memo and the USDC balance change of the receiving owner.
    def _solana(self) -> int:
        to = self.funding.destinations.solana
        waiting = [r for r in self.funding.waiting() if r.method == "solana"]
        if not waiting and self.funding.links is None:
            return 0
        sigs = self.rpc(self.solana_rpc, "getSignaturesForAddress", [to, {"limit": 40}]) or []
        n = 0
        for item in sigs:
            sig = item.get("signature")
            if not sig or sig in self.seen or item.get("err"):
                continue
            tx = self.rpc(self.solana_rpc, "getTransaction",
                          [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
            if not tx:
                continue
            self.seen.add(sig)
            amount = _solana_usdc_in(tx, to, self.solana_mint)
            memo = _solana_memo(tx)
            if amount <= 0:
                continue
            found = REFERENCE.search(memo or "")
            req = next((r for r in waiting if found and r.reference == found.group(0) and r.open), None)
            sender = _solana_sender(tx)
            if req is None:
                req = next((r for r in waiting if r.sender and r.sender == sender and r.open), None)
            if req is None and not self._linked(sender, "solana", amount, sig, waiting):
                continue
            if req is not None:
                self._credit(req, amount, sig, "solana")
            n += 1
        return n

    # Ethereum style: Transfer logs of the USDC contract into the receiving
    # address since the last block seen; matched by the sending address.
    def _evm(self) -> int:
        to = self.funding.destinations.evm.lower()
        waiting = [r for r in self.funding.waiting() if r.method == "evm"]
        if not waiting and self.funding.links is None:
            return 0
        head = int(self.rpc(self.evm_rpc, "eth_blockNumber", []), 16)
        start = self.last_evm_block + 1 if self.last_evm_block is not None else max(0, head - 5000)
        if start > head:
            return 0
        logs = self.rpc(self.evm_rpc, "eth_getLogs", [{
            "fromBlock": hex(start), "toBlock": hex(head), "address": self.evm_usdc,
            "topics": [TRANSFER_TOPIC, None, "0x" + to[2:].rjust(64, "0")],
        }]) or []
        n = 0
        for log in logs:
            tx = f"{log.get('transactionHash', '')}:{log.get('logIndex', '')}"
            if tx in self.seen:
                continue
            self.seen.add(tx)
            sender = "0x" + str(log["topics"][1])[-40:]
            amount = int(str(log.get("data", "0x0")), 16) / 10 ** USDC_DECIMALS
            req = next((r for r in waiting if r.sender and r.sender.lower() == sender.lower() and r.open), None)
            if amount <= 0:
                continue
            if req is None and not self._linked(sender, "evm", amount, tx, waiting):
                continue
            if req is not None:
                self._credit(req, amount, tx, "ethereum")
            n += 1
        self.last_evm_block = head
        return n


def _solana_usdc_in(tx: dict[str, Any], owner: str, mint: str) -> float:
    meta = tx.get("meta") or {}
    def balance(rows: list[dict[str, Any]]) -> float:
        total = 0.0
        for row in rows or []:
            if row.get("owner") == owner and row.get("mint") == mint:
                total += float((row.get("uiTokenAmount") or {}).get("uiAmount") or 0.0)
        return total
    return round(balance(meta.get("postTokenBalances")) - balance(meta.get("preTokenBalances")), 6)


def _solana_memo(tx: dict[str, Any]) -> str:
    message = (tx.get("transaction") or {}).get("message") or {}
    for ins in message.get("instructions") or []:
        if ins.get("program") == "spl-memo":
            parsed = ins.get("parsed")
            return parsed if isinstance(parsed, str) else json.dumps(parsed)
    for line in (tx.get("meta") or {}).get("logMessages") or []:
        if "Memo" in line:
            return line
    return ""


def _solana_sender(tx: dict[str, Any]) -> str:
    keys = ((tx.get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    if not keys:
        return ""
    first = keys[0]
    return first.get("pubkey", "") if isinstance(first, dict) else str(first)
