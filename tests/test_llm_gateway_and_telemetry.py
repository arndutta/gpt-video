"""Real LangChain HTTP envelopes and failure-isolated operational metadata."""

import asyncio
import json
from types import SimpleNamespace

import httpx
from langsmith.run_helpers import get_tracing_context
import pytest

from platform_app.config import Settings
from platform_app.llm import GroundedLLM
from platform_app.llm.monitor import CallMonitor
from platform_app.llm.safety import redact, validate_citations
from platform_app.telemetry import Telemetry
from test_grounded_llm import Explanation, GroundingFixture, ProviderFixture, SECRET


async def test_actual_langchain_json_schema_gateway_request_and_usage(tmp_path, monkeypatch):
    import platform_app.llm.runtime as runtime
    original_client = httpx.AsyncClient
    captured = []

    def gateway(request):
        body = json.loads(request.content)
        captured.append(body)
        assert request.url == "https://gateway.test/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert body["model"] == "corporate-analyst"
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(200, json={"id": "completion-1", "object": "chat.completion", "created": 1,
            "model": "corporate-analyst", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"rationale": "Computed pricing follows policy.",
                                                               "citations": ["policy-v1:0"]})}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 24, "total_tokens": 144}})

    class GatewayClient(original_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(gateway), **kwargs)
    monkeypatch.setattr(runtime.httpx, "AsyncClient", GatewayClient)
    settings = Settings(data_dir=tmp_path, gateway_url="https://gateway.test/v1", api_key=SECRET,
                        model_analyst="corporate-analyst")
    telemetry = Telemetry(tmp_path)
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path)
    try:
        result = await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"price": "3.50"})
        assert result.citations == ["policy-v1:0"]
        assert len(captured) == 1
        assert llm.snapshot()["tokens_in"] == 120 and llm.snapshot()["tokens_out"] == 24
        assert SECRET not in str(captured)
    finally:
        await llm.close()
        telemetry.close()
    assert SECRET not in (tmp_path / "telemetry.jsonl").read_text()


async def test_ambient_langsmith_flags_cannot_enable_prompt_egress(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    provider = ProviderFixture()
    original = provider.ainvoke
    async def check_context(*args, **kwargs):
        assert get_tracing_context()["enabled"] is False
        return await original(*args, **kwargs)
    provider.ainvoke = check_context
    settings, telemetry = Settings(data_dir=tmp_path), Telemetry(tmp_path)
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path, lambda *_: provider)
    try:
        await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"sku": "A"})
    finally:
        await llm.close()
        telemetry.close()


async def test_corrupt_cached_output_is_revalidated_before_reuse(tmp_path):
    settings, telemetry = Settings(data_dir=tmp_path), Telemetry(tmp_path)
    provider = ProviderFixture()
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path, lambda *_: provider)
    try:
        args = {"role": "analyst", "query": "Explain policy", "facts": {"sku": "A"}}
        await llm.generate(Explanation, **args)
        with llm.cache.connection() as db:
            db.execute("UPDATE llm_responses SET response=?", (json.dumps({"rationale": "stale", "citations": ["invented"]}),))
        result = await llm.generate(Explanation, **args)
        assert result.citations == ["policy-v1:0"] and len(provider.calls) == 2
    finally:
        await llm.close()
        telemetry.close()


async def test_broken_cache_and_telemetry_never_fail_a_valid_model_response(tmp_path, monkeypatch):
    settings, telemetry = Settings(data_dir=tmp_path), Telemetry(tmp_path)
    provider = ProviderFixture()
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path, lambda *_: provider)
    def broken(*_args, **_kwargs):
        raise OSError("offline")
    monkeypatch.setattr(llm.cache, "get", broken)
    monkeypatch.setattr(llm.cache, "put", broken)
    monkeypatch.setattr(telemetry, "event", broken)
    try:
        result = await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"sku": "A"})
        assert result.citations
        assert llm.snapshot()["active_calls"] == 0
    finally:
        await llm.close()
        telemetry.close()


async def test_langfuse_egress_failure_stays_off_business_path(tmp_path, monkeypatch):
    settings, telemetry = Settings(data_dir=tmp_path), Telemetry(tmp_path)
    provider = ProviderFixture()
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path, lambda *_: provider)
    def offline(_item):
        raise OSError("unreachable tracing service")
    monkeypatch.setattr(llm.monitor, "_export", offline)
    try:
        result = await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"sku": "A"})
        assert result.citations
    finally:
        await llm.close()
        telemetry.close()
    assert "model_call" in (tmp_path / "telemetry.jsonl").read_text()
    assert llm.monitor.available is False


def test_jsonl_allowlist_never_accepts_prompt_fact_or_secret_fields(tmp_path):
    telemetry = Telemetry(tmp_path)
    telemetry.event("node", run_id="run-1", agent="strategy", status="completed", latency_ms=2,
                    prompt=SECRET, facts={"sales": SECRET}, api_key=SECRET)
    telemetry.close()
    payload = json.loads((tmp_path / "telemetry.jsonl").read_text())
    assert payload["agent"] == "strategy" and SECRET not in str(payload)
    assert "facts" not in payload and "prompt" not in payload


def test_nested_citation_validation_cannot_hide_invalid_child_citations():
    with pytest.raises(ValueError):
        validate_citations({"citations": ["valid"], "details": [{"citations": ["invented"]}]}, {"valid"})
    assert redact({"phone": "12025551234", "note": "a@example.test", "price": "12.50"}) == {
        "phone": "[REDACTED]", "note": "[EMAIL]", "price": "12.50"}
    assert redact("Call +1 555 123 4567. Cost 12345678901.25.") == "Call [PHONE]. Cost 12345678901.25."
