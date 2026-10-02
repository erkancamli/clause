"""The book holds the secret that signs every session.

clause/store.py writes `session_secret` into clause.sqlite, and
Authenticator.derived makes the ten minute price promise's key from the same
secret. So whoever can read the file can mint a session for any address and
forge a price promise. Nothing reaches it over HTTP; it is listed because
the file is the one thing that gets backed up and copied about.

deploy/install.sh puts the state directory at 750, and sqlite creates the
file at whatever the umask allows, which on a default Debian umask is
readable by every user on the machine. The file says it for itself now, so a
deployment that did not run the installer, or a book copied somewhere else,
carries the same answer.

The WAL and the SHM are the same data in flight and appear on the first
write, after the constructor has been past, so the keeper narrows them again
after every save.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

import pytest

from clause.store import Store


@pytest.fixture
def opened_with_a_loose_umask():
    """The umask a Debian login shell has, which is the case that matters.

    Nothing here calls narrow(): what is being asked is whether opening the
    book is enough, and an earlier version of this file called it in the
    fixture and so passed with the constructor doing nothing at all.
    """
    was = os.umask(0o022)
    where = Path(tempfile.mkdtemp()) / "clause.sqlite"
    store = Store(where)
    yield store, where
    store.close()
    os.umask(was)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_opening_the_book_is_enough(opened_with_a_loose_umask) -> None:
    _store, where = opened_with_a_loose_umask
    assert mode(where) == 0o600, oct(mode(where))


def test_so_is_everything_beside_it(opened_with_a_loose_umask) -> None:
    """The WAL is the same data, a moment earlier. It is created by the first
    write, so this is the one that needs the save to have happened."""
    store, where = opened_with_a_loose_umask
    store._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('format', '1')")
    store.narrow()
    beside = [where.with_name(where.name + s) for s in ("-wal", "-shm")]
    assert any(p.exists() for p in beside), "no write ahead log to check"
    for p in beside:
        if p.exists():
            assert mode(p) == 0o600, (p.name, oct(mode(p)))


def test_the_keeper_narrows_them_again_after_a_save() -> None:
    """They are created by the first write, which is after the constructor."""
    from pathlib import Path as P

    source = (P(__file__).resolve().parent.parent / "clause" / "store.py"
              ).read_text(encoding="utf-8")
    at = source.index("    def save(self) -> None:")
    said = source[at:source.index("\n    def ", at + 10)]
    assert "self.store.narrow()" in said


def test_a_filesystem_that_cannot_do_it_is_not_a_reason_to_refuse_to_start(monkeypatch) -> None:
    """A mount with no permission bits is somebody's deployment, not a fault."""
    where = Path(tempfile.mkdtemp()) / "clause.sqlite"

    def refuse(*_args, **_kw):
        raise OSError("this filesystem has no permission bits")

    monkeypatch.setattr(Path, "chmod", refuse)
    store = Store(where)                      # does not raise
    assert store.empty()
    store.close()
