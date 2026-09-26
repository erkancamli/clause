"""The answer a signed request got, kept, so asking twice cannot buy twice.

A purchase is one POST. If its reply goes missing -- a phone that changed
network between sending and hearing back, a proxy that dropped the connection,
the protocol being replaced mid-request -- the browser cannot tell a request
that was never read from one that was read and acted on. Sending it again is
how somebody is charged twice, so the page did not send it again: it told the
buyer they might have been charged and to go and look. That is a poor answer to
give somebody who has just pressed Buy, and it was the answer they got most
often, because the request had in fact been read and the cover was already
theirs.

What makes asking a second time safe is that the challenge the request is
signed over is single use. The nonce names exactly one purchase, for good. So
the answer that nonce produced is kept here for a quarter of an hour, and a
request presenting a spent nonce with the same signature is answered with what
it got the first time -- the application it wrote, or the refusal it earned --
rather than writing a second application, or reporting an authentication
failure for a challenge the buyer spent legitimately.

Two things are deliberate. It is in memory and small: it exists to cover the
seconds after a lost reply, not to be a record, and the applications themselves
are the record. And nothing secret goes in it. A signature that travelled once
could have been captured, and holding a captured signature is not proof of
holding the key that made it, so a repeat is allowed to read back the
application it already paid for and nothing else: the caller of keep() leaves
session tokens out, and gets them back from nowhere.

begin() covers the other direction, where the first ask was lost on its way out
rather than on its way back and is still being decided when the second arrives.
A request that crashes between begin() and keep() leaves its note standing until
it expires, so a repeat of it is told the purchase is being decided rather than
that it was refused. That is the honest answer: the protocol did authorise it
and start, and did not finish, and the place that knows how it ended is the
holder's own cover.
"""

from __future__ import annotations

import dataclasses
import hmac
import time
from typing import Any

KEPT_SECONDS = 900.0
MOST = 512

#: The status held against a request that is still being decided. Not an HTTP
#: status: the route turns it into one, and it exists so that a repeat arriving
#: while the first is still in flight is answered with what is true -- we are
#: deciding -- rather than with an authentication failure, which is what a spent
#: challenge looks like from the outside.
DECIDING = 0


@dataclasses.dataclass(frozen=True)
class Answer:
    """What one signed request was answered with."""

    at: float
    status: int
    body: Any


class Answers:
    """Answers to signed requests, by the nonce that authorised them."""

    def __init__(self, *, seconds: float = KEPT_SECONDS, most: int = MOST) -> None:
        self._seconds = float(seconds)
        self._most = int(most)
        # nonce -> (signature, answer). The signature is held to be compared,
        # never to be given out.
        self._kept: dict[str, tuple[str, Answer]] = {}

    def __len__(self) -> int:
        return len(self._kept)

    def _forget_stale(self, now: float) -> None:
        for nonce in [n for n, (_s, a) in self._kept.items()
                      if a.at + self._seconds < now]:
            self._kept.pop(nonce, None)
        # Oldest first, if the cap is still exceeded. A flood of purchases must
        # not be a way to grow this without bound.
        while len(self._kept) > self._most:
            oldest = min(self._kept, key=lambda n: self._kept[n][1].at)
            self._kept.pop(oldest, None)

    def begin(self, nonce: str, signature: str, now: float | None = None) -> None:
        """This request has been authorised and is being decided.

        Held so that the same request arriving again a moment later -- the first
        ask having been lost on its way out rather than on its way back -- is
        told that, instead of being told it is not authorised. The challenge is
        spent by then, and a spent challenge is indistinguishable from a forged
        one to everything except this.
        """
        now = time.time() if now is None else now
        if not nonce or not signature or nonce in self._kept:
            return
        self._kept[nonce] = (signature, Answer(at=now, status=DECIDING, body=None))
        self._forget_stale(now)

    def keep(self, nonce: str, signature: str, *, status: int, body: Any,
             now: float | None = None) -> None:
        """Remember what this request was answered with. The first answer
        stands: a second call for one nonce changes nothing, so a repeat that
        somehow reaches the work cannot overwrite the answer it should give.
        The one thing it does replace is the marker begin() left, which is not
        an answer but a note that one was coming."""
        now = time.time() if now is None else now
        if not nonce or not signature:
            return
        held = self._kept.get(nonce)
        if held is not None and held[1].status != DECIDING:
            return
        self._kept[nonce] = (signature, Answer(at=now, status=int(status), body=body))
        self._forget_stale(now)

    def recall(self, nonce: str, signature: str,
               now: float | None = None) -> Answer | None:
        """The answer this exact request already got, if it is still held.

        The signature must match the one that earned the answer, compared
        without leaking how far it matched: a spent nonce is public the moment
        it is used, and must not become a way to read somebody's application by
        guessing at the signature beside it.
        """
        now = time.time() if now is None else now
        held = self._kept.get(nonce)
        if held is None:
            return None
        kept_signature, answer = held
        if answer.at + self._seconds < now:
            self._kept.pop(nonce, None)
            return None
        if not hmac.compare_digest(str(kept_signature), str(signature or "")):
            return None
        return answer
