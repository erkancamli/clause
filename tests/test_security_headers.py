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
