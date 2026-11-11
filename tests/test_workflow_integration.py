"""Actual five-node LangGraph checkpoints and per-item Commerce-bound human review."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import time

from fastapi.testclient import TestClient
import httpx
from langchain_core.messages import AIMessage
import pytest

from commerce.app import create_app as commerce_app
from commerce.seed import seed_database
from platform_app.app import create_app
from platform_app.config import Settings
from platform_app.rag.store import RagStore
from test_grounding_api import Embedder, complete, upload


class TypedProvider:
    """Explicit test seam: real retrieval and graph, deterministic explanatory model fixture."""
    def __init__(self):
        self.calls = []
        self.roles = []

    def for_role(self, role):
        provider = self
        class RoleProvider:
            def with_structured_output(self, schema, **options):
                chain = provider.with_structured_output(schema, **options)
                original = chain.ainvoke
                async def record(*args, **kwargs):
                    provider.roles.append(role)
                    return await original(*args, **kwargs)
                chain.ainvoke = record
                return chain
        return RoleProvider()

    def with_structured_output(self, schema, **kwargs):
        provider = self
        assert kwargs["method"] == "json_schema"
        class Chain:
            async def ainvoke(self, messages, config):
                payload = json.loads(messages[1][1])
                provider.calls.append((schema.__name__, payload))
                citation = payload["evidence"][0]["citation_id"]
                if schema.__name__ == "ChatAnswer":
                    parsed = {"answer": "This read-only chat cannot approve prices, push changes, switch modes, or start a loop. Use the reviewed operator controls.",
                              "citations": [citation]}
                elif schema.__name__ == "StrategyNarrative":
                    parsed = {"recommendations": [{"sku": i["sku"], "rationale": "The computed price balances expected impact and uncertainty.",
                                                     "citations": [citation]} for i in payload["facts"]["recommendations"]],
                              "citations": [citation]}
                else:
                    parsed = {"interpretation": "The computed evidence and policy require deterministic review.",
                              "assumptions": [], "anomalies": [], "citations": [citation]}
                return {"parsed": schema.model_validate(parsed), "raw": AIMessage(content=""), "parsing_error": None}
        return Chain()


@contextmanager
def workbench(directory, *, seed=True):
    if seed:
        seed_database(directory / "commerce.db", sku_count=3, days=90,
                      as_of=datetime.now(timezone.utc).date(), data_dir=directory)
    upstream = commerce_app(directory / "commerce.db")
    provider = TypedProvider()
    settings = Settings(data_dir=directory, commerce_url="http://commerce", gateway_url="https://fixture-gateway.test/v1",
                        api_key="fixture-memory-only", model_router="router", model_narrator="narrator",
                        model_analyst="analyst", model_strategist="strategist")
    app = create_app(settings, commerce_transport=httpx.ASGITransport(app=upstream),
                     rag_factory=lambda config: RagStore(config.data_dir / "chroma", Embedder()),
                     llm_provider_factory=lambda _settings, role: provider.for_role(role))
    with TestClient(app) as client:
        yield client, app, provider


def run(client):
    response = client.post("/api/runs", json={"kind": "grounded", "iterations": 100, "seed": 17})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def settled(client, run_id, *, different_interrupt=None):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        result = client.get(f"/api/runs/{run_id}").json()
        if result["status"] in {"completed", "failed", "interrupted", "awaiting_review"}:
            pending = (result.get("result") or {}).get("pending_interrupts", [])
            if different_interrupt is None or not pending or pending[0]["item_id"] != different_interrupt:
                return result
        time.sleep(.02)
    pytest.fail("The graph did not reach a bounded terminal or review state")


def decide(client, item, action):
    result = client.post(f'/api/recommendations/{item["id"]}/decision', json={
        "action": action, "expected_revision": item["revision"], "reason": "Synthetic acceptance fixture review"})
    assert result.status_code == 200, result.text
    return result.json()


def test_five_nodes_numeric_integrity_citations_and_mixed_item_execution(tmp_path):
    with workbench(tmp_path) as (client, app, provider):
        assert complete(client, upload(client))["status"] == "ready"
        run_id = run(client)
        result = settled(client, run_id)
        assert result["status"] == "awaiting_review", result
        items = result["result"]["recommendations"]
        assert len(items) == 3 and len(provider.calls) == 5
        assert sorted(provider.roles) == ["analyst", "analyst", "narrator", "strategist", "strategist"]
        context_facts = next(payload["facts"] for _, payload in provider.calls if "sales_observations" in payload["facts"])
        signals = context_facts["business_signals"]
        assert context_facts["sales_observations"] == 270 and context_facts["competitor_observations"] == 6
        assert sum(signals["inventory_flags"].values()) == 3 and signals["competitor_status"] == {"available": 3}
        assert len(signals["representative_skus"]) == 3
        assert "baseline_demand" not in str(provider.calls), "Held-out evaluator truth must not enter model facts"
        assert {i["mode_at_decision"] for i in items} == {"supervised"}
        assert all(i["compliance_status"] == "passed" and i["numeric_hash"] and i["rationale"] for i in items)
        strategy_facts = next(payload["facts"]["recommendations"] for name, payload in provider.calls if name == "StrategyNarrative")
        assert {(i["sku"], i["proposed_price"]) for i in strategy_facts} == {(i["sku"], i["proposed_price"]) for i in items}
        for item in items:
            assert all(client.get(f"/api/grounding/citations/{c}").status_code == 200 for c in item["citations"])
        interrupted = result["result"]["pending_interrupts"][0]["item_id"]
        # Approve a later item before the first interrupt: its authorization is item-scoped.
        later = next(i for i in items if i["id"] != interrupted)
        assert decide(client, later, "approve")["status"] == "applied"
        first = next(i for i in items if i["id"] == interrupted)
        assert decide(client, first, "reject")["status"] == "rejected"
        result = settled(client, run_id, different_interrupt=interrupted)
        remaining = next(i for i in result["result"]["recommendations"] if i["status"] == "pending_review")
        decide(client, remaining, "reject")
        result = settled(client, run_id, different_interrupt=remaining["id"])
        assert result["status"] == "completed", result
        assert sorted(i["status"] for i in result["result"]["recommendations"]) == ["applied", "rejected", "rejected"]
        assert len(provider.calls) == 5, "Execution/resume must never call a model"
        events = client.get(f"/api/runs/{run_id}/events")
        assert events.status_code == 200 and '"status": "completed"' in events.text
        audit = client.get("/api/audit", params={"run_id": run_id, "limit": 1000}).json()["items"]
        stages = {e["detail"].get("agent") for e in audit if e["action"] == "agent_started"}
        assert stages == {"data_context", "quantitative", "strategy_reasoning", "validation_compliance", "execution"}
        assert any(e["action"] == "price_receipt" for e in audit)


def test_checkpoint_survives_restart_and_requires_recorded_item_decision(tmp_path):
    with workbench(tmp_path) as (client, _, _):
        complete(client, upload(client))
        run_id = run(client)
        result = settled(client, run_id)
        first_id = result["result"]["pending_interrupts"][0]["item_id"]
    assert (tmp_path / "checkpoints.db").exists()
    with workbench(tmp_path, seed=False) as (client, _, provider):
        assert client.get("/api/control").json()["mode"] == "supervised"
        response = client.post(f"/api/runs/{run_id}/resume")
        assert response.status_code == 409 and "decision" in response.text.lower()
        current = client.get(f"/api/recommendations/{first_id}").json()
        decide(client, current, "reject")
        assert client.post(f"/api/runs/{run_id}/resume").status_code == 202
        result = settled(client, run_id, different_interrupt=first_id)
        assert result["status"] == "awaiting_review" and result["result"]["pending_interrupts"][0]["item_id"] != first_id
        assert not provider.calls, "Checkpoint recovery should resume Execution, not regenerate earlier nodes"
        assert client.get("/api/loop").json()["running"] is False


def test_missing_mandatory_grounding_halts_before_recommendations_or_price_writes(tmp_path):
    with workbench(tmp_path) as (client, _, provider):
        result = settled(client, run(client))
        assert result["status"] == "failed" and "grounding" in result["error"].lower()
        assert client.get("/api/recommendations").json()["items"] == [] and not provider.calls
        with TestClient(commerce_app(tmp_path / "commerce.db")) as commerce:
            assert commerce.get("/price-history").json()["items"] == []


def test_saved_scenario_api_retains_inputs_without_creating_approval(tmp_path):
    with workbench(tmp_path) as (client, _, _):
        payload = {"name": "Synthetic cost stress", "request": {"items": [
            {"sku": "SKU-00001", "candidate_price": "12.00"}], "iterations": 100, "stress": "cost_spike"}}
        response = client.post("/api/scenarios/saved", json=payload)
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["result"]["executable"] is False and result["request"]["stress"] == "cost_spike"
        assert client.get("/api/scenarios/saved").json()["items"][0]["id"] == result["id"]
        assert client.get("/api/recommendations").json()["items"] == []
