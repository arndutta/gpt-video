"""Failures after grounding, authorization, or delayed review cannot keep a loop alive."""

import asyncio
import json
import time

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import pytest

from commerce.app import create_app as commerce_app
from governance_helpers import recommendation, setup_governance
from platform_app.config import RunRequest
from platform_app.governance import GovernanceError
from platform_app.tools import AnalysisError
from test_governance_execution import Intercept
from test_grounding_api import complete, upload
from test_workflow_integration import workbench


def auto_mode(client):
    response = client.patch("/api/policy", json={"confidence_threshold": 0., "auto_delta_pct": 100.,
        "volatility_limit": 5., "margin_proximity_buffer": 0., "minimum_sample": 30})
    assert response.status_code == 200, response.text
    assert client.patch("/api/control/mode", json={"mode": "assisted"}).status_code == 200


def start_loop(client):
    response = client.post("/api/loop", json={"request": {"kind": "grounded", "iterations": 100},
                                             "interval_seconds": 5, "max_iterations": 2})
    assert response.status_code == 202, response.text
    return response.json()


def loop_terminal(client):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        result = client.get("/api/loop").json()
        if not result["running"]:
            return result
        time.sleep(.025)
    pytest.fail("The failed full-pipeline loop did not stop.")


def test_validation_model_failure_leaves_drafts_unexecutable_and_stops_loop(tmp_path, monkeypatch):
    with workbench(tmp_path) as (client, app, provider):
        complete(client, upload(client))
        auto_mode(client)
        original = provider.with_structured_output

        def structured(schema, **kwargs):
            chain = original(schema, **kwargs)

            class FailedValidation:
                async def ainvoke(self, messages, config):
                    payload = json.loads(messages[1][1])
                    if "bands" in payload["facts"]:
                        return {"parsed": None, "raw": AIMessage(content=""),
                                "parsing_error": ValueError("Synthetic invalid validation narrative")}
                    return await chain.ainvoke(messages, config)

            return FailedValidation()

        monkeypatch.setattr(provider, "with_structured_output", structured)
        start_loop(client)
        result = loop_terminal(client)
        assert result["status"] == "failed" and result["iteration_count"] == 1
        items = client.get("/api/recommendations").json()["items"]
        assert items and {i["status"] for i in items} == {"draft"}
        assert not any(i["approval"] or i["executable"] for i in items)
        time.sleep(1.05)  # maintenance cannot activate a failed Validation node
        assert len(client.get("/api/runs").json()["items"]) == 1
        with TestClient(commerce_app(tmp_path / "commerce.db")) as commerce:
            assert commerce.get("/price-history").json()["total"] == 0


def test_unknown_full_graph_execution_stops_loop_without_second_iteration(tmp_path):
    with workbench(tmp_path) as (client, app, _):
        complete(client, upload(client))
        auto_mode(client)
        intercepted = Intercept(app.state.commerce.transport, fail=True)
        app.state.commerce.transport = intercepted
        start_loop(client)
        result = loop_terminal(client)
        assert result["status"] == "failed" and result["iteration_count"] == 1
        run = client.get(f'/api/runs/{result["last_run_id"]}').json()
        assert run["status"] == "failed" and "unknown" in run["error"].lower()
        items = client.get("/api/recommendations").json()["items"]
        assert {i["status"] for i in items} == {"unknown"}
        assert intercepted.posts == 3 and len(set(intercepted.bodies)) == 1
        time.sleep(1.05)
        assert intercepted.posts == 3 and len(client.get("/api/runs").json()["items"]) == 1


async def test_failed_grounded_run_revokes_authorizations_before_maintenance(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode("assisted")
    run = service.store.create_run(RunRequest(kind="grounded").model_dump())
    service.store.update_run(run["id"], "running", "execution")
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register(run["id"], [recommendation(product)])
    assert item["status"] == "approved"
    service.store.update_run(run["id"], "failed", "failed", error="Synthetic execution dependency failed")
    assert not await service.dispatch_due()
    assert service.get(item["id"])["status"] == "canceled"
    with pytest.raises(GovernanceError, match="resume"):
        await service.decide(item["id"], {"action": "approve", "expected_revision": 1})
    assert (await commerce.all("/price-history"))["total"] == 0


async def test_cancel_run_is_item_scoped_and_never_recalls_confirmed_writes(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode("assisted")
    products = (await commerce.all("/catalog"))["items"]
    first = await service.register("first", [recommendation(products[0]), recommendation(products[3])])
    [other] = await service.register("other", [recommendation(products[6])])
    await service.dispatch_due([first[0]["id"]])
    canceled = await service.cancel_run("first", "Pipeline failed after a confirmed partial outcome")
    assert canceled["canceled"] == 1
    assert service.get(first[0]["id"])["status"] == "applied"
    assert service.get(first[1]["id"])["status"] == "canceled"
    assert service.get(other["id"])["status"] == "approved"
    await service.dispatch_due()
    assert (await commerce.all("/price-history"))["total"] == 2


async def test_confirmed_part_of_failed_run_can_be_reverted_without_reviving_other_intents(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode("assisted")
    run = service.store.create_run(RunRequest(kind="grounded").model_dump())
    service.store.update_run(run["id"], "running", "execution")
    products = (await commerce.all("/catalog"))["items"]
    items = await service.register(run["id"], [recommendation(products[0]), recommendation(products[3])])
    await service.dispatch_due([items[0]["id"]])
    intercepted = Intercept(commerce.transport, fail=True)
    commerce.transport = intercepted
    assert not await service.dispatch_due([items[1]["id"]])
    assert intercepted.posts == 3 and service.get(items[1]["id"])["status"] == "unknown"
    service.store.update_run(run["id"], "failed", "failed", error="Other item had an unknown outcome")
    await service.cancel_run(run["id"])
    intercepted.fail = False
    result = await service.revert(items[0]["id"])
    assert result["status"] == "applied" and result["execution"]["new_price"] == items[0]["current_price"]
    assert service.get(items[1]["id"])["status"] == "unknown" and intercepted.posts == 4
    assert service.store.get_run(run["id"])["status"] == "failed"
    assert (await commerce.all("/price-history"))["total"] == 2
    assert (await service.revert(items[0]["id"]))["id"] == result["id"]
    assert (await commerce.all("/price-history"))["total"] == 2 and intercepted.posts == 4
