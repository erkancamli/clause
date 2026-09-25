"""What the protocol writes down about itself.

Nothing in the package ever configured logging, so every line it wrote fell
through to Python's last resort handler: WARNING, and the message with no
time, no level and no logger name. The service runs uvicorn at
``--log-level warning``, which reads like a setting for this protocol and is
not one. None of it was written anywhere.
"""

from __future__ import annotations

import logging

import pytest

from clause import telemetry


@pytest.fixture(autouse=True)
def restore_logging():
    logger = logging.getLogger("clause")
    was = (list(logger.handlers), logger.level, logger.propagate,
           telemetry._configured)
    yield
    logger.handlers, logger.level, logger.propagate = was[0], was[1], was[2]
    telemetry._configured = was[3]


def test_the_package_writes_at_info_by_default() -> None:
    """The lines this codebase writes at INFO are the record of what it did.
    A record kept at WARNING is a record of failures only."""
    assert telemetry.configure(force=True) == "INFO"
    assert logging.getLogger("clause.chain").isEnabledFor(logging.INFO)


def test_a_line_carries_the_time_the_level_and_who_said_it(caplog) -> None:
    telemetry.configure(force=True)
    handler = logging.getLogger("clause").handlers[0]
    record = logging.LogRecord("clause.chain", logging.INFO, __file__, 1,
                               "a settlement happened", None, None)
    line = handler.format(record)
    assert "clause.chain" in line
    assert "INFO" in line
    assert "a settlement happened" in line
    # A timestamp, which the last resort handler never printed.
    assert line[:4].isdigit()


def test_the_level_can_be_set_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("CLAUSE_LOG_LEVEL", "debug")
    assert telemetry.configure(force=True) == "DEBUG"


def test_a_level_nobody_can_read_does_not_silently_turn_it_down(monkeypatch, capsys) -> None:
    """Dropping to a level nobody chose is how a service goes quiet without
    anyone deciding that it should."""
    monkeypatch.setenv("CLAUSE_LOG_LEVEL", "chatty")
    assert telemetry.configure(force=True) == "INFO"
    assert "not a level" in capsys.readouterr().err


def test_configuring_twice_does_not_print_every_line_twice() -> None:
    telemetry.configure(force=True)
    telemetry.configure(force=True)
    assert len(logging.getLogger("clause").handlers) == 1


def test_a_policy_that_did_not_pay_records_why() -> None:
    """The chain does not keep its readings, by design. So the answer to "why
    did this one not pay" has to be written down when it is still known, or it
    does not exist six months later."""
    import sys

    sys.path.insert(0, "tests")
    from test_chain import blocks_for, built, write
    from clause.protocol.policy import PolicyStatus

    pool, chain = built()
    policy = write(pool, chain, "earthquake",
                   {"location": "IST-KADIKOY", "radius_km": 50}, 100_000, 30,
                   simulated=True)
    for _ in range(blocks_for(30)):
        chain.produce_block()
        if pool.policies[policy.policy_id].status is not PolicyStatus.ACTIVE:
            break

    closed = policy.metadata.get("closed_on")
    assert closed, "a policy that closed says nothing about why"
    assert closed["source"] == policy.data_reference
    assert closed["trigger"] == pytest.approx(policy.curve.attachment)
    assert "index" in closed and "last_heard" in closed


# -- health -----------------------------------------------------------------

def app_for():
    from clause.api.app import create_app
    from clause.api.security import Settings

    return create_app(trials=100, seed=11, run_chain=False, seed_book=False,
                      settings=Settings(faucet=True, allowed_origins=()))


def test_the_health_check_does_not_hand_out_the_balance() -> None:
    """It was serving how much money is here to anybody who asked, on the one
    route a deployment leaves open on purpose."""
    from fastapi.testclient import TestClient

    with TestClient(app_for()) as client:
        body = client.get("/api/health").json()
    assert "balance" not in body["pool"]
    assert "open_policies" in body["pool"]


def test_a_book_that_is_not_reaching_disk_is_not_healthy(monkeypatch, tmp_path) -> None:
    """A hardcoded "ok" is worse than no health check: a monitor watching it
    reports green through a book that has not been saved in hours. A service
    answering requests it cannot save is the failure that looks healthiest
    from outside."""
    import time as _time

    from fastapi.testclient import TestClient

    monkeypatch.setenv("CLAUSE_STATE_DIR", str(tmp_path))
    app = app_for()
    with TestClient(app) as client:
        keeper = app.state.keeper
        assert keeper is not None, "a book was configured, so there is a keeper"
        assert client.get("/api/health").status_code == 200

        # An hour since the last save that reached disk.
        keeper.saved_at = _time.time() - 3600.0
        answer = client.get("/api/health")
        assert answer.status_code == 503
        assert answer.json()["status"] == "degraded"

        # And a save that is failing right now says so too, whatever the clock.
        keeper.saved_at = _time.time()
        keeper.last_error = "disk full"
        failing = client.get("/api/health")
        assert failing.status_code == 503
        assert failing.json()["book"]["last_error"] == "disk full"


# -- backup -----------------------------------------------------------------

def test_the_book_can_be_copied_while_it_is_being_written(tmp_path) -> None:
    """There was no backup command at all -- one line of prose in a README and
    nothing for a cron line to call. And a database being written to cannot be
    copied with cp: the copy opens and is wrong."""
    import sqlite3

    from clause.cli import build_parser
    from clause.store import Store

    book = tmp_path / "state" / "clause.sqlite"
    store = Store(book)
    store.write(meta={"session_secret": "abc"}, docs={"wallet": {}}, logs={})

    into = tmp_path / "backups"
    args = build_parser().parse_args(
        ["backup", "--to", str(into), "--book", str(book)])
    args.func(args)

    copies = list(into.glob("clause-*/clause.sqlite"))
    assert len(copies) == 1, f"expected one copy, found {copies}"
    # And it is a database somebody can actually open and read back.
    read = sqlite3.connect(f"file:{copies[0]}?mode=ro", uri=True)
    try:
        names = {row[0] for row in read.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        read.close()
    assert names, "the copy has no tables in it"


def test_backing_up_a_book_that_is_not_there_says_so(tmp_path) -> None:
    from clause.cli import build_parser

    args = build_parser().parse_args(
        ["backup", "--to", str(tmp_path / "out"), "--book", str(tmp_path / "nothing.sqlite")])
    with pytest.raises(SystemExit, match="no book at"):
        args.func(args)
