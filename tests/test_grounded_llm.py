"""Grounding, typed repair, cache invalidation, and redaction at the model boundary."""

import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, Field
import pytest

from platform_app.config import Settings
from platform_app.llm import GroundedLLM, GroundedLLMError
from platform_app.rag.models import EvidenceChunk, RetrievalContext
from platform_app.telemetry import Telemetry


SECRET = "runtime-private-key-834927"


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rationale: str
    citations: list[str] = Field(min_length=1)


class GroundingFixture:
    def __init__(self):
        self.version, self.calls, self.fail = 1, [], False

    async def retrieve(self, query, role):
        self.calls.append((query, role))
        if self.fail:
            raise RuntimeError(SECRET)
        return RetrievalContext(query=query, role=role, corpus_version=self.version, chunks=[EvidenceChunk(
            citation_id=f"policy-v{self.version}:0", source_id="policy", title="Policy", collection="user_uploads",
            version=str(self.version), chunk_index=0, text="Keep prices above the margin floor.",
            start_char=0, end_char=40)])


class ProviderFixture:
    def __init__(self, results=None):
        self.results, self.calls, self.configs = list(results or []), [], []

    def with_structured_output(self, schema, **options):
        self.schema, self.options = schema, options
        return self

    async def ainvoke(self, messages, config):
        self.calls.append(messages.copy())
        self.configs.append(config)
        result = self.results.pop(0) if self.results else {"rationale": "The computed move meets policy.", "citations": ["policy-v1:0"]}
        if isinstance(result, Exception):
            raise result
        return {"raw": AIMessage(content="", usage_metadata={"input_tokens": 40, "output_tokens": 10, "total_tokens": 50}),
                "parsed": result, "parsing_error": None}


@pytest.fixture
def runtime(tmp_path):
    settings = Settings(data_dir=tmp_path, api_key=SECRET, model_analyst="analyst", model_strategist="strategy")
    grounding, provider, telemetry = GroundingFixture(), ProviderFixture(), Telemetry(tmp_path)
    llm = GroundedLLM(lambda: settings, grounding, telemetry, tmp_path, lambda *_: provider)
    return SimpleNamespace(settings=settings, grounding=grounding, provider=provider, telemetry=telemetry,
                           llm=llm, directory=tmp_path)


async def generate(runtime, **overrides):
    return await runtime.llm.generate(Explanation, **{"role": "analyst", "query": "Explain pricing policy",
        "facts": {"sku": "SKU-1", "proposed_price": "12.50"}, **overrides})


async def close(runtime):
    await runtime.llm.close()
    runtime.telemetry.close()


async def test_typed_grounded_response_uses_schema_and_records_real_usage(runtime):
    try:
        result = await generate(runtime)
        assert isinstance(result, Explanation) and result.citations == ["policy-v1:0"]
        assert runtime.provider.options == {"method": "json_schema", "include_raw": True, "strict": True}
        sent = str(runtime.provider.calls[0])
        assert "proposed_price" in sent and "12.50" in sent and "policy-v1:0" in sent
        stats = runtime.llm.snapshot()
        assert stats["tokens_in"] == 40 and stats["tokens_out"] == 10 and stats["active_calls"] == 0
        assert stats["estimated_cost_usd"] > 0
    finally:
        await close(runtime)


@pytest.mark.parametrize("bad", [{"rationale": "uncited", "citations": []},
                                  {"rationale": "invented", "citations": ["made-up"]},
                                  {"rationale": "extra", "citations": ["policy-v1:0"], "price": "1.00"}])
async def test_invalid_structure_or_citation_gets_exactly_one_repair(runtime, bad):
    runtime.provider.results = [bad]
    try:
        result = await generate(runtime)
        assert result.citations and len(runtime.provider.calls) == 2
        assert "Repair the response" in str(runtime.provider.calls[1][-1])
    finally:
        await close(runtime)


async def test_second_invalid_response_is_typed_safe_failure(runtime):
    runtime.provider.results = [{"rationale": SECRET, "citations": ["bad"]}] * 3
    try:
        with pytest.raises(GroundedLLMError) as caught:
            await generate(runtime)
        assert caught.value.code == "structured_output_invalid" and SECRET not in str(caught.value)
        assert len(runtime.provider.calls) == 2 and runtime.llm.snapshot()["cache"]["entries"] == 0
    finally:
        await close(runtime)


async def test_grounding_failure_prevents_provider_call_and_cache_bypass(runtime):
    try:
        await generate(runtime)
        runtime.grounding.fail = True
        with pytest.raises(GroundedLLMError, match="Required grounding"):
            await generate(runtime)
        assert len(runtime.provider.calls) == 1
    finally:
        await close(runtime)


async def test_prompts_outputs_and_persistence_are_redacted(runtime):
    runtime.provider.results = [{"rationale": f"Contact a@example.test using {SECRET}", "citations": ["policy-v1:0"]}]
    try:
        result = await generate(runtime, facts={"sku": "SKU-1", "note": SECRET, "access_token": "other-private"},
                                prompt="Explain without api_key=accidental-secret or a@example.test")
        sent = str(runtime.provider.calls)
        assert SECRET not in sent and "accidental-secret" not in sent and "a@example.test" not in sent
        assert SECRET not in result.rationale and "a@example.test" not in result.rationale
    finally:
        await close(runtime)
    for path in runtime.directory.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes(), path
            assert b"accidental-secret" not in path.read_bytes(), path


@pytest.mark.parametrize("facts", [{"customer_id": "C-1"}, {"nested": [{"loyalty_score": 5}]}])
async def test_personal_pricing_is_rejected_before_model_or_retrieval(runtime, facts):
    try:
        with pytest.raises(GroundedLLMError) as caught:
            await generate(runtime, facts=facts)
        assert caught.value.code == "personal_pricing_forbidden"
        assert not runtime.provider.calls and not runtime.grounding.calls
    finally:
        await close(runtime)


async def test_persistent_exact_and_conservative_semantic_hits(runtime):
    try:
        first = await generate(runtime)
        assert await generate(runtime) == first
        assert await generate(runtime, query="  EXPLAIN   pricing policy  ") == first
        assert len(runtime.provider.calls) == 1 and len(runtime.grounding.calls) == 3
        assert runtime.llm.snapshot()["cache"]["exact_hits"] == 1
        assert runtime.llm.snapshot()["cache"]["semantic_hits"] == 1
        await runtime.llm.close()
        runtime.llm = GroundedLLM(lambda: runtime.settings, runtime.grounding, runtime.telemetry,
                                 runtime.directory, lambda *_: runtime.provider)
        assert await generate(runtime) == first and len(runtime.provider.calls) == 1
    finally:
        await close(runtime)


@pytest.mark.parametrize("change", ["price", "policy", "upload", "model", "role", "intent"])
async def test_changed_decision_context_cannot_reuse_cached_response(runtime, change):
    try:
        await generate(runtime)
        args = {}
        if change == "price":
            args["facts"] = {"sku": "SKU-1", "proposed_price": "12.55"}
        elif change == "policy":
            args["policy_version"] = "v2"
        elif change == "upload":
            runtime.grounding.version = 2
            runtime.provider.results = [{"rationale": "Changed policy.", "citations": ["policy-v2:0"]}]
        elif change == "model":
            runtime.settings.model_analyst = "different-model"
        elif change == "role":
            args["role"] = "strategist"
        else:
            args["query"] = "Explain why the price must not change"
        await generate(runtime, **args)
        assert len(runtime.provider.calls) == 2
    finally:
        await close(runtime)


async def test_unconfigured_gateway_and_transport_errors_are_safe(runtime):
    try:
        runtime.llm.provider_factory = None
        with pytest.raises(GroundedLLMError) as caught:
            await generate(runtime)
        assert caught.value.code == "gateway_unconfigured"
        runtime.llm.provider_factory = lambda *_: runtime.provider
        runtime.provider.results = [RuntimeError(SECRET)]
        with pytest.raises(GroundedLLMError) as caught:
            await generate(runtime)
        assert caught.value.code == "gateway_call_failed" and SECRET not in str(caught.value)
        assert runtime.llm.snapshot()["active_calls"] == 0
    finally:
        await close(runtime)


async def test_retryable_statuses_have_bounded_backoff(runtime):
    class Overloaded(RuntimeError):
        status_code = 429
    runtime.provider.results = [Overloaded(SECRET), Overloaded(SECRET)]
    try:
        await generate(runtime)
        assert len(runtime.provider.calls) == 3
        assert runtime.llm.snapshot()["failed_calls"] == 2
    finally:
        await close(runtime)


async def test_cancellation_releases_active_counter(runtime):
    entered = asyncio.Event()
    async def blocked(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()
    runtime.provider.ainvoke = blocked
    try:
        task = asyncio.create_task(generate(runtime))
        await asyncio.wait_for(entered.wait(), 2)
        assert runtime.llm.snapshot()["active_calls"] == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime.llm.snapshot()["active_calls"] == 0
    finally:
        await close(runtime)
