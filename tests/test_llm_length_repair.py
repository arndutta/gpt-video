"""A real SDK length-limit error receives one safe repair and retains token accounting."""

import json

import httpx
import pytest

from platform_app.config import Settings
from platform_app.llm import GroundedLLM, GroundedLLMError
from platform_app.telemetry import Telemetry
from test_grounded_llm import Explanation, GroundingFixture, SECRET


@pytest.mark.parametrize("repair_succeeds", [True, False])
async def test_actual_gateway_truncation_gets_one_repair_without_echoing_partial_output(tmp_path, monkeypatch, repair_succeeds):
    from platform_app.llm import runtime
    requests = []
    original_client = httpx.AsyncClient

    def gateway(request):
        body = json.loads(request.content)
        requests.append(body)
        truncated = len(requests) == 1 or not repair_succeeds
        content = '{"rationale":"' + SECRET if truncated else json.dumps({
            "rationale": "The computed price meets policy.", "citations": ["policy-v1:0"]})
        return httpx.Response(200, json={"id": "length-fixture", "object": "chat.completion", "created": 1,
            "model": "fixture-model", "choices": [{"index": 0,
                "finish_reason": "length" if truncated else "stop",
                "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}})

    class GatewayClient(original_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(gateway), **kwargs)

    monkeypatch.setattr(runtime.httpx, "AsyncClient", GatewayClient)
    settings = Settings(data_dir=tmp_path, gateway_url="https://gateway.test/v1", api_key=SECRET,
                        model_analyst="fixture-model", llm_transport_retries=2)
    telemetry = Telemetry(tmp_path)
    llm = GroundedLLM(lambda: settings, GroundingFixture(), telemetry, tmp_path)
    try:
        if repair_succeeds:
            answer = await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"price": "10.00"})
            assert answer.citations == ["policy-v1:0"]
        else:
            with pytest.raises(GroundedLLMError) as caught:
                await llm.generate(Explanation, role="analyst", query="Explain policy", facts={"price": "10.00"})
            assert caught.value.code == "structured_output_invalid" and SECRET not in str(caught.value)
        assert len(requests) == 2
        repair = requests[1]["messages"][-1]["content"]
        assert "structured_output_truncated" in repair and "concise wording" in repair
        assert SECRET not in repair and SECRET not in str(requests)
        assert requests[0]["response_format"] == requests[1]["response_format"]
        assert requests[0]["messages"] == requests[1]["messages"][:-1]
        usage = llm.snapshot()
        assert usage["active_calls"] == 0 and usage["calls"] == 2
        assert usage["tokens_in"] == 240 and usage["tokens_out"] == 160
        assert usage["cache"]["entries"] == int(repair_succeeds)
    finally:
        await llm.close()
        telemetry.close()
    assert SECRET not in (tmp_path / "telemetry.jsonl").read_text()
