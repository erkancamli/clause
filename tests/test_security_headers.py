"""What every answer from the API carries for the browser's sake: no cache
may keep it, nothing may sniff or frame it, and a refusal for haste says
how long to wait."""

from __future__ import annotations

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings


def test_every_api_answer_is_uncacheable_and_hardened() -> None:
    with TestClient(create_app(trials=200, seed=11, run_chain=False, seed_book=False,
                               settings=Settings(faucet=True, allowed_origins=("http://site.test",)))) as client:
        for path in ("/api/health", "/api/perils", "/api/rulebook", "/api/no-such-route"):
            r = client.get(path)
            assert r.headers["cache-control"] == "no-store", path
            assert r.headers["x-content-type-options"] == "nosniff", path
            assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin", path
            assert r.headers["x-frame-options"] == "DENY" and "camera=()" in r.headers["permissions-policy"], path
            assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'", path
        # The event stream keeps its own cache header; the redirect off the API
        # host is hardened but not told what to cache.
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 302 and r.headers["x-content-type-options"] == "nosniff" and "cache-control" not in r.headers
        # A refusal for haste says when to come back.
        for _ in range(12):
            r = client.post("/api/operator/session", json={}, headers={"x-operator-token": "guess"})
            if r.status_code == 429:
                break
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1 and r.headers["cache-control"] == "no-store"


def test_an_encrypted_answer_says_not_to_come_back_unencrypted() -> None:
    """HSTS, from the application rather than only from the edge.

    deploy/nginx.conf has sent `Strict-Transport-Security` for as long as it
    has existed, and the deployment that is actually running answers through
    a different proxy, which does not: measured against the live service,
    every other header in the test above was present and this one was
    missing. Said here too, so changing the edge cannot lose it.

    Only where the connection is already encrypted. A header promising a
    browser never to use http again, sent over http, is a promise made on
    the one channel that could have been tampered with.
    """
    with TestClient(create_app(trials=50, seed=11, run_chain=False, seed_book=False,
                               settings=Settings())) as client:
        plain = client.get("/api/health")
        assert "strict-transport-security" not in plain.headers

        for proto in ("https", "https, http", "https,http"):
            said = client.get("/api/health", headers={"x-forwarded-proto": proto}).headers
            assert said["strict-transport-security"] == "max-age=31536000; includeSubDomains", proto

        for proto in ("http", "ws", ""):
            said = client.get("/api/health", headers={"x-forwarded-proto": proto}).headers
            assert "strict-transport-security" not in said, proto


def test_the_application_and_the_edge_say_the_same_thing() -> None:
    """Two copies of one policy, which only add up while they agree."""
    from pathlib import Path

    conf = (Path(__file__).resolve().parent.parent / "deploy" / "nginx.conf"
            ).read_text(encoding="utf-8")
    assert 'Strict-Transport-Security "max-age=31536000; includeSubDomains"' in conf
