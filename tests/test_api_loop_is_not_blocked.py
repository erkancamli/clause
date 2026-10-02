"""The simulation must not run on the event loop.

Measured with a 5 ms asyncio timer against the app as it was: one
unauthenticated client holding GET /api/stream open blocked the loop for
15,208 ms continuously, about three seconds in every four, because the SSE
generator called pool.summary() and pool.risk_view() directly inside an
``async def``. Both run the Monte Carlo, in Python. The same simulation
through POST /api/quote, which has always been offloaded, blocks it for 54 ms.

/api/pool and /api/pool/risk did the same thing on an ordinary GET, with no
rate limit: 0.55 s and 2.47 s measured against the live deployment, which a
single caller could repeat as fast as it answered. The site's own front page
opens the stream, so the first visitor was the attack.

There was a timing test here and it is gone, because it could not tell the two
apart. Measured on this machine against a seeded book of four thousand trials:
the loop runs 10.2 ms late with the handoff and 20.1 ms late without it, where
the live book of two thousand policies at twelve thousand trials is three
seconds in four. A test that passes at 20 ms and would pass at 10 is not
measuring what it says it is, so what is left are two that read the code: the
handoff has to be there, and the limit with it.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_SOURCE = (Path(__file__).resolve().parent.parent
              / "clause" / "api" / "app.py").read_text(encoding="utf-8")



def test_the_stream_asks_for_the_pool_off_the_loop() -> None:
    """The generator is an async def, so a direct call is a call on the loop
    however fast it looks on an empty book."""
    at = APP_SOURCE.index("async def events()")
    body = APP_SOURCE[at:APP_SOURCE.index("\n    @app.", at)]
    assert "run_in_threadpool" in body
    heavy = re.findall(r"(?<!lambda: \{)[^ (]*pool\.(?:summary|risk_view)\(\)", body)
    offloaded = body.index("run_in_threadpool")
    for call in ("pool.summary()", "pool.risk_view()"):
        assert body.index(call) > offloaded, f"{call} is called before the handoff"
    assert heavy, "the stream no longer reads the pool at all"


def test_every_route_that_simulates_is_behind_a_limit() -> None:
    for route in ("/api/pool", "/api/pool/risk"):
        at = APP_SOURCE.index(f'@app.get("{route}")')
        body = APP_SOURCE[at:APP_SOURCE.index("\n    @app.", at)]
        assert 'guard(http, "pool"' in body, f"{route} has no rate limit"
        assert "run_in_threadpool" in body, f"{route} runs on the loop"
