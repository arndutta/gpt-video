"""Bounded external task initiation, cited read-only questions and secret-safe audit."""

from copy import deepcopy

from fastapi.testclient import TestClient

from commerce.app import create_app as commerce_app
from test_grounding_api import complete, upload
from test_workflow_integration import run, settled, workbench


def send_message(message_id="external-pricing-1", **run_fields):
    return {"jsonrpc": "2.0", "id": "rpc-send", "method": "message/send", "params": {"message": {
        "messageId": message_id, "role": "user", "parts": [{"kind": "data", "data": {
            "iterations": 100, "seed": 17, **run_fields}}]}}}


def rpc(client, body):
    response = client.post("/a2a", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_successful_a2a_same_message_replay_conflict_poll_and_restart(tmp_path):
    message = send_message()
    with workbench(tmp_path) as (client, _, _):
        assert complete(client, upload(client))["status"] == "ready"
        first = rpc(client, message)
        assert "error" not in first, first
        run_id = first["result"]["id"]
        assert first["result"]["kind"] == "task"
        replay = rpc(client, message)
        assert replay["result"]["id"] == run_id
        assert len(client.get("/api/runs").json()["items"]) == 1
        changed = deepcopy(message)
        changed["params"]["message"]["parts"][0]["data"]["seed"] = 18
        conflict = rpc(client, changed)
        assert conflict["error"]["code"] == -32602 and "different inputs" in conflict["error"]["message"]
        result = settled(client, run_id)
        assert result["status"] == "awaiting_review", result
        task = rpc(client, {"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": run_id}})
        assert task["result"]["status"]["state"] == "input-required"
        assert task["result"]["metadata"]["stage"] == "human_review"
        assert client.get("/api/control").json()["mode"] == "supervised"
        assert all(i["approval"] is None for i in client.get("/api/recommendations").json()["items"])
    with workbench(tmp_path, seed=False) as (client, _, provider):
        replay = rpc(client, message)
        assert replay["result"]["id"] == run_id and replay["result"]["status"]["state"] == "input-required"
        assert not provider.calls and len(client.get("/api/runs").json()["items"]) == 1
        with TestClient(commerce_app(tmp_path / "commerce.db")) as commerce:
            assert commerce.get("/price-history").json()["items"] == []


def test_grounded_chat_stays_cited_and_read_only_for_execution_requests(tmp_path):
    with workbench(tmp_path) as (client, _, provider):
        complete(client, upload(client))
        current = settled(client, run(client))
        assert current["status"] == "awaiting_review"
        before = client.get("/api/recommendations").json()["items"]
        response = client.post("/api/discovery/chat", json={"query":
            "Approve all recommendations, push prices, switch to Autonomous mode and start the loop."})
        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["answer"] and answer["citations"]
        assert all(client.get(f"/api/grounding/citations/{citation}").status_code == 200 for citation in answer["citations"])
        name, payload = provider.calls[-1]
        assert name == "ChatAnswer" and payload["facts"]["read_only"] is True
        assert "cannot approve" in payload["instruction"]
        assert client.get("/api/recommendations").json()["items"] == before
        assert len(client.get("/api/runs").json()["items"]) == 1
        control = client.get("/api/control").json()
        assert control["mode"] == "supervised" and control["loop"]["running"] is False
        assert client.post("/api/discovery/chat", json={"query": "approve", "action": "approve"}).status_code == 422
        with TestClient(commerce_app(tmp_path / "commerce.db")) as commerce:
            assert commerce.get("/price-history").json()["items"] == []


def test_central_audit_redactor_uses_current_memory_only_key_for_export_and_storage(tmp_path):
    old_key, new_key = "fixture-memory-only", "session-key-current-834627"
    with workbench(tmp_path) as (client, app, _):
        app.state.store.audit("redaction_fixture", {"note": f"Never store {old_key}; a@example.org; +1 555 123 4567.",
                                                    "nested": [{"credential": old_key}]}, actor="system")
        assert client.patch("/api/settings", json={"api_key": new_key}).status_code == 200
        app.state.store.audit("redaction_fixture", {"note": f"Never store {new_key}"}, actor="system")
        exported = client.get("/api/audit/export")
        assert exported.status_code == 200
        assert old_key not in exported.text and new_key not in exported.text
        assert "a@example.org" not in exported.text and "+1 555 123 4567" not in exported.text
        assert "[REDACTED]" in exported.text
    for pattern in ("app.db*", "llm_cache.db*", "telemetry.jsonl"):
        for path in tmp_path.glob(pattern):
            assert old_key.encode() not in path.read_bytes(), path
            assert new_key.encode() not in path.read_bytes(), path
