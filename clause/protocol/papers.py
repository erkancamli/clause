"""The box a buyer's own papers go in, and the record that they were there.

This protocol asks for no name, no email address and no telephone number, so
there is nowhere to send anything. The law does not care: the order has to be
confirmed without delay, the terms agreed to have to be given, and the right
to withdraw has to be put in front of the person who has it. All three are
obligations to *give*, and giving has to be provable.

So they are put here instead, under the address that bought the cover, each
with the moment it was given and the moment it was first opened. The person
reaches them by signing in with the same key that bought the cover, which is
the only thing the protocol knows about them.

Three rules are enforced rather than trusted, because each is a way a record
like this stops being evidence.

Nothing is ever taken out. There is no method here that removes a paper and
none that rewrites one; a file that can quietly lose a page proves nothing
about what was in it.

The moment of opening is written once. The first time somebody reads a thing
is the fact that matters, and a later visit must not overwrite it.

And a paper belongs to one address. It is returned to that address and to
nobody else, operator included: this book holds what a person was told about
their own contract.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

#: What a paper can be. Each exists because something requires it to.
KINDS = (
    # 6563 m.4(1): the order, confirmed without delay.
    "confirmation",
    # The terms as they were accepted, with the hash that was signed over.
    "terms",
    # Directive (EU) 2023/2673: the reminder of the right to withdraw, given
    # within a day of the contract where the information came later than a day
    # before it. Taken here as the ordinary case, since a purchase made in one
    # sitting is never a day ahead of itself.
    "withdrawal",
    # What the insurer decided, once it has.
    "decision",
)

MAX_TITLE = 120
MAX_BODY = 20_000


class PaperError(ValueError):
    """Something this book refuses. Safe to show."""


@dataclass(slots=True)
class Paper:
    paper_id: str
    account: str
    kind: str
    title: str
    body: str
    #: What it is about, when it is about something: a policy or an application.
    about: str = ""
    #: The hash of the terms, where the paper carries terms that were signed.
    terms_hash: str = ""
    given_at: float = 0.0
    #: Set once, the first time it is opened, and never moved after.
    opened_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"paper_id": self.paper_id, "kind": self.kind, "title": self.title,
                "body": self.body, "about": self.about or None,
                "terms_hash": self.terms_hash or None,
                "given_at": self.given_at, "opened_at": self.opened_at or None}

    def summary(self) -> dict[str, Any]:
        """The row in the list: everything but the text itself."""
        out = self.to_dict()
        out.pop("body")
        return out


class Papers:
    """Everything the protocol has given each address, in the order it gave it."""

    def __init__(self) -> None:
        self.papers: dict[str, Paper] = {}
        self._lock = threading.RLock()

    # -- giving -------------------------------------------------------------

    def give(self, account: str, kind: str, title: str, body: str, *,
             about: str = "", terms_hash: str = "", now: float | None = None) -> Paper:
        """Put a paper in somebody's box. This is the only way one appears."""
        if kind not in KINDS:
            raise PaperError(f"no such paper: {kind}")
        if not account:
            raise PaperError("a paper needs an address to belong to")
        moment = time.time() if now is None else now
        paper = Paper(
            paper_id="PAP-" + secrets.token_hex(6).upper(),
            account=account, kind=kind,
            title=str(title)[:MAX_TITLE], body=str(body)[:MAX_BODY],
            about=str(about or ""), terms_hash=str(terms_hash or ""),
            given_at=moment,
        )
        with self._lock:
            self.papers[paper.paper_id] = paper
        return paper

    # -- reading ------------------------------------------------------------

    def mine(self, account: str) -> list[Paper]:
        """Everything this address was given, newest first."""
        with self._lock:
            found = [p for p in self.papers.values() if p.account == account]
        return sorted(found, key=lambda p: p.given_at, reverse=True)

    def unread(self, account: str) -> int:
        return sum(1 for p in self.mine(account) if not p.opened_at)

    def about(self, account: str, reference: str) -> list[Paper]:
        return [p for p in self.mine(account) if p.about == reference]

    def open(self, account: str, paper_id: str, *, now: float | None = None) -> Paper:
        """Read one, and write down that it was read.

        The moment is written the first time and never again: what matters is
        when this person first had it in front of them, not when they last
        looked at it.
        """
        moment = time.time() if now is None else now
        with self._lock:
            paper = self.papers.get(paper_id)
            if paper is None or paper.account != account:
                # The same answer either way: whether a paper exists is not
                # something to tell somebody it does not belong to.
                raise PaperError("no such paper")
            if not paper.opened_at:
                paper.opened_at = moment
            return paper
