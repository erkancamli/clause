"""How this deployment reaches a source, as distinct from which source a
policy names.

A policy's reference is the public query: the address anybody can repeat to
get the same answer, which is what makes a reading evidence rather than a
claim. A subscription key is a fact about who is paying for the quota, not a
fact about the evidence, so it lives here and never in a reference. Writing
one into a reference would put the operator's credential on every policy
record and on the proof page, where anybody could read it and spend it.
"""

from __future__ import annotations

import os
import urllib.parse

#: Open-Meteo's archive is free and keyless, and rate limited by address. That
#: is enough for one machine and runs out on a shared one, which is how a
#: settlement silently stops happening: the day's quota goes, every read comes
#: back as an error, and a policy reads nothing rather than reading rain. A
#: commercial key sends the same query to the customer host instead.
OPENMETEO_FREE = "archive-api.open-meteo.com"
OPENMETEO_PAID = "customer-archive-api.open-meteo.com"
OPENMETEO_KEY = "CLAUSE_OPENMETEO_KEY"


def reaching(url: str) -> str:
    """The address to actually request for a public query.

    Without a subscription this is the query itself, unchanged. With one it is
    the same query on the host the subscription answers, carrying the key.
    """
    key = os.environ.get(OPENMETEO_KEY, "").strip()
    if not key or OPENMETEO_FREE not in url:
        return url
    moved = url.replace(OPENMETEO_FREE, OPENMETEO_PAID, 1)
    join = "&" if "?" in moved else "?"
    return f"{moved}{join}apikey={urllib.parse.quote(key, safe='')}"


def subscribed() -> bool:
    """Whether this deployment holds an Open-Meteo subscription.

    For the operator's own page. It says that a key is set, never what it is.
    """
    return bool(os.environ.get(OPENMETEO_KEY, "").strip())
