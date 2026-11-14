"""Operational metadata failures cannot suppress independent sinks or model results."""

import sqlite3
from types import SimpleNamespace

import pytest

from platform_app.config import Settings
from platform_app.llm import GroundedLLM
from platform_app.llm.monitor import CallMonitor, usage
from platform_app.telemetry import Telemetry
from test_grounded_llm import Explanation, GroundingFixture, ProviderFixture


def test_jsonl_failure_preserves_usage_history_and_other_export(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path)
    telemetry = Telemetry(tmp_path)
    monitor = CallMonitor(tmp_path, telemetry, lambda: settings)
    exported = []

    def broken_jsonl(*_args, **_kwargs):
        raise OSError("Local metadata sink unavailable")

    monkeypatch.setattr(telemetry, "event", broken_jsonl)
    monkeypatch.setattr(monitor, "_export", exported.append)
    try:
        monitor.complete(monitor.begin(), role="analyst", model="fixture-model", run_id="run-1",
                         settings=settings, raw=SimpleNamespace(
                             usage_metadata={"input_tokens": 40, "output_tokens": 10}))
    finally:
        monitor.close()
        telemetry.close()
    with sqlite3.connect(tmp_path / "app.db") as db:
        rows = db.execute("SELECT run_id,status,tokens_in,tokens_out FROM llm_usage").fetchall()
    assert rows == [("run-1", "completed", 40, 10)]
    assert len(exported) == 1 and exported[0]["run_id"] == "run-1"
    assert monitor.snapshot()["dropped_events"] == 0
    assert monitor.snapshot()["telemetry_available"] is False


@pytest.mark.parametrize(("standard", "response", "expected"), [
    ("input_tokens", {}, (0, 0)),
    (None, "token_usage", (0, 0)),
    (None, {"token_usage": "prompt_tokens"}, (0, 0)),
    ([40, 10], {"token_usage": {"prompt_tokens": 40, "completion_tokens": 10}}, (40, 10)),
])
def test_usage_ignores_malformed_metadata_containers(standard, response, expected):
    assert usage(SimpleNamespace(usage_metadata=standard, response_metadata=response)) == expected


async def test_malformed_usage_does_not_turn_a_valid_cited_response_into_gateway_failure(tmp_path):
    class Provider(ProviderFixture):
        async def ainvoke(self, *args, **kwargs):
            response = await super().ainvoke(*args, **kwargs)
            response["raw"] = SimpleNamespace(usage_metadata="input_tokens", response_metadata={})
            return response

    settings, telemetry = Settings(data_dir=tmp_path), Telemetry(tmp_path)
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path, lambda *_: Provider())
    try:
        answer = await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"sku": "A"})
        assert answer.citations == ["policy-v1:0"]
        snapshot = llm.snapshot()
        assert snapshot["calls"] == 1 and snapshot["active_calls"] == 0
        assert snapshot["tokens_in"] == snapshot["tokens_out"] == 0
    finally:
        await llm.close()
        telemetry.close()
