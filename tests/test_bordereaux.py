"""The three bordereaux: what was bound, what was paid, whether the ledger
and the book agree."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from clause.api.app import create_app
from clause.api.security import Settings
from clause.protocol.fees import month_of
from test_api_security import session_for
from test_commerce import TOKEN, register, signed_post
from test_desk import buy_quake

OP = {"x-operator-token": TOKEN}


def test_the_bordereaux_are_read_off_the_book_and_reconcile_with_the_ledger(tmp_path) -> None:
    app = create_app(trials=300, seed=11, run_chain=False, seed_book=True,
                     settings=Settings(faucet=True, operator_token=TOKEN, specimens=True),
                     store_path=tmp_path / "book.sqlite")
    with TestClient(app) as client:
        device, address = register(client)
        auth = {"authorization": f"Bearer {session_for(client, device, address)}"}
        first = buy_quake(client, device, address, 20_000)
        second = buy_quake(client, device, address, 30_000)
        carrier_id, month = first["metadata"]["carrier"], month_of(time.time())
        assert second["metadata"]["carrier"] == carrier_id
        # The company takes its desk and reads the month.
        desk_device, desk_addr = register(client)
        desk = {"authorization": f"Bearer {session_for(client, desk_device, desk_addr)}"}
        assert client.post("/api/company/specimen", json={"carrier_id": carrier_id}, headers=desk).status_code == 200
        risk = client.get("/api/company/bordereaux", params={"carrier_id": carrier_id, "month": month}, headers=desk).json()["bordereau"]
        mine = [r for r in risk["rows"] if r["reference"] in (first["policy_id"], second["policy_id"])]
        assert risk["kind"] == "risk" and len(mine) == 2
        row = next(r for r in mine if r["reference"] == first["policy_id"])
        assert row["limit"] == 20_000 and row["gross_premium"] == first["premium"] and row["inception"] and row["expiry"]
        assert row["fee_paid"] > 0 and row["platform_fee_paid"] > 0 and abs(row["net_fee_to_carrier"] - (row["fee_paid"] - row["platform_fee_paid"])) < 0.005
        assert row["province"] == "İstanbul" and "address" not in row     # the company sees the address in "insured"
        assert risk["totals"]["gross_premium"] >= first["premium"] + second["premium"]
        # Nothing paid yet: the claims bordereau is empty for the month.
        claims = client.get("/api/company/bordereaux", params={"carrier_id": carrier_id, "month": month, "kind": "claims"}, headers=desk).json()["bordereau"]
        assert claims["kind"] == "claims" and claims["totals"]["claims"] == 0
        # The reconciliation agrees with the fee ledger to the cent.
        recon = client.get("/api/company/bordereaux", params={"carrier_id": carrier_id, "month": month, "kind": "reconciliation"}, headers=desk).json()["bordereau"]
        items = {i["item"]: i["amount"] for i in recon["items"]}
        assert recon["reconciled"] and items["difference_ledger_less_bound"] == 0
        statement = client.get("/api/company/statements", params={"carrier_id": carrier_id, "month": month}, headers=desk).json()["statement"]
        assert abs(items["net_to_carrier_in_ledger"] - statement["net_to_company"]) < 0.005
        assert abs(items["net_fees_on_bound_policies"] - statement["net_to_company"]) < 0.005
        # A cancellation shows up as a premium returned, and the fee ledger follows.
        reply = signed_post(client, device, address, "cancel", {"policy_id": second["policy_id"]},
                            f"/api/policies/{second['policy_id']}/cancel", {"account": address})
        assert reply.status_code == 200, reply.text
        claims = client.get("/api/company/bordereaux", params={"carrier_id": carrier_id, "month": month, "kind": "claims"}, headers=desk).json()["bordereau"]
        returned = [r for r in claims["rows"] if r["kind"] == "premium_returned"]
        assert len(returned) == 1 and returned[0]["reference"] == second["policy_id"] and returned[0]["premium_returned"] > 0
        # CSV, with the header a bordereau desk loads.
        csv = client.get("/api/company/bordereaux", params={"carrier_id": carrier_id, "month": month, "format": "csv"}, headers=desk)
        assert csv.status_code == 200 and csv.headers["content-disposition"].endswith(f'{carrier_id}-{month}-risk.csv"')
        assert csv.text.splitlines()[0].startswith("reference,insured,peril,subject,province,country,inception,expiry,limit,gross_premium")
        recon_csv = client.get("/api/company/bordereaux", params={"carrier_id": carrier_id, "month": month, "kind": "reconciliation", "format": "csv"}, headers=desk).text
        assert recon_csv.startswith("item,amount") and "reconciled," in recon_csv
        # A stranger sees nothing; a wrong kind is refused; the operator sees every carrier.
        assert client.get("/api/company/bordereaux", params={"carrier_id": carrier_id}, headers=auth).status_code == 404
        assert client.get("/api/company/bordereaux", params={"carrier_id": carrier_id, "kind": "x"}, headers=desk).status_code == 422
        everything = client.get("/api/operator/bordereaux", params={"month": month}, headers=OP).json()["bordereau"]
        assert everything["carrier_id"] is None and everything["count"] >= 2
        assert client.get("/api/operator/bordereaux", params={"month": month, "kind": "reconciliation"}, headers=OP).json()["bordereau"]["kind"] == "reconciliation"
