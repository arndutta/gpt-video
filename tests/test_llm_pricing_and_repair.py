"""Attributed LiteLLM rates, unknown aliases and non-sensitive repair diagnostics."""

import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage
import pytest

from platform_app.config import Settings
from platform_app.llm import GroundedLLM
from platform_app.llm.pricing import catalog, estimate_cost
from platform_app.telemetry import Telemetry
from test_grounded_llm import Explanation, GroundingFixture, ProviderFixture, SECRET


def test_litellm_snapshot_provenance_and_provider_model_resolution():
    provenance = catalog()["provenance"]
    assert provenance["source"].startswith("https://raw.githubusercontent.com/BerriAI/litellm/")
    assert len(provenance["source_sha256"]) == 64 and provenance["retrieved_at"]
    raw = SimpleNamespace(response_metadata={"model_name": "gemini-2.5-flash"})
    priced = estimate_cost(Settings(), "analyst", "corporate-alias", raw, 100_000, 20_000)
    assert priced["pricing_source"] == "litellm_snapshot" and priced["pricing_model"] == "gemini-2.5-flash"
    assert priced["cost_usd"] == pytest.approx(.08)


def test_explicit_role_pricing_identifier_and_long_context_rates():
    settings = Settings(pricing_model_strategist="gemini/gemini-2.5-pro")
    raw = SimpleNamespace(response_metadata={"model_name": "gpt-4o-mini"})
    short = estimate_cost(settings, "strategist", "corporate-alias", raw, 1000, 1000)
    assert short["pricing_model"] == "gemini/gemini-2.5-pro" and short["cost_usd"] == pytest.approx(.01125)
    long = estimate_cost(settings, "strategist", "corporate-alias", raw, 1_000_000, 15_000)
    assert long["cost_usd"] == pytest.approx(2.725)


def test_unknown_identifier_uses_explicit_configured_fallback_and_env_mapping(monkeypatch):
    monkeypatch.setenv("LLM_PRICING_MODEL_ANALYST", "unknown-provider-model")
    settings = Settings.from_environment()
    settings.llm_input_cost_per_million, settings.llm_output_cost_per_million = .3, 1.2
    priced = estimate_cost(settings, "analyst", "unknown-alias", None, 1000, 1000)
    assert priced == {"pricing_source": "configured_fallback_rates", "pricing_model": None,
                      "cost_usd": pytest.approx(.0015)}
    assert settings.public()["pricing_models"]["analyst"] == "unknown-provider-model"


async def test_usage_monitor_persists_pricing_provenance_without_provider_bypass(tmp_path):
    settings = Settings(data_dir=tmp_path, pricing_model_analyst="gemini/gemini-2.5-flash-lite")
    telemetry, provider = Telemetry(tmp_path), ProviderFixture()
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path, lambda *_: provider)
    try:
        await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"price": "10.00"})
        monitor = llm.snapshot()
        assert monitor["cost_source"] == "litellm_snapshot"
        assert monitor["pricing_sources"] == {"litellm_snapshot": 1}
        assert monitor["estimated_cost_usd"] == pytest.approx(.000008)
    finally:
        await llm.close()
        telemetry.close()
    events = [json.loads(line) for line in (tmp_path / "telemetry.jsonl").read_text().splitlines()]
    call = next(e for e in events if e["event"] == "model_call")
    assert call["pricing_source"] == "litellm_snapshot"
    assert call["pricing_model"] == "gemini/gemini-2.5-flash-lite"


async def test_repair_contains_safe_actual_schema_location_without_invalid_input(tmp_path):
    settings, telemetry = Settings(data_dir=tmp_path, api_key=SECRET), Telemetry(tmp_path)
    provider = ProviderFixture(results=[{"rationale": {"untrusted": SECRET}, "citations": ["policy-v1:0"], SECRET: SECRET}])
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path, lambda *_: provider)
    try:
        await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"price": "10.00"})
        assert len(provider.calls) == 2
        repair = provider.calls[1][-1][1]
        assert '"loc":["rationale"]' in repair and '"type":"string_type"' in repair
        assert '"loc":["[unknown_field]"]' in repair and '"type":"extra_forbidden"' in repair
        assert SECRET not in repair and '"input"' not in repair and '"ctx"' not in repair
    finally:
        await llm.close()
        telemetry.close()


async def test_repair_citation_failure_uses_static_non_sensitive_diagnostic(tmp_path):
    settings, telemetry = Settings(data_dir=tmp_path, api_key=SECRET), Telemetry(tmp_path)
    provider = ProviderFixture(results=[{"rationale": "Invalid citation", "citations": [SECRET]}])
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path, lambda *_: provider)
    try:
        await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"price": "10.00"})
        repair = provider.calls[1][-1][1]
        assert "supplied_citations_required" in repair and SECRET not in repair
        assert len(provider.calls) == 2
    finally:
        await llm.close()
        telemetry.close()
