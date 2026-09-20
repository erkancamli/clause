"""Keeping the book across restarts.

Until this module the protocol kept everything in memory: a restart, a deploy
or a crash emptied the pool, forgot every policy and every settlement, and
signed every company out of its approval. A protocol whose whole promise is a
record anyone can check cannot lose its record.

What is kept
------------
Everything that is a fact about the world rather than a cache of one:

    pool        balance, shares, providers, every policy, the full ledger
    wallets     every address, its balance and every movement
    chain       height, clock, and every settlement it has performed
    registry    every company, its licences, and every review decision
    identity    registered public keys, the extra devices allowed to sign
                for an address, which address each Privy account acts as, and
                the secret that signs read sessions

What is not: prices (recomputed), live feeds (refetched), open challenges and
operator sessions (short lived by design), and the simulated world's readings,
which are rebuilt; an open policy is armed again on the chain at startup and
its source comes back with it.

How
---
One SQLite file, written in a single transaction per checkpoint, so the file
is always one consistent moment and never half of two. A checkpoint follows
every request that changes something and runs every few seconds while the
chain settles on its own, and once more on shutdown. SQLite in WAL mode makes
each one cheap; the book is small next to what SQLite is built for.

Objects are stored as tagged JSON rather than pickled. A pickle breaks the day
a class changes shape; this reads an old file into a new class by name, drops
fields the class no longer has and lets new fields take their defaults.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .protocol.policy import PolicyStatus

logger = logging.getLogger("clause.store")

FORMAT = 1


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


# Only classes from the protocol's own packages are ever built from a file.
_ALLOWED = ("clause.protocol.", "clause.perils.base", "clause.chain.world")


def _tag(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def _class(tag: str) -> type:
    import importlib

    module, _, name = tag.partition(":")
    if not module.startswith(_ALLOWED) and module not in _ALLOWED:
        raise ValueError(f"refusing to build {tag} from a stored file")
    obj = importlib.import_module(module)
    for part in name.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, type) or not (dataclasses.is_dataclass(obj) or issubclass(obj, enum.Enum)):
        raise ValueError(f"{tag} is not a stored kind")
    return obj


def encode(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return {"__e": _tag(type(value)), "v": value.value}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out: dict[str, Any] = {"__t": _tag(type(value))}
        for f in dataclasses.fields(value):
            out[f.name] = encode(getattr(value, f.name))
        return out
    if isinstance(value, frozenset):
        return {"__fs": sorted((encode(v) for v in value), key=repr)}
    if isinstance(value, tuple):
        return {"__tu": [encode(v) for v in value]}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, float) and value != value:
        return None
    return value


def decode(value: Any) -> Any:
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if "__e" in value:
        return _class(value["__e"])(value["v"])
    if "__fs" in value:
        return frozenset(decode(v) for v in value["__fs"])
    if "__tu" in value:
        return tuple(decode(v) for v in value["__tu"])
    if "__t" in value:
        cls = _class(value["__t"])
        names = {f.name for f in dataclasses.fields(cls) if f.init}
        kwargs = {k: decode(v) for k, v in value.items() if k in names}
        return cls(**kwargs)
    return {k: decode(v) for k, v in value.items()}


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def default_path() -> Path | None:
    """Where the book lives: CLAUSE_STATE_DIR, else nowhere (memory only)."""
    directory = os.environ.get("CLAUSE_STATE_DIR", "").strip()
    return Path(directory) / "clause.sqlite" if directory else None


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("CREATE TABLE IF NOT EXISTS docs (kind TEXT, id TEXT, data TEXT, PRIMARY KEY(kind, id))")
        self._db.execute("CREATE TABLE IF NOT EXISTS log (kind TEXT, seq INTEGER, data TEXT, PRIMARY KEY(kind, seq))")
        self._db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        self.saved_at: float | None = None
        self._prints: dict[str, dict[str, Any]] = {}
        self._lengths: dict[str, int] = {}

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- reading ------------------------------------------------------------

    def empty(self) -> bool:
        row = self._db.execute("SELECT value FROM meta WHERE key='format'").fetchone()
        return row is None

    def meta(self, key: str, default: Any = None) -> Any:
        row = self._db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def docs(self, kind: str) -> dict[str, Any]:
        rows = self._db.execute("SELECT id, data FROM docs WHERE kind=?", (kind,)).fetchall()
        return {id_: decode(json.loads(data)) for id_, data in rows}

    def log(self, kind: str) -> list[Any]:
        rows = self._db.execute("SELECT data FROM log WHERE kind=? ORDER BY seq", (kind,)).fetchall()
        return [decode(json.loads(data)) for (data,) in rows]

    def count(self, kind: str) -> int:
        return self._db.execute("SELECT COUNT(*) FROM log WHERE kind=?", (kind,)).fetchone()[0]

    # -- writing ------------------------------------------------------------

    def write(self, *, meta: dict[str, Any], docs: dict[str, dict[str, str]],
              logs: dict[str, list[str]]) -> dict[str, int]:
        """One consistent moment, written incrementally.

        ``docs`` maps a kind to its items, each already encoded to its JSON
        text by the caller while it held the protocol's locks (see
        checkpoint), so what lands here is one consistent moment and nothing
        can change under the encoder. The text is its own fingerprint: only
        an item whose text differs from the last write is written, so a book
        of a hundred thousand settled policies costs nothing to keep once
        written, and no change to any field can go unsaved. Logs are only
        ever appended to.
        """
        written: dict[str, int] = {}
        with self._lock:
            cur = self._db.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                for key, value in meta.items():
                    cur.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))
                for kind, items in docs.items():
                    seen = self._prints.setdefault(kind, {})
                    rows = []
                    for id_, text in items.items():
                        if seen.get(id_) == text:
                            continue
                        rows.append((kind, id_, text))
                        seen[id_] = text
                    gone = [id_ for id_ in seen if id_ not in items]
                    for id_ in gone:
                        cur.execute("DELETE FROM docs WHERE kind=? AND id=?", (kind, id_))
                        seen.pop(id_, None)
                    cur.executemany("INSERT OR REPLACE INTO docs VALUES (?, ?, ?)", rows)
                    written[kind] = len(rows)
                for kind, entries in logs.items():
                    have = self._lengths.get(kind)
                    if have is None:
                        have = cur.execute("SELECT COUNT(*) FROM log WHERE kind=?", (kind,)).fetchone()[0]
                    fresh = entries[have:]
                    cur.executemany(
                        "INSERT INTO log VALUES (?, ?, ?)",
                        [(kind, have + i, text) for i, text in enumerate(fresh)],
                    )
                    self._lengths[kind] = have + len(fresh)
                    written[kind] = len(fresh)
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                self._prints.clear()
                self._lengths.clear()
                raise
        self.saved_at = time.time()
        return written

    def remember(self, kind: str, items: dict[str, Any]) -> None:
        """After a restore: these are already on disk as they are."""
        self._prints[kind] = {str(k): _text(v) for k, v in items.items()}


# ---------------------------------------------------------------------------
# The protocol's state, in and out
# ---------------------------------------------------------------------------


def _pem(key: Any) -> str:
    from .protocol.auth import _b64, raw_public_key

    return _b64(raw_public_key(key))


def _text(item: Any) -> str:
    """An item as it is written: its JSON text, which is also its fingerprint."""
    return json.dumps(encode(item), separators=(",", ":"), sort_keys=True)


KINDS = ("policy", "provider", "wallet", "carrier", "key", "signers", "privy",
         "application", "payout_pref", "payout_order", "partner", "mandate", "funding",
         "link", "instruction", "asset", "rule")


def _books(payouts: Any, partners: Any, mandates: Any,
           applications: Any = None, funding: Any = None, links: Any = None,
           instructions: Any = None, assets: Any = None, pipeline: Any = None) -> dict[str, dict[str, Any]]:
    """The newer books, each a plain dict of stored kinds, when present."""
    out: dict[str, dict[str, Any]] = {}
    if pipeline is not None:
        # The operator's policy entries: what is refused, why, by whom.
        out["rule"] = pipeline.entries
    if applications is not None:
        out["application"] = applications.applications
    if funding is not None:
        out["funding"] = funding.requests
    if links is not None:
        out["link"] = links.links
    if instructions is not None:
        out["instruction"] = instructions.instructions
    if assets is not None:
        out["asset"] = assets.assets
    if payouts is not None:
        out["payout_pref"] = payouts.preferences
        out["payout_order"] = payouts.orders
    if partners is not None:
        out["partner"] = partners.partners
    if mandates is not None:
        out["mandate"] = mandates.mandates
    return out


def checkpoint(store: Store, *, pool: Any, wallets: Any, chain: Any, registry: Any,
               auth: Any, accounts: Any, payouts: Any = None, partners: Any = None,
               mandates: Any = None, applications: Any = None, funding: Any = None,
               links: Any = None, instructions: Any = None, assets: Any = None,
               pipeline: Any = None) -> None:
    with pool.lock, chain.lock:
        meta = {
            "format": FORMAT,
            "pool": {
                "balance": pool.balance, "total_shares": pool.total_shares,
                "premiums_earned": pool.premiums_earned, "claims_paid": pool.claims_paid,
                "refunds_paid": pool.refunds_paid,
                "tranches": {n: {"balance": t.balance, "shares": t.shares}
                             for n, t in pool.tranches.items()},
            },
            "chain": {"height": chain.height, "timestamp": chain.timestamp, "genesis": chain.genesis},
            "session_secret": auth._secret.hex(),
        }
        # Encoded here, under the locks, so the snapshot is one moment. Each
        # book is copied before it is walked: the money lock covers the pool
        # and the chain, but a key being registered or an account being
        # joined on a request thread holds no lock, and a dict that grows
        # while it is iterated raises and loses the whole save. The copy is
        # one atomic step; the walk is over something nobody else holds.
        books: dict[str, dict[str, Any]] = {
            "policy": dict(pool.policies), "provider": dict(pool.providers), "wallet": dict(wallets.accounts),
            "carrier": dict(registry.carriers),
            "key": {a: _pem(k) for a, k in dict(auth.keys).items()},
            "signers": {a: [_pem(k) for k in list(ks)] for a, ks in dict(auth.signers).items()},
            "privy": dict(accounts._by_user),
        }
        books.update({kind: dict(book) for kind, book in
                      _books(payouts, partners, mandates, applications, funding, links, instructions, assets, pipeline).items()})
        docs = {kind: {str(id_): _text(item) for id_, item in book.items()} for kind, book in books.items()}
        logs = {"ledger": [_text(e) for e in list(pool.ledger)],
                "settlement": [_text(e) for e in list(chain.settlements)]}
    store.write(meta=meta, docs=docs, logs=logs)


def restore(store: Store, *, pool: Any, wallets: Any, chain: Any, registry: Any,
            auth: Any, accounts: Any, payouts: Any = None, partners: Any = None,
            mandates: Any = None, applications: Any = None, funding: Any = None,
            links: Any = None, instructions: Any = None, assets: Any = None,
            pipeline: Any = None) -> dict[str, int]:
    """Put a saved book back. Returns counts, for the log line."""
    from .protocol.auth import load_public_key

    saved_format = int(store.meta("format", 1) or 1)
    if saved_format > FORMAT:
        raise RuntimeError(
            f"the book at {store.path} was written by a newer build (format {saved_format}, "
            f"this build reads {FORMAT}); install that build or move the file aside")

    p = store.meta("pool", {})
    pool.balance = float(p.get("balance", 0.0))
    pool.total_shares = float(p.get("total_shares", 0.0))
    pool.premiums_earned = float(p.get("premiums_earned", 0.0))
    pool.claims_paid = float(p.get("claims_paid", 0.0))
    pool.refunds_paid = float(p.get("refunds_paid", 0.0))
    # A book saved before tranches held everything as senior capital, which is
    # what the two lines above have just rebuilt; a newer one says exactly.
    for name, layer in (p.get("tranches") or {}).items():
        if name in pool.tranches:
            pool.tranches[name].balance = float(layer.get("balance", 0.0))
            pool.tranches[name].shares = float(layer.get("shares", 0.0))
    pool.policies = store.docs("policy")
    pool.providers = store.docs("provider")
    pool.ledger = store.log("ledger")

    wallets.accounts = store.docs("wallet")
    registry.carriers = store.docs("carrier")

    for address, encoded in store.docs("key").items():
        try:
            auth.keys[address] = load_public_key(encoded)
        except Exception:  # a key this build cannot read is skipped, not fatal
            logger.warning("could not restore the key for %s", address)
    for address, encoded_list in store.docs("signers").items():
        keys = []
        for encoded in encoded_list:
            try:
                keys.append(load_public_key(encoded))
            except Exception:
                logger.warning("could not restore a signer for %s", address)
        auth.signers[address] = keys
    secret = store.meta("session_secret")
    if secret:
        auth._secret = bytes.fromhex(secret)
    accounts._by_user.update(store.docs("privy"))

    c = store.meta("chain", {})
    with chain.lock:
        if c:
            chain.height = int(c.get("height", chain.height))
            chain.timestamp = float(c.get("timestamp", chain.timestamp))
            chain.genesis = float(c.get("genesis", chain.genesis))
        chain.settlements = store.log("settlement")
    store.remember("policy", pool.policies)
    store.remember("provider", pool.providers)
    store.remember("wallet", wallets.accounts)
    store.remember("carrier", registry.carriers)
    store.remember("key", {a: _pem(k) for a, k in auth.keys.items()})
    store.remember("signers", {a: [_pem(k) for k in ks] for a, ks in auth.signers.items()})
    store.remember("privy", accounts._by_user)
    for kind, book in _books(payouts, partners, mandates, applications, funding, links, instructions, assets, pipeline).items():
        book.clear()
        book.update(store.docs(kind))
        store.remember(kind, book)
    migrated = migrate_legacy_addresses(pool=pool, wallets=wallets, chain=chain, registry=registry,
                                        auth=auth, accounts=accounts, payouts=payouts, partners=partners,
                                        mandates=mandates, applications=applications, funding=funding,
                                        links=links, instructions=instructions, assets=assets,
                                        pipeline=pipeline)
    if migrated:
        # Re-fingerprinted so the next checkpoint writes every rewritten
        # record under its new id and drops the old ones.
        store.remember("policy", pool.policies)
        store.remember("provider", pool.providers)
        store.remember("wallet", wallets.accounts)
        store.remember("carrier", registry.carriers)
        store.remember("key", {a: _pem(k) for a, k in auth.keys.items()})
        store.remember("signers", {a: [_pem(k) for k in ks] for a, ks in auth.signers.items()})
        store.remember("privy", accounts._by_user)
        for kind, book in _books(payouts, partners, mandates, applications, funding, links, instructions, assets, pipeline).items():
            store.remember(kind, book)
        logger.info("rewrote %s legacy 0x addresses in Rialo form", migrated)
    armed = 0
    reinstated = reinstate_lapsed_by_the_demo_clock(pool)
    for policy in pool.policies.values():
        if not policy.is_open:
            continue
        try:
            if (policy.metadata or {}).get("provisional"):
                chain.resume_provisional(policy)
            else:
                chain.register(policy)
            armed += 1
        except Exception:  # one unreadable policy must not stop the book
            logger.exception("could not arm %s again", policy.policy_id)
    return {"policies": len(pool.policies), "armed": armed, "wallets": len(wallets.accounts),
            "carriers": len(registry.carriers), "settlements": len(chain.settlements),
            "reinstated": reinstated}


LAPSE_NOTE = "the term ended without the index triggering"


def reinstate_lapsed_by_the_demo_clock(pool: Any, *, now: float | None = None) -> int:
    """Put back in force the cover a person bought that an earlier build
    closed by the demonstration's clock.

    Before cover bought by a person ran on the real clock, the world's
    acceleration lapsed it minutes after approval, with a year still to run
    on its document. Such a policy is recognisable: bought with a declared
    interest, lapsed on the untriggered note, and not yet at the end of its
    term by the clock. It goes back to active, the record says so, and the
    chain arms it again with the rest. The settlement that closed it stays
    in the chain's history; the note on the policy points at it.
    """
    now = time.time() if now is None else now
    count = 0
    for policy in pool.policies.values():
        meta = policy.metadata or {}
        if (policy.status.value == "lapsed" and meta.get("interest")
                and policy.settlement_note == LAPSE_NOTE and policy.ends_at > now
                and not meta.get("reinstated")):
            policy.status = PolicyStatus.ACTIVE
            policy.settlement_note = ""
            meta["reinstated"] = {"at": now, "lapsed_at": policy.settled_at,
                                  "why": "closed by the demonstration clock before its term ended; put back in force"}
            policy.settled_at = None
            policy.metadata = meta
            count += 1
    return count


class Keeper:
    """Checkpoints on demand and on a timer, never two at once."""

    def __init__(self, store: Store, save: Any, *, every: float = 5.0) -> None:
        self.store = store
        self._save = save
        self.every = every
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.failures = 0

    def save(self) -> None:
        with self._lock:
            try:
                self._save()
            except Exception as error:  # a failed save is logged and retried
                self.failures += 1
                logger.error("could not save the book: %s", error)

    def start(self) -> None:
        def run() -> None:
            while not self._stop.wait(self.every):
                self.save()
        self._thread = threading.Thread(target=run, name="clause-keeper", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.save()


# ---------------------------------------------------------------------------
# Addresses written in the old 0x form become Rialo shaped
# ---------------------------------------------------------------------------

_LEGACY = re.compile(r"0x[0-9a-fA-F]{40}")


def legacy_to_rialo(old: str) -> str:
    """The Rialo shaped address an old 0x address becomes: deterministic, so
    every restart maps it the same way and a device key registered under
    the old address (auth.register looks keys up by their bytes) lands on
    the same account."""
    from .protocol.address import from_material
    return from_material(("legacy:" + old.lower()).encode())


def migrate_legacy_addresses(*, pool: Any, wallets: Any, chain: Any, registry: Any, auth: Any,
                             accounts: Any, payouts: Any = None, partners: Any = None,
                             mandates: Any = None, applications: Any = None, funding: Any = None,
                             links: Any = None, instructions: Any = None, assets: Any = None,
                             pipeline: Any = None) -> int:
    """Rewrite every 0x address in the restored book into Rialo form.

    Walks every record, dict key and string, replacing each old address (as
    a whole value, or inside a longer string such as a provider key) with
    its mapped form. Runs on every restore and is idempotent: a book with
    no 0x addresses is untouched.
    """
    found: set[str] = set()
    roots: list[Any] = [pool.policies, pool.providers, pool.ledger, wallets.accounts, registry.carriers,
                        auth.keys, auth.signers, accounts._by_user, chain.settlements]
    roots += list(_books(payouts, partners, mandates, applications, funding, links, instructions, assets, pipeline).values())

    # Only an address that is an account here is rewritten: one with a
    # wallet, a key, a Privy user or a policy. An Ethereum address somebody
    # gave as a payout destination, a deposit's sender or a linked wallet is
    # the same shape and must stay exactly as they wrote it.
    def note(value: Any) -> None:
        if isinstance(value, str) and _LEGACY.fullmatch(value):
            found.add(value.lower())

    for key in list(wallets.accounts) + list(auth.keys) + list(auth.signers) + list(accounts._by_user.values()):
        note(key)
    for policy in pool.policies.values():
        note(getattr(policy, "holder", None))
    for key in pool.providers:
        if isinstance(key, str):
            for m in _LEGACY.finditer(key):
                found.add(m.group(0).lower())
    if not found:
        return 0
    mapping = {old: legacy_to_rialo(old) for old in found}

    def fix(text: str) -> str:
        return _LEGACY.sub(lambda m: mapping.get(m.group(0).lower(), m.group(0)), text)

    def rewrite(value: Any, depth: int = 0) -> Any:
        if depth > 12 or isinstance(value, enum.Enum):
            return value
        if isinstance(value, str):
            return fix(value)
        if isinstance(value, dict):
            items = [(rewrite(k, depth + 1), rewrite(v, depth + 1)) for k, v in value.items()]
            value.clear()
            value.update(items)
            return value
        if isinstance(value, list):
            value[:] = [rewrite(v, depth + 1) for v in value]
            return value
        if isinstance(value, tuple):
            return tuple(rewrite(v, depth + 1) for v in value)
        if isinstance(value, (set, frozenset)):
            return type(value)(rewrite(v, depth + 1) for v in value)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            for f in dataclasses.fields(value):
                try:
                    current = getattr(value, f.name)
                    new = rewrite(current, depth + 1)
                    if new is not current or isinstance(new, str):
                        object.__setattr__(value, f.name, new)
                except (AttributeError, TypeError):
                    pass
            return value
        return value

    for root in roots:
        rewrite(root)
    return len(mapping)
