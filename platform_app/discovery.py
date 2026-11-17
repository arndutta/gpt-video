"""Read-only grounded questions and bounded A2A 0.3 JSON-RPC interoperability."""

from platform_app.database import sql

import hashlib
import json
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from platform_app.config import RunRequest
from platform_app.commerce_client import CommerceUnavailable

router = APIRouter()


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)


class ChatAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=8000)
    citations: list[str] = Field(min_length=1, max_length=50)


@router.post("/api/discovery/chat")
async def chat(payload: ChatRequest, request: Request):
    state = request.app.state
    items = state.governance.queue(limit=100)
    facts = {"recommendations": [{k: i.get(k) for k in ("sku", "name", "current_price", "proposed_price", "band",
                                                                          "confidence", "status", "rationale")}
                                 for i in items], "mode": state.governance.mode(),
             "read_only": True, "scope": "Latest 100 stored recommendations, not a full catalog query"}
    return (await state.llm.generate(ChatAnswer, role="router", query=payload.query, facts=facts,
                                     prompt="Answer only from supplied recommendation facts and cited knowledge. This interface cannot approve, change prices, or start tasks.",
                                     policy_version=str(state.governance.mode()["policy_version"])) ).model_dump()


@router.get("/.well-known/agent-card.json")
def card():
    # Pin the bounded 0.3 method names required by the PRD, rather than claiming
    # support for the evolving full protocol or negotiation/task lifecycle.
    return {"protocolVersion": "0.3.0", "name": "Retail Pricing Workbench", "version": "0.2.0",
            "description": "Local grounded SKU pricing analysis; human review and independent Commerce compliance required.",
            "url": "http://127.0.0.1:8000/a2a", "preferredTransport": "JSONRPC",
            "capabilities": {"streaming": False, "pushNotifications": False, "stateTransitionHistory": False},
            "defaultInputModes": ["application/json"], "defaultOutputModes": ["application/json"],
            "skills": [{"id": "grounded-pricing-run", "name": "Grounded pricing analysis",
                        "description": "Send a data part containing RunRequest. Poll tasks/get; use the local UI for human decisions.",
                        "tags": ["pricing", "grounded", "review-required"]}],
            "documentationUrl": "http://127.0.0.1:8000/docs"}


def init_discovery(store):
    with store.connection() as db:
        db.executescript(sql("discovery_ddl.sql"))


def task(run):
    statuses = {"queued": "submitted", "running": "working", "awaiting_review": "input-required",
                "completed": "completed", "failed": "failed", "interrupted": "canceled"}
    return {"kind": "task", "id": run["id"], "contextId": run["id"],
            "status": {"state": statuses.get(run["status"], "unknown"),
                       "timestamp": run.get("completed_at") or run["created_at"]},
            "metadata": {"stage": run["stage"], "error": run["error"], "reviewUrl": "/review"}}


def rpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


@router.post("/a2a")
async def rpc(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return rpc_error(None, -32700, "Parse error")
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or not isinstance(body.get("method"), str):
        return rpc_error(None, -32600, "Invalid Request")
    request_id = body.get("id")
    if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
        return rpc_error(None, -32600, "An id is required; notifications are not supported")
    state, params = request.app.state, body.get("params", {})
    if not isinstance(params, dict):
        return rpc_error(request_id, -32602, "Invalid params")
    if body["method"] == "tasks/get":
        run = state.store.get_run(params.get("id", "")) if isinstance(params.get("id"), str) else None
        if not run:
            return rpc_error(request_id, -32001, "Task not found")
        return {"jsonrpc": "2.0", "id": request_id, "result": task(run)}
    if body["method"] != "message/send":
        return rpc_error(request_id, -32601, "Method not found")
    message = params.get("message")
    if not isinstance(message, dict) or message.get("role") != "user" or message.get("taskId"):
        return rpc_error(request_id, -32602, "Supply a new user message; task continuation is not supported")
    message_id = message.get("messageId")
    parts = message.get("parts")
    if not isinstance(message_id, str) or not 1 <= len(message_id) <= 128 or not isinstance(parts, list) or len(parts) != 1:
        return rpc_error(request_id, -32602, "Supply a messageId and one data part")
    part = parts[0]
    if not isinstance(part, dict) or part.get("kind") != "data" or not isinstance(part.get("data"), dict):
        return rpc_error(request_id, -32602, "A typed RunRequest data part is required")
    try:
        payload = RunRequest.model_validate({**part["data"], "kind": "grounded"})
    except ValidationError:
        return rpc_error(request_id, -32602, "Invalid pricing request; personal pricing and execution commands are unsupported")
    fingerprint = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    with state.store.connection() as db:
        old = db.execute("SELECT * FROM a2a_messages WHERE message_id=?", (message_id,)).fetchone()
    if old:
        if old["digest"] != fingerprint:
            return rpc_error(request_id, -32602, "messageId was already used for different inputs")
        return {"jsonrpc": "2.0", "id": request_id, "result": task(state.store.get_run(old["run_id"]))}
    try:
        health = await state.commerce.get("/health")
        if health.get("status") != "ok" or not health.get("seeded"):
            return rpc_error(request_id, -32002, "Commerce must be healthy and seeded")
        with state.store.connection() as db:
            concurrent = db.execute("SELECT * FROM a2a_messages WHERE message_id=?", (message_id,)).fetchone()
        if concurrent:
            if concurrent["digest"] != fingerprint:
                return rpc_error(request_id, -32602, "messageId was already used for different inputs")
            return {"jsonrpc": "2.0", "id": request_id, "result": task(state.store.get_run(concurrent["run_id"]))}
        run = state.workflow.start(payload)
    except (RuntimeError, CommerceUnavailable):
        return rpc_error(request_id, -32002, "Pricing unavailable or busy; check gateway aliases, grounding and Commerce")
    with state.store.connection() as db:
        db.execute("INSERT INTO a2a_messages VALUES(?,?,?)", (message_id, fingerprint, run["id"]))
        state.store._audit(db, "external", "a2a_task_requested", run["id"], {"message_id": message_id})
    return {"jsonrpc": "2.0", "id": request_id, "result": task(run)}
