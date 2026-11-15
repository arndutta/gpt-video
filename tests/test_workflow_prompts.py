"""Concise initial instructions retain complete facts, warnings and deterministic authority."""

from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from commerce.app import create_app as create_commerce
from platform_app.workflow.nodes import AgentNodes
from platform_app.workflow.schemas import CitedNarrative
import platform_app.workflow.nodes as module
from test_grounding_api import complete, upload
from test_workflow_integration import run, settled, workbench
from test_workflow_owned_tasks import owner_fixture


async def test_concise_context_narration_keeps_complete_quality_and_business_findings(monkeypatch):
    owner = owner_fixture(monkeypatch)
    quality = {"blocked": False, "status": "degraded", "checks": [
        {"check": "missing_competitor", "severity": "warning", "affected_records": 1,
         "message": "No competitor observation is available."},
        {"check": "sparse_history", "severity": "warning", "affected_records": 1,
         "message": "Historical evidence is limited; retain uncertainty."}]}
    signals = {"inventory_flags": {"scarce": 1}, "representative_skus": [{
        "sku": "SKU-1", "inventory_pressure": 0.9, "competitor_status": "missing",
        "assumption": "No replenishment is assumed."}]}
    monkeypatch.setattr(module, "quality_report", lambda *_args: deepcopy(quality))
    monkeypatch.setattr(module, "business_context", lambda *_args: deepcopy(signals))
    captured = []

    async def generate(schema, **request):
        assert schema is CitedNarrative
        captured.append(deepcopy(request))
        return schema(interpretation="Synthetic response with the retained warnings.",
                      assumptions=["No replenishment is assumed."],
                      anomalies=["Competitor evidence missing; history limited."],
                      citations=["policy-v1:0"])

    owner.llm.generate = generate
    state = await AgentNodes(owner).data_context({"run_id": "fixture-run", "request": {}})
    assert len(captured) == 2
    for request in captured:
        assert request["facts"]["quality"] == quality
        assert request["facts"]["business_signals"] == signals
        assert "normally two or three short sentences" in request["prompt"]
        assert "Preserve all material" in request["prompt"]
        assert "using extra space when needed" in request["prompt"]
        assert "use an empty list only when no such finding is supported" in request["prompt"]
    assert state["quality"] == quality
    assert state["data_narrative"]["assumptions"] == ["No replenishment is assumed."]
    assert state["data_narrative"]["anomaly_commentary"]["anomalies"] == [
        "Competitor evidence missing; history limited."]


@pytest.mark.parametrize("batch_size", [25, 1])
def test_concise_five_node_envelopes_keep_numeric_inputs_citations_and_supervised_review(tmp_path, batch_size):
    with workbench(tmp_path) as (client, app, provider):
        app.state.settings.strategy_batch_size = batch_size
        assert complete(client, upload(client))["status"] == "ready"
        result = settled(client, run(client))
        assert result["status"] == "awaiting_review", result
        items = result["result"]["recommendations"]
        assert len(items) == 3 and len(provider.calls) == 4 + (3 + batch_size - 1) // batch_size
        assert {item["mode_at_decision"] for item in items} == {"supervised"}
        assert all(not item["approval"] and not item["executable"] for item in items)
        strategy_skus = []
        for schema, payload in provider.calls:
            instruction = payload["instruction"]
            if schema == "StrategyNarrative":
                assert "normally one or two short sentences" in instruction
                assert "Return exactly the supplied SKU identifiers" in instruction
                facts = payload["facts"]["recommendations"]
                assert 1 <= len(facts) <= batch_size
                strategy_skus.extend(candidate["sku"] for candidate in facts)
                for candidate in facts:
                    saved = next(item for item in items if item["sku"] == candidate["sku"])
                    for field in ("current_price", "proposed_price", "delta_pct", "confidence",
                                  "confidence_factors", "optimal_price_uncertainty", "elasticity",
                                  "impact", "competitive_gap_pct", "inventory_pressure"):
                        assert candidate[field] == saved[field]
            else:
                assert "normally two or three short sentences" in instruction
                assert "Preserve all material" in instruction
            assert payload["evidence"] and "citation_id" in payload["evidence"][0]
        assert sorted(strategy_skus) == sorted(item["sku"] for item in items)
        quantitative = next(payload["facts"] for _, payload in provider.calls if "aggregate" in payload["facts"])
        assert quantitative["aggregate"] == result["result"]["aggregate"]
        assert quantitative["configuration"] == result["result"]["configuration"]
        assert quantitative["skipped"] == result["result"]["skipped"]
        assert {item["numeric_hash"] for item in items} == {quantitative["numeric_hash"]}
        validation = next(payload["facts"] for _, payload in provider.calls if "verdicts" in payload["facts"])
        assert {v["sku"] for v in validation["verdicts"]} == {item["sku"] for item in items}
        for verdict in validation["verdicts"]:
            saved = next(item for item in items if item["sku"] == verdict["sku"])
            assert verdict["band"] == saved["band"] and verdict["compliance"] == saved["compliance"]
        for item in items:
            assert all(client.get("/api/grounding/citations/" + citation).status_code == 200
                       for citation in item["citations"])
        with TestClient(create_commerce(tmp_path / "commerce.db")) as commerce:
            assert commerce.get("/price-history").json()["total"] == 0
