"""The public grounded-run and human override routes preserve run limits in every mode."""

from decimal import Decimal

import pytest

from test_grounding_api import complete, upload
from test_workflow_integration import settled, workbench


@pytest.mark.parametrize("mode", ["supervised", "assisted", "autonomous"])
@pytest.mark.parametrize("constraint", ["cap", "floor", "ceiling"])
def test_public_api_override_cannot_escape_run_constraints(tmp_path, mode, constraint):
    with workbench(tmp_path) as (client, _, _):
        complete(client, upload(client))
        assert client.patch("/api/policy", json={"confidence_threshold": 1.}).status_code == 200
        assert client.patch("/api/control/mode", json={"mode": mode, "hold_seconds": 3600}).status_code == 200
        product = client.get("/api/catalog", params={"limit": 1}).json()["items"][0]
        current = Decimal(product["current_price"])
        if constraint == "cap":
            limits = {"max_change_pct": .01}
            bad_price = f"{current * Decimal('1.05'):.2f}"
        else:
            limits = {"category_floors": {product["category"]: f"{current - Decimal('0.05'):.2f}"},
                      "category_ceilings": {product["category"]: f"{current + Decimal('0.05'):.2f}"}}
            bad_price = f"{current + (Decimal('-0.10') if constraint == 'floor' else Decimal('0.10')):.2f}"
        response = client.post("/api/runs", json={"kind": "grounded", "iterations": 100,
            "sku_ids": [product["sku"]], "constraints": limits})
        assert response.status_code == 202, response.text
        run = settled(client, response.json()["id"])
        assert run["status"] == "awaiting_review", run
        [item] = run["result"]["recommendations"]
        assert item["compliance_status"] == "passed" and item["run_constraints"]
        result = client.post(f'/api/recommendations/{item["id"]}/decision', json={"action": "override",
            "expected_revision": item["revision"], "price": bad_price, "reason": "Cannot waive deterministic run limits."})
        assert result.status_code == 409 and result.json()["detail"]["code"] == "compliance_veto", result.text
        audit = client.get("/api/audit", params={"run_id": run["id"], "limit": 1000}).json()["items"]
        assert not any(event["action"] == "price_dispatch" for event in audit)
