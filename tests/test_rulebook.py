"""The calculation agent's rulebook: in every contract, on the page, and
the same in both."""

from __future__ import annotations

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.perils import REGISTRY
from clause.protocol import rulebook


def test_every_peril_has_its_rules_and_they_read_as_contract_lines() -> None:
    assert set(rulebook.RULES) == set(REGISTRY)
    for key, r in rulebook.RULES.items():
        assert r["primary"] and len(r["fallbacks"]) >= 2 and len(r["criteria"]) >= 3 and r["freeze_hours"] >= 72
    lines = rulebook.contract_lines("earthquake", deadline_days=7, on_missing_data="the premium comes back",
                                    attestation="At least 3 of 4 validators must report the reading.")
    assert lines[0].startswith("10. How the reading is determined")
    text = "\n".join(lines)
    assert "Fallback 1: USGS ShakeMap" in text and "Fallback 2:" in text
    assert "frozen 7 days after the event" in text and "Silence: if no final figure has been published 7 days" in text
    assert "Objection: the policyholder may object" in text and "Successor source:" in text and "Rulebook version 2026-09" in text
    assert rulebook.contract_lines("no-such-peril") == []


def test_the_rulebook_is_in_the_contract_and_on_the_api() -> None:
    with TestClient(create_app(trials=200, seed=11, run_chain=False, seed_book=False,
                               settings=Settings(faucet=True, specimens=True))) as client:
        preview = client.post("/api/contract", json={
            "peril": "earthquake", "subject": {"location": "IST-KADIKOY", "radius_km": 50}, "limit": 20_000,
            "term_days": 365, "holder": "", "settlement": "fiat",
            "interest": {"what": "a flat", "country": "TR", "inside_trigger_area": True, "value_at_risk": 90_000,
                         "size": {"kind": "home", "building": "flat", "area_m2": 100}}})
        assert preview.status_code == 200, preview.text
        text = preview.json()["text"]
        assert "10. How the reading is determined (calculation rules)" in text
        assert "validators must report the reading" in text        # the chain's own rule, quoted
        assert "Objection: the policyholder may object" in text
        book = client.get("/api/rulebook").json()
        assert set(book["perils"]) == set(REGISTRY) and book["objection_days"] == 30
        quake = book["perils"]["earthquake"]
        assert quake["deadline_days"] == 7 and quake["on_missing_data"] and "validators" in quake["attestation"]
        assert book["perils"]["flight_delay"]["deadline_days"] == 3 and book["perils"]["storm"]["deadline_days"] == 14
