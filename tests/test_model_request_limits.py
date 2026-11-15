"""Configured application-envelope caps reject complete inputs without provider calls."""

from types import SimpleNamespace
import json

import pytest

from platform_app.config import Settings
from platform_app.llm import GroundedLLM, GroundedLLMError
from platform_app.llm.request_limits import envelope_size
from platform_app.telemetry import Telemetry
from test_grounded_llm import Explanation, GroundingFixture, ProviderFixture


def runtime(tmp_path, **configuration):
    settings = Settings(data_dir=tmp_path, model_analyst="test-model", **configuration)
    grounding, provider, telemetry = GroundingFixture(), ProviderFixture(), Telemetry(tmp_path)
    initialized = []
    def factory(*_args):
        initialized.append(True)
        return provider
    llm = GroundedLLM(lambda: settings, grounding, telemetry, tmp_path, factory)
    return SimpleNamespace(settings=settings, grounding=grounding, provider=provider,
                           telemetry=telemetry, llm=llm, initialized=initialized)


async def close(owner):
    await owner.llm.close()
    owner.telemetry.close()


async def test_oversized_complete_envelope_fails_before_provider_initialization(tmp_path):
    owner = runtime(tmp_path, llm_max_envelope_bytes=1)
    try:
        with pytest.raises(GroundedLLMError) as caught:
            await owner.llm.generate(Explanation, role="analyst", query="Explain policy", facts={"price": "10.00"})
        assert caught.value.code == "model_envelope_too_large"
        assert "messages/schema" in str(caught.value) and "token-context" in str(caught.value)
        assert len(owner.grounding.calls) == 1, "The limit includes freshly retrieved evidence."
        assert not owner.initialized and not owner.provider.calls
        assert owner.llm.snapshot()["calls"] == 0
    finally:
        await close(owner)


async def test_exact_utf8_envelope_cap_accepts_all_messages_and_schema_without_truncation(tmp_path):
    owner = runtime(tmp_path)
    facts = {"price": "10.00", "note": "政策と不確実性"}
    try:
        await owner.llm.generate(Explanation, role="analyst", query="Explain policy", facts=facts)
        messages = owner.provider.calls[0]
        size = envelope_size(Explanation, messages)
        owner.settings.llm_max_envelope_bytes = size
        # Keep the payload length constant, but invalidate the previous numerical-context cache.
        facts["price"] = "10.01"
        await owner.llm.generate(Explanation, role="analyst", query="Explain policy", facts=facts)
        assert len(owner.provider.calls) == 2
        assert envelope_size(Explanation, owner.provider.calls[1]) == size
        assert json.loads(owner.provider.calls[1][1][1])["facts"]["note"] == "政策と不確実性"
        assert '"price":"10.01"' in owner.provider.calls[1][1][1]
        assert owner.provider.schema is Explanation
        owner.settings.llm_max_envelope_bytes = size - 1
        facts["price"] = "10.02"
        with pytest.raises(GroundedLLMError) as caught:
            await owner.llm.generate(Explanation, role="analyst", query="Explain policy", facts=facts)
        assert caught.value.code == "model_envelope_too_large"
        assert len(owner.provider.calls) == 2
    finally:
        await close(owner)


async def test_repair_growth_is_checked_before_a_second_provider_request(tmp_path):
    owner = runtime(tmp_path)
    arguments = {"role": "analyst", "query": "Explain policy", "facts": {"price": "10.00"}}
    try:
        await owner.llm.generate(Explanation, **arguments)
        initial_size = envelope_size(Explanation, owner.provider.calls[0])
        # Force a fresh provider call with an equal-length numerical context.
        arguments["facts"]["price"] = "10.01"
        owner.settings.llm_max_envelope_bytes = initial_size
        owner.provider.results = [{"rationale": "Invalid citation", "citations": ["invented"]}]
        with pytest.raises(GroundedLLMError) as caught:
            await owner.llm.generate(Explanation, **arguments)
        assert caught.value.code == "model_envelope_too_large"
        assert len(owner.provider.calls) == 2, "The larger repair envelope must never reach the provider."
        assert owner.llm.snapshot()["active_calls"] == 0
        assert owner.llm.snapshot()["cache"]["entries"] == 1, "The invalid result is never cached."
    finally:
        await close(owner)


def test_batch_size_and_envelope_limit_are_explicit_server_environment_choices(monkeypatch):
    assert Settings().strategy_batch_size == 25
    assert Settings().llm_max_envelope_bytes is None
    monkeypatch.setenv("LLM_STRATEGY_BATCH_SIZE", "3")
    monkeypatch.setenv("LLM_MAX_ENVELOPE_BYTES", "16384")
    settings = Settings.from_environment()
    assert settings.strategy_batch_size == 3 and settings.llm_max_envelope_bytes == 16384


@pytest.mark.parametrize("configuration", [{"strategy_batch_size": 0}, {"strategy_batch_size": 26},
                                           {"strategy_batch_size": 1.5}, {"llm_max_envelope_bytes": 0}])
def test_invalid_batch_or_envelope_configuration_is_rejected(configuration):
    with pytest.raises(ValueError):
        Settings(**configuration)
