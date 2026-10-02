"""The one ending in the demonstration that returns money, after a restart.

The opening book silences a source on purpose. The drought policy written
against it can settle neither way: the index never reaches its trigger and
nobody is publishing a figure to say it has not, so when the deadline passes
the protocol returns the premium instead of keeping it. Watching that happen
is the only reason the case is in the book, and it is the ending a buyer most
wants to believe in, because it is the one where the protocol gives money
back for nothing.

Measured on live: expired 0, against 2003 lapsed. The chain's counts include
the settlements it has since forgotten, so zero means it had never happened,
not that the record had been flushed.

Being silent is not a reading, and readings are deliberately not kept: they
are rebuilt by arming each open policy again. So the source came back
speaking at the first restart. And because the opening book is written once,
on a book that does not yet exist, nothing ever silenced it again.
"""

from __future__ import annotations

import pathlib
import sys

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.store import Store

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_privy import verifier  # noqa: E402

QUIET = "api.meteo.example/v1/station/TR-SANLIURFA/cumulative"


def app_on(path):
    return create_app(trials=120, run_chain=False, seed_book=True,
                      settings=Settings(faucet=True), privy_verifier=verifier(),
                      store_path=path)


def chain_of(app):
    return app.state.chain


def test_the_opening_book_silences_a_source() -> None:
    app = app_on(None)
    with TestClient(app):
        reading = chain_of(app).readings.get(QUIET)

    assert reading is not None, "the opening book's quiet source is not there at all"
    assert reading.silent is True


def test_the_silence_is_written_down(tmp_path) -> None:
    path = tmp_path / "clause.sqlite"
    with TestClient(app_on(path)):
        pass

    kept = (Store(path).meta("chain", {}) or {}).get("silenced") or []

    assert QUIET in kept


def test_the_source_is_still_quiet_after_a_restart(tmp_path) -> None:
    """The finding. Without this the premium is never returned again."""
    path = tmp_path / "clause.sqlite"
    with TestClient(app_on(path)):
        pass

    app = app_on(path)
    with TestClient(app) as client:
        reading = chain_of(app).readings.get(QUIET)
        assert reading is not None, "the policy was not armed again"
        assert reading.silent is True, \
            "the source came back speaking, so nothing in the book will expire"
        # And the operator can see it from outside, which is how it was found.
        rows = [r for r in client.get("/api/chain").json()["pending"]
                if r["keys"] == [f"edge:{QUIET}"]]
        assert rows and rows[0]["source_silent"] is True


def test_a_quiet_source_whose_policy_is_gone_is_not_mourned(tmp_path) -> None:
    """A reference nothing reads any more cannot be silenced again, and that
    is not a failure: the policy it belonged to was settled and forgotten."""
    path = tmp_path / "clause.sqlite"
    with TestClient(app_on(path)):
        pass
    book = Store(path)
    chain_meta = dict(book.meta("chain", {}) or {})
    chain_meta["silenced"] = sorted(set(chain_meta["silenced"]) | {"api.nowhere.example/v1/x"})
    book.write(meta={"chain": chain_meta}, docs={}, logs={})

    app = app_on(path)
    with TestClient(app):
        # The real one is still silenced; the stray one is simply not found.
        assert chain_of(app).readings[QUIET].silent is True
        assert "api.nowhere.example/v1/x" not in chain_of(app).readings

def test_the_quiet_station_is_named_once() -> None:
    """The opening book and the stream of arrivals have to mean the same
    station, or only one of them silences anything and the other writes
    cover against a source that answers."""
    from clause.api.app import QUIET_STATION

    source = (pathlib.Path(__file__).resolve().parent.parent / "clause" / "api"
              / "app.py").read_text(encoding="utf-8")

    assert QUIET_STATION in QUIET
    # Written out as a literal nowhere but its own definition.
    assert source.count(f'"{QUIET_STATION}"') == 1, (
        "the station is spelled out more than once, so the two can drift")


def test_the_ending_that_returns_money_is_not_a_one_off() -> None:
    """The finding behind this one.

    The opening book silences a source and the policy written against it
    returns its premium at the deadline. That happens once. The book is
    written on a book that does not yet exist, the policy settles, the
    demonstration forgets it, and the register can never show that ending
    again: live reported expired 0 against 2003 lapsed. So the stream of
    arrivals that keeps the book turning over has to keep supplying it.
    """
    import asyncio
    import time

    from clause.api.app import QUIET_STATION, _arrivals
    from clause.chain import Chain, ChainConfig
    from clause.pricing import PricingEngine
    from clause.protocol import Pool
    from clause.protocol.wallet import Wallets

    async def watch() -> tuple[bool, bool]:
        pool = Pool(engine=PricingEngine(trials=40, seed=1))
        pool.deposit("lp", 40_000_000.0)
        chain = Chain(pool, ChainConfig(seed=1))
        # every=0 runs the stream as fast as it can price, which is what makes
        # this a test of the stream rather than of a sleep.
        stream = asyncio.create_task(
            _arrivals(pool, chain, Wallets(), [], every=0.0))
        try:
            began = time.monotonic()
            while time.monotonic() - began < 30:
                await asyncio.sleep(0.1)
                if any(r.silent for r in chain.readings.values()):
                    break
        finally:
            stream.cancel()
        written = any(p.subject.get("station") == QUIET_STATION
                      for p in pool.policies.values())
        return any(r.silent for r in chain.readings.values()), written

    quiet, written = asyncio.run(watch())

    assert written, (
        "no arrival is ever written against the quiet station, so the ending "
        "where the premium comes back happens once and never again")
    assert quiet, (
        "the arrival is written but its source is never silenced, so it "
        "settles like any other and returns nobody anything")

