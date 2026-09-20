"""The anchor: what the protocol tells a public chain, and the record of it.

Three kinds of thing go out, each as an *intent* first: a token to mint
when a policy is issued, a token to burn when one is cancelled, a
settlement to record when the chain settles; and, on a timer, the root of
the book. An intent is written the moment the thing happens, in the book,
so a restart or a node that is down loses nothing: the sender walks the
pending intents every cycle and sends what it can, then reads receipts for
what it sent. Without a key and an RPC endpoint the service still builds
roots and keeps intents, marked as not sent, so the proof page and the
policy page say what would be on the chain and the day the key is set
everything is sent in order.

The signer is one hot key with the issuer role on both contracts and
nothing else: it can mint, burn, settle and anchor, and cannot change who
the issuer is. That is the owner's, kept elsewhere.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import merkle
from .rpc import Rpc, RpcError, int_hex
from .signing import address_of_key, checksum, contract_address, encode_call, private_key_of, sign_1559, to_address, tx_hash

logger = logging.getLogger("clause.anchor")

CHAINS: dict[int, dict[str, str]] = {
    84532: {"name": "Base Sepolia", "explorer": "https://sepolia.basescan.org", "rpc": "https://sepolia.base.org"},
    8453: {"name": "Base", "explorer": "https://basescan.org", "rpc": "https://mainnet.base.org"},
    11155111: {"name": "Sepolia", "explorer": "https://sepolia.etherscan.io", "rpc": ""},
}
KINDS = ("mint", "burn", "settle", "root")
SETTLEMENT_CODES = {"paid": 2, "lapsed": 3, "expired": 4}
KEEP_LEAVES = 3           # recent roots that keep their leaf list, for proofs
SEND_PER_CYCLE = 25
GAS_FALLBACK = {"mint": 260_000, "burn": 90_000, "settle": 90_000, "root": 120_000}
CALLS = {
    "mint": "mint(address,string,bytes32,bytes32)",
    "burn": "burn(string,string)",
    "settle": "settle(string,uint8,uint256,bytes32,uint64)",
    "root": "anchor(bytes32,uint64,uint64)",
}
ARTIFACTS = Path(__file__).with_name("artifacts.json")


def artifacts() -> dict[str, Any]:
    with ARTIFACTS.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass(slots=True)
class AnchorIntent:
    intent_id: str
    kind: str
    policy_id: str
    created_at: float
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"        # pending | sent | confirmed | failed
    tx_hash: str | None = None
    sent_at: float | None = None
    block: int | None = None
    error: str = ""
    attempts: int = 0

    def to_dict(self, *, leaves: bool = False) -> dict[str, Any]:
        payload = dict(self.payload)
        if not leaves:
            payload.pop("leaves", None)
        return {"intent_id": self.intent_id, "kind": self.kind, "policy_id": self.policy_id,
                "created_at": self.created_at, "payload": payload, "status": self.status,
                "tx_hash": self.tx_hash, "sent_at": self.sent_at, "block": self.block,
                "error": self.error, "attempts": self.attempts}


@dataclass(slots=True)
class AnchorConfig:
    chain_id: int = 84532
    rpc_url: str = ""
    private_key: str = ""
    policy_contract: str = ""
    book_contract: str = ""
    every: float = 600.0

    @classmethod
    def from_env(cls) -> "AnchorConfig":
        def env(name: str) -> str:
            return os.environ.get(name, "").strip()
        chain = env("CLAUSE_ANCHOR_CHAIN_ID")
        every = env("CLAUSE_ANCHOR_EVERY")
        return cls(chain_id=int(chain) if chain.isdigit() else 84532,
                   rpc_url=env("CLAUSE_ANCHOR_RPC") or (CHAINS.get(int(chain) if chain.isdigit() else 84532, {}).get("rpc", "") if env("CLAUSE_ANCHOR_KEY") else ""),
                   private_key=env("CLAUSE_ANCHOR_KEY"),
                   policy_contract=env("CLAUSE_ANCHOR_POLICY"),
                   book_contract=env("CLAUSE_ANCHOR_BOOK"),
                   every=float(every) if every else 600.0)

    @property
    def chain(self) -> dict[str, str]:
        return CHAINS.get(self.chain_id, {"name": f"chain {self.chain_id}", "explorer": "", "rpc": ""})

    @property
    def live(self) -> bool:
        return bool(self.rpc_url and self.private_key and self.policy_contract and self.book_contract)

    @property
    def mode(self) -> str:
        return "live" if self.live else "record"


class Anchor:
    def __init__(self, config: AnchorConfig | None = None, *, pool: Any, links: Any = None,
                 rpc: Rpc | None = None, synthetic: Any = None) -> None:
        self.config = config or AnchorConfig()
        self.pool = pool
        self.links = links
        # Policies the demonstration writes for itself are in the root, since
        # the root is the book as it is, but get no token, burn or settlement
        # of their own: a public chain is for cover people bought.
        self.synthetic = synthetic or (lambda policy: bool((policy.metadata or {}).get("synthetic")))
        self.intents: dict[str, AnchorIntent] = {}
        self.lock = threading.RLock()
        self._key = private_key_of(self.config.private_key) if self.config.private_key else None
        self.signer = address_of_key(self._key) if self._key is not None else None
        self.rpc = rpc or (Rpc(self.config.rpc_url) if self.config.rpc_url else None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_run_at: float | None = None
        self.last_error = ""
        self.balance_wei: int | None = None

    # -- what happens in the protocol ------------------------------------------

    def _add(self, kind: str, policy_id: str, payload: dict[str, Any], now: float | None = None) -> AnchorIntent:
        intent = AnchorIntent(intent_id="ANC-" + secrets.token_hex(6).upper(), kind=kind, policy_id=policy_id,
                              created_at=time.time() if now is None else now, payload=payload)
        with self.lock:
            self.intents[intent.intent_id] = intent
        return intent

    def recipient(self, holder: str) -> tuple[str, bool]:
        """Where a policy's token goes: the holder's linked Ethereum wallet
        if they linked one, else the signer's own address, held for them.
        The second value says which."""
        if self.links is not None:
            try:
                linked = self.links.wallets_of(holder, "evm")
            except Exception:
                linked = []
            if linked:
                return checksum(linked[0]), False
        return (self.signer or "0x" + "00" * 20), True

    def on_token(self, event: str, policy: Any) -> AnchorIntent | None:
        if self.synthetic(policy):
            return None
        token = (policy.metadata or {}).get("token") or {}
        if event == "minted":
            if any(i.kind == "mint" and i.policy_id == policy.policy_id for i in self.intents.values()):
                return None
            to, custodial = self.recipient(policy.holder)
            return self._add("mint", policy.policy_id, {
                "to": to, "custodial": custodial, "holder_hash": merkle.text_hash(policy.holder),
                "terms_hash": token.get("terms_hash") or "0x" + "00" * 32})
        if event == "burned":
            if any(i.kind == "burn" and i.policy_id == policy.policy_id for i in self.intents.values()):
                return None
            return self._add("burn", policy.policy_id, {"reason": token.get("burned_because") or "cancelled"})
        return None

    def backfill(self) -> int:
        """Mint intents for tokens that exist but were never told to the
        chain: the policies from before anchoring. A token burned before then
        was never minted on the chain, so there is nothing to burn; and
        settlements are told from now on, not the seeded past."""
        have = {(i.kind, i.policy_id) for i in self.intents.values()}
        added = 0
        for policy in list(self.pool.policies.values()):
            token = (policy.metadata or {}).get("token")
            if not token or token.get("burned_at") or ("mint", policy.policy_id) in have or self.synthetic(policy):
                continue
            self.on_token("minted", policy)
            added += 1
        return added

    def on_settlement(self, settlement: Any) -> AnchorIntent | None:
        code = SETTLEMENT_CODES.get(getattr(settlement, "kind", ""), 0)
        policy = self.pool.policies.get(settlement.policy_id)
        if not code or policy is None or self.synthetic(policy):
            return None
        if any(i.kind == "settle" and i.policy_id == settlement.policy_id for i in self.intents.values()):
            return None
        return self._add("settle", settlement.policy_id, {
            "status": settlement.kind, "status_code": code,
            "payout_cents": int(round(float(settlement.amount) * 100)),
            "reading_hash": merkle.text_hash(settlement.signature),
            "when": int(settlement.at), "index_value": settlement.index_value,
        }, now=settlement.at)

    # -- the book's root --------------------------------------------------------

    def leaves(self) -> list[tuple[str, str]]:
        out = []
        for policy in list(self.pool.policies.values()):
            if "token" not in (policy.metadata or {}):
                continue
            out.append((policy.policy_id, merkle.leaf_of(merkle.leaf_fields(policy))))
        return sorted(out, key=lambda p: p[1])

    def roots(self) -> list[AnchorIntent]:
        return sorted((i for i in self.intents.values() if i.kind == "root"), key=lambda i: i.payload.get("epoch", 0))

    def latest_root(self) -> AnchorIntent | None:
        roots = self.roots()
        return roots[-1] if roots else None

    def anchor_root(self, now: float | None = None, *, force: bool = False) -> AnchorIntent | None:
        """A new root if the book changed since the last one."""
        now = time.time() if now is None else now
        leaves = self.leaves()
        root = merkle.root_of(l for _, l in leaves)
        last = self.latest_root()
        if last is not None and last.payload.get("root") == root and not force:
            return None
        epoch = max(int(now), (int(last.payload.get("epoch", 0)) + 1) if last else 0)
        intent = self._add("root", "", {"root": root, "count": len(leaves), "epoch": epoch, "leaves": leaves}, now=now)
        with self.lock:
            for old in self.roots()[:-KEEP_LEAVES]:
                old.payload.pop("leaves", None)
        return intent

    def proof(self, policy_id: str) -> dict[str, Any]:
        """A policy's place in the book: its leaf in the clear, the sibling
        hashes, the root, and where that root is on the chain."""
        policy = self.pool.policies.get(policy_id)
        if policy is None:
            raise KeyError(policy_id)
        fields = merkle.leaf_fields(policy)
        leaf_now = merkle.leaf_of(fields)
        for root in reversed(self.roots()):
            leaves = root.payload.get("leaves")
            if not leaves:
                continue
            entry = next((l for pid, l in leaves if pid == policy_id), None)
            if entry is None:
                continue
            siblings = merkle.proof_of([l for _, l in leaves], entry) or []
            return {
                "policy_id": policy_id, "fields": fields, "leaf": entry, "leaf_now": leaf_now,
                "current": entry == leaf_now, "proof": siblings,
                "root": root.payload["root"], "epoch": root.payload["epoch"], "count": root.payload["count"],
                "verified": merkle.verify(root.payload["root"], siblings, entry),
                "anchor": root.to_dict(), "tx_url": self.tx_url(root.tx_hash),
            }
        return {"policy_id": policy_id, "fields": fields, "leaf": None, "leaf_now": leaf_now, "current": False,
                "proof": [], "root": None, "epoch": None, "count": 0, "verified": False, "anchor": None, "tx_url": None}

    # -- sending ------------------------------------------------------------------

    def calldata(self, intent: AnchorIntent) -> tuple[str, bytes]:
        p = intent.payload
        if intent.kind == "mint":
            return self.config.policy_contract, encode_call(CALLS["mint"], [p["to"], intent.policy_id, p["holder_hash"], p["terms_hash"]])
        if intent.kind == "burn":
            return self.config.policy_contract, encode_call(CALLS["burn"], [intent.policy_id, p.get("reason", "cancelled")])
        if intent.kind == "settle":
            return self.config.book_contract, encode_call(CALLS["settle"], [intent.policy_id, p["status_code"], p["payout_cents"], p["reading_hash"], p["when"]])
        if intent.kind == "root":
            return self.config.book_contract, encode_call(CALLS["root"], [p["root"], p["count"], p["epoch"]])
        raise ValueError(intent.kind)

    def pending(self) -> list[AnchorIntent]:
        """Oldest first, so a burn never overtakes its mint and roots rise."""
        return sorted((i for i in self.intents.values() if i.status == "pending"), key=lambda i: (i.created_at, i.intent_id))

    def send(self, intent: AnchorIntent, *, nonce: int | None = None, fees: tuple[int, int] | None = None) -> AnchorIntent:
        assert self.rpc is not None and self._key is not None and self.signer
        to, data = self.calldata(intent)
        intent.attempts += 1
        try:
            nonce = self.rpc.nonce(self.signer) if nonce is None else nonce
            max_fee, tip = self.rpc.fees() if fees is None else fees
            try:
                gas = int(self.rpc.estimate_gas(sender=self.signer, to=to, data=data) * 1.25)
            except RpcError as error:
                # A call that would revert estimates as an error: say so and stop,
                # rather than pay for a failed transaction.
                message = str(error)
                if "revert" in message.lower() or "execution" in message.lower():
                    intent.status = "failed"
                    intent.error = message[:300]
                    return intent
                gas = GAS_FALLBACK[intent.kind]
            raw = sign_1559(self._key, chain_id=self.config.chain_id, nonce=nonce, max_priority_fee=tip,
                            max_fee=max_fee, gas=gas, to=to_address(to), value=0, data=data)
            sent = self.rpc.send_raw(raw)
            intent.tx_hash = sent if sent.startswith("0x") else tx_hash(raw)
            intent.status = "sent"
            intent.sent_at = time.time()
            intent.error = ""
        except RpcError as error:
            intent.error = str(error)[:300]
            if intent.attempts >= 20:
                intent.status = "failed"
        return intent

    def confirm(self, intent: AnchorIntent) -> AnchorIntent:
        assert self.rpc is not None and intent.tx_hash
        try:
            receipt = self.rpc.receipt(intent.tx_hash)
        except RpcError as error:
            intent.error = str(error)[:300]
            return intent
        if not receipt:
            # Dropped from the pool after a long silence: send it again.
            if intent.sent_at and time.time() - intent.sent_at > 1800:
                intent.status = "pending"
                intent.error = "not mined within thirty minutes; sending again"
            return intent
        if int_hex(receipt.get("status")) == 1:
            intent.status = "confirmed"
            intent.block = int_hex(receipt.get("blockNumber"))
            intent.error = ""
        else:
            intent.status = "failed"
            intent.error = "the transaction reverted"
        return intent

    def run_once(self, now: float | None = None) -> dict[str, Any]:
        """One cycle: a new root if the book moved, then what can be sent."""
        report = {"root": None, "sent": 0, "confirmed": 0, "failed": 0, "mode": self.config.mode}
        with self.lock:
            fresh = self.anchor_root(now)
            report["root"] = fresh.payload["root"] if fresh else None
            if not self.config.live or self.rpc is None:
                self.last_run_at = time.time()
                return report
            try:
                for intent in [i for i in self.intents.values() if i.status == "sent"]:
                    before = intent.status
                    self.confirm(intent)
                    if intent.status == "confirmed" and before != "confirmed":
                        report["confirmed"] += 1
                    elif intent.status == "failed":
                        report["failed"] += 1
                queue = self.pending()[:SEND_PER_CYCLE]
                if queue:
                    nonce = self.rpc.nonce(self.signer)  # type: ignore[arg-type]
                    fees = self.rpc.fees()
                    for intent in queue:
                        self.send(intent, nonce=nonce, fees=fees)
                        if intent.status == "sent":
                            nonce += 1
                            report["sent"] += 1
                        elif intent.status == "failed":
                            report["failed"] += 1
                        else:
                            break  # the node is not answering: try again next cycle
                try:
                    self.balance_wei = self.rpc.balance(self.signer)  # type: ignore[arg-type]
                except RpcError:
                    pass
                self.last_error = ""
            except RpcError as error:
                self.last_error = str(error)[:300]
                logger.warning("anchor cycle: %s", error)
            self.last_run_at = time.time()
        return report

    # -- the worker ---------------------------------------------------------------

    def start(self) -> None:
        def run() -> None:
            while not self._stop.wait(self.config.every):
                try:
                    self.run_once()
                except Exception:
                    logger.exception("anchor cycle failed")
        self._thread = threading.Thread(target=run, name="clause-anchor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.rpc is not None:
            self.rpc.close()

    # -- what the page shows ---------------------------------------------------------

    def tx_url(self, tx: str | None) -> str | None:
        explorer = self.config.chain.get("explorer")
        return f"{explorer}/tx/{tx}" if tx and explorer else None

    def address_url(self, address: str | None) -> str | None:
        explorer = self.config.chain.get("explorer")
        return f"{explorer}/address/{address}" if address and explorer else None

    def for_policy(self, policy_id: str) -> dict[str, Any]:
        rows = sorted((i for i in self.intents.values() if i.policy_id == policy_id), key=lambda i: i.created_at)
        return {"intents": [dict(i.to_dict(), tx_url=self.tx_url(i.tx_hash)) for i in rows],
                "token_url": (f"{self.config.chain['explorer']}/nft/{self.config.policy_contract}/{int(merkle.text_hash(policy_id), 16)}"
                              if self.config.policy_contract and self.config.chain.get("explorer") else None)}

    def status(self, *, recent: int = 12) -> dict[str, Any]:
        counts = {k: 0 for k in ("pending", "sent", "confirmed", "failed")}
        by_kind = {k: 0 for k in KINDS}
        for i in self.intents.values():
            counts[i.status] = counts.get(i.status, 0) + 1
            by_kind[i.kind] = by_kind.get(i.kind, 0) + 1
        last = self.latest_root()
        latest = sorted(self.intents.values(), key=lambda i: i.created_at, reverse=True)[:recent]
        return {
            "mode": self.config.mode,
            "chain": {"id": self.config.chain_id, "name": self.config.chain["name"], "explorer": self.config.chain.get("explorer", "")},
            "contracts": {"policy": self.config.policy_contract or None, "book": self.config.book_contract or None,
                          "policy_url": self.address_url(self.config.policy_contract or None),
                          "book_url": self.address_url(self.config.book_contract or None)},
            "signer": self.signer, "signer_url": self.address_url(self.signer),
            "balance_eth": (self.balance_wei / 1e18) if self.balance_wei is not None else None,
            "every": self.config.every, "last_run_at": self.last_run_at, "last_error": self.last_error,
            "counts": counts, "by_kind": by_kind,
            "last_root": dict(last.to_dict(), tx_url=self.tx_url(last.tx_hash)) if last else None,
            "recent": [dict(i.to_dict(), tx_url=self.tx_url(i.tx_hash)) for i in latest],
        }


# ---------------------------------------------------------------------------
# Deploying the two contracts, once, from a funded key
# ---------------------------------------------------------------------------


def deploy(rpc: Rpc, private_key: str, *, chain_id: int, base_uri: str = "",
           log: Any = print) -> dict[str, str]:
    """Deploy ClausePolicy and ClauseBook from this key and return their
    addresses. The key becomes owner and issuer of both; hand the owner role
    to a safer key afterwards with ``setOwner``."""
    key = private_key_of(private_key)
    sender = address_of_key(key)
    built = artifacts()
    got = rpc.chain_id()
    if got != chain_id:
        raise RuntimeError(f"the node is chain {got}, not {chain_id}")
    nonce = rpc.nonce(sender)
    out: dict[str, str] = {}
    for name in ("ClausePolicy", "ClauseBook"):
        code = bytes.fromhex(built[name]["bin"])
        max_fee, tip = rpc.fees()
        try:
            gas = int(rpc.estimate_gas(sender=sender, to=None, data=code) * 1.2)
        except RpcError:
            gas = 1_500_000
        raw = sign_1559(key, chain_id=chain_id, nonce=nonce, max_priority_fee=tip, max_fee=max_fee, gas=gas,
                        to=b"", value=0, data=code)
        address = contract_address(sender, nonce)
        sent = rpc.send_raw(raw)
        log(f"{name}: tx {sent}, address {address}")
        out[name] = address
        nonce += 1
    if base_uri:
        data = encode_call("setBaseURI(string)", [base_uri])
        max_fee, tip = rpc.fees()
        raw = sign_1559(key, chain_id=chain_id, nonce=nonce, max_priority_fee=tip, max_fee=max_fee, gas=120_000,
                        to=to_address(out["ClausePolicy"]), value=0, data=data)
        log(f"setBaseURI: tx {rpc.send_raw(raw)}")
    return out
