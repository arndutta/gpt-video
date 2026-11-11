"""A fresh observed market shock reaches the deterministic Escalate gate."""

import json

import pytest

from test_grounding_api import complete, upload
from test_workflow_integration import settled, workbench


@pytest.mark.parametrize("mode", ["assisted", "autonomous"])
def test_large_observed_market_gap_prevents_automatic_execution(tmp_path, mode):
    with workbench(tmp_path) as (client, _, _):
        complete(client, upload(client))
        assert client.patch("/api/control/mode", json={"mode": mode, "hold_seconds": 0}).status_code == 200
        product = client.get("/api/catalog", params={"limit": 1}).json()["items"][0]
        path = tmp_path / "competitor_feed.json"
        feed = json.loads(path.read_text())
        rows = feed["items"] if isinstance(feed, dict) else feed
        for row in rows:
            if row["sku"] == product["sku"]:
                row["price"] = f"{float(product['current_price']) / 2:.2f}"
        path.write_text(json.dumps(feed))
        response = client.post("/api/runs", json={"kind": "grounded", "iterations": 100,
                                                  "sku_ids": [product["sku"]]})
        assert response.status_code == 202, response.text
        run = settled(client, response.json()["id"])
        assert run["status"] == "awaiting_review", run
        [item] = run["result"]["recommendations"]
        assert item["band"] == "escalate" and item["status"] == "escalated" and item["approval"] is None
        reason = next(row for row in item["band_reasons"] if row["code"] == "novel_market")
        assert not reason["passed"]
        assert abs(reason["actual"]["competitive_gap_pct"]) > reason["threshold"]["abs_market_gap_pct"]
        assert item["market_novelty"]["basis"].startswith("configured")
        result = client.post(f'/api/recommendations/{item["id"]}/decision', json={
            "action": "approve", "expected_revision": item["revision"]})
        assert result.status_code == 422 and result.json()["detail"]["code"] == "escalation_reason_required"
        audit = client.get("/api/audit", params={"run_id": run["id"], "limit": 1000}).json()["items"]
        assert not any(row["action"] == "price_dispatch" for row in audit)
