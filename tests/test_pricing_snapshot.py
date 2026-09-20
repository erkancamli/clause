"""A quote runs on a snapshot of the book, outside the money lock, and says
the same thing it would have said under it; several at once do not trip
over the engine's caches."""

from __future__ import annotations

import threading

from clause.pricing.engine import PricingEngine
from clause.protocol.pool import Pool

SUBJECT = {"location": "IST-KADIKOY", "radius_km": 50}


def _pool() -> Pool:
    pool = Pool(engine=PricingEngine(trials=400, seed=7))
    pool.deposit("lp", 5_000_000)
    for i in range(3):
        pool.write(peril_key="earthquake", subject={"location": "ANK-CANKAYA", "radius_km": 25},
                   limit=20_000, term_days=365, holder=f"h{i}", payer="lp")
    return pool


def test_a_quote_on_a_snapshot_matches_the_live_quote() -> None:
    pool = _pool()
    book, balance = pool.snapshot()
    live = pool.quote(peril_key="earthquake", subject=SUBJECT, limit=50_000, term_days=365)
    still = pool.quote(peril_key="earthquake", subject=SUBJECT, limit=50_000, term_days=365, book=book)
    assert still.premium == live.premium and still.marginal_capital == live.marginal_capital
    assert pool.can_write(peril_key="earthquake", subject=SUBJECT, limit=50_000, term_days=365) == \
        pool.can_write(peril_key="earthquake", subject=SUBJECT, limit=50_000, term_days=365, book=book, balance=balance)
    # The snapshot is a copy: writing another policy does not change what it says.
    pool.write(peril_key="earthquake", subject=SUBJECT, limit=30_000, term_days=365, holder="h9", payer="lp")
    again = pool.quote(peril_key="earthquake", subject=SUBJECT, limit=50_000, term_days=365, book=book)
    assert again.premium == still.premium and len(book) == 3 and len(pool.snapshot()[0]) == 4


def test_quotes_on_several_threads_agree_and_do_not_fail() -> None:
    pool = _pool()
    book, balance = pool.snapshot()
    out: list[float] = []
    errors: list[BaseException] = []

    def one(limit: float) -> None:
        try:
            for _ in range(3):
                q = pool.quote(peril_key="earthquake", subject=SUBJECT, limit=limit, term_days=365, book=book)
                pool.can_write(peril_key="earthquake", subject=SUBJECT, limit=limit, term_days=365, book=book, balance=balance)
                out.append(q.premium)
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=one, args=(limit,)) for limit in (10_000, 20_000, 30_000, 40_000) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(out) == 24 and len(set(out)) == 4          # four limits, each priced the same every time
    assert len(pool.engine._candidates) <= 8               # the cache stays bounded
