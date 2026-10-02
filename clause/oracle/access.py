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
import time
import urllib.parse

#: Open-Meteo's archive is free and keyless, and rate limited by address. That
#: is enough for one machine and runs out on a shared one, which is how a
#: settlement silently stops happening: the day's quota goes, every read comes
#: back as an error, and a policy reads nothing rather than reading rain. A
#: commercial key sends the same query to the customer host instead.
OPENMETEO_FREE = "archive-api.open-meteo.com"
OPENMETEO_PAID = "customer-archive-api.open-meteo.com"
OPENMETEO_KEY = "CLAUSE_OPENMETEO_KEY"


#: How long to leave the subscription host alone after it has turned a query
#: away. Asked and refused is two requests for one reading, and the reason a
#: subscription refuses is rarely gone a second later: measured against the
#: real host, what comes back is
#:
#:     403 {"error":true,"reason":"This API endpoint requires the API
#:          Professional or Enterprise plan"}
#:
#: which is a fact about the plan and will be true for every query until
#: somebody changes the plan. An hour is short enough that an upgrade is
#: picked up without a restart, and long enough that the second request stops
#: being paid for with every reading.
REST_AFTER_A_REFUSAL = 3600.0


def reaching(url: str) -> str:
    """The address to actually request for a public query.

    Without a subscription this is the query itself, unchanged. With one it is
    the same query on the host the subscription answers, carrying the key --
    unless that host has just refused, in which case the public query stands
    until the hour is up.
    """
    key = os.environ.get(OPENMETEO_KEY, "").strip()
    if not key or OPENMETEO_FREE not in url:
        return url
    if resting():
        return url
    moved = url.replace(OPENMETEO_FREE, OPENMETEO_PAID, 1)
    join = "&" if "?" in moved else "?"
    return f"{moved}{join}apikey={urllib.parse.quote(key, safe='')}"


def resting(*, now: float | None = None) -> bool:
    """Whether the subscription host is being left alone for the moment."""
    at = float(_refusal.get("at", 0.0) or 0.0)
    if at <= 0.0:
        return False
    return (time.time() if now is None else now) - at < REST_AFTER_A_REFUSAL


#: A query the subscription host turns away, by whatever status it chooses.
#: Measured against the real host: a key it does not recognise comes back 400,
#: the live deployment's key comes back 403, a spent quota comes back 429. None
#: of them is the source refusing to answer the question, so no list of codes
#: is kept -- any refusal of a paid query sends the same query to the public
#: keyless host, where a query that is genuinely malformed refuses again and is
#: raised. The refusal is recorded for the operator either way.
_refusal: dict[str, float | int] = {}


def refused(code: int, *, now: float | None = None) -> None:
    """Record that the subscription host turned a query away."""
    _refusal["code"] = int(code)
    _refusal["at"] = time.time() if now is None else now


def refusal() -> dict[str, float | int]:
    """The last refusal by the subscription host, for the operator's page.

    Empty while the subscription is answering. It names the status code, when,
    and whether the host is being left alone for the hour after it; never the
    key.
    """
    if not _refusal:
        return {}
    return {**_refusal, "resting": resting()}


def forget_refusal() -> None:
    """For tests, and for an operator who has just replaced the key."""
    _refusal.clear()


def subscribed() -> bool:
    """Whether this deployment holds an Open-Meteo subscription.

    For the operator's own page. It says that a key is set, never what it is.
    """
    return bool(os.environ.get(OPENMETEO_KEY, "").strip())
