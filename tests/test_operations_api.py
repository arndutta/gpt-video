"""Read/write control contracts and discovery must not create a bypass to Commerce."""

import json

import httpx
import pytest

from platform_app.config import Settings
from platform_app.feeds import LiveJSONFeed, configured_feed, SyntheticFeed
from test_platform import integrated, complete_preview


def test_new_controls_default_supervised_off_and_secrets_remain_memory_only(integrated):
    client, _, commerce, _, _, directory = integrated
    before = commerce.get("/prices").json()
    assert client.get("/api/control").json()["mode"] == "supervised"
    assert client.get("/api/loop").json()["running"] is False
    for path in ("/api/recommendations", "/api/feedback", "/api/scenarios/saved", "/api/loop/history"):
        assert client.get(path).json()["items"] == []
    assert client.patch("/api/control/mode", json={"mode": "assisted", "hold_seconds": 2}).json()["mode"] == "assisted"
    killed = client.post("/api/control/kill").json()
    assert killed["mode"] == "supervised" and not killed["loop"]["running"]
    assert commerce.get("/prices").json() == before
    assert client.get("/api/monitor").json()["active_calls"] == 0
    assert client.get("/api/settings").json()["cache"]["available"] is True
    assert client.get("/api/dashboard").json()["realized"]["revenue"] is None
    assert client.get("/api/audit/export").headers["content-disposition"].endswith('"pricing-audit.json"')


def test_no_cross_site_mode_price_loop_or_settings_writes(integrated):
    client, *_ = integrated
    for path, method, body in (("/api/control/mode", "patch", {"mode": "autonomous"}),
                               ("/api/control/kill", "post", {}),
                               ("/api/settings", "patch", {}),
                               ("/api/runs", "post", {}),
                               ("/a2a", "post", {})):
        assert getattr(client, method)(path, json=body, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.get("/api/control").json()["mode"] == "supervised"
    assert client.post("/api/control/kill", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_known_credential_pasted_into_public_settings_is_redacted(integrated):
    client, *_ = integrated
    secret = "runtime-secret-alias-mistake-946812"
    response = client.patch("/api/settings", json={"api_key": secret, "model_analyst": secret})
    assert response.status_code == 200 and secret not in response.text
    public = client.get("/api/settings")
    assert secret not in public.text and public.json()["key_configured"] is True
    assert public.json()["models"]["analyst"] == "[REDACTED]"


def test_typed_personal_pricing_and_unconfigured_grounded_tasks_fail_closed(integrated):
    client, _, commerce, *_ = integrated
    before = commerce.get("/price-history").json()["items"]
    assert client.post("/api/runs", json={"kind": "grounded"}).status_code == 409
    assert client.post("/api/runs", json={"customer_id": "personal-1"}).status_code == 422
    assert client.post("/api/recommendations/missing/decision", json={"action": "approve", "expected_revision": 1}).status_code == 404
    assert client.post("/api/recommendations/bulk", json={"ids": ["missing"], "expected_revisions": {"missing": 1}}).status_code == 409
    assert commerce.get("/price-history").json()["items"] == before


def test_scenarios_save_distributions_stress_compare_and_never_approve(integrated):
    client, _, commerce, *_ = integrated
    products = client.get("/api/catalog").json()["items"][:2]
    body = {"items": [{"sku": p["sku"], "candidate_price": p["current_price"]} for p in products],
            "iterations": 100, "seed": 99, "horizon_days": 7, "stress": "none"}
    before = commerce.get("/prices").json()
    result = client.post("/api/scenarios/batch", json=body)
    assert result.status_code == 200, result.text
    report = result.json()
    assert len(report["items"]) == 2 and report["aggregate"]["sku_count"] == 2
    for item in report["items"]:
        assert item["forecast"] == item["current_forecast"]
        assert item["baseline"]["forecast"] and "ai_forecast" in item
    saved = client.post("/api/scenarios/saved", json={"name": "Matched seven-day comparison", "request": body})
    assert saved.status_code == 201, saved.text
    assert saved.json()["result"] == report
    assert client.get("/api/scenarios/saved").json()["items"][0]["id"] == saved.json()["id"]
    stressed = client.post("/api/scenarios/batch", json={**body, "stress": "cost_spike"}).json()
    assert stressed["items"][0]["forecast"]["gross_profit"]["mean"] < report["items"][0]["forecast"]["gross_profit"]["mean"]
    assert client.get("/api/recommendations").json()["items"] == []
    assert commerce.get("/prices").json() == before


def test_bounded_a2a_card_method_errors_and_existing_task_poll(integrated):
    client, *_ = integrated
    card = client.get("/.well-known/agent-card.json").json()
    assert card["protocolVersion"] == "0.3.0" and not card["capabilities"]["streaming"]
    assert client.post("/a2a", content="invalid").json()["error"]["code"] == -32700
    assert client.post("/a2a", json=[]).json()["error"]["code"] == -32600
    assert client.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "tasks/cancel"}).json()["error"]["code"] == -32601
    missing = client.post("/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": "missing"}}).json()
    assert missing["error"]["code"] == -32001
    run = complete_preview(client, {"iterations": 100})
    result = client.post("/a2a", json={"jsonrpc": "2.0", "id": 3, "method": "tasks/get", "params": {"id": run["id"]}}).json()
    assert result["result"]["status"]["state"] == "completed"
    denied = client.post("/a2a", json={"jsonrpc": "2.0", "id": 4, "method": "message/send", "params": {"message": {
        "messageId": "fixture", "role": "user", "parts": [{"kind": "data", "data": {"customer_id": "no"}}]}}}).json()
    assert denied["error"]["code"] == -32602


async def test_optional_live_competitor_feed_opt_in_and_bounded_contract(tmp_path):
    default = Settings(data_dir=tmp_path)
    assert isinstance(configured_feed(default), SyntheticFeed)
    with pytest.raises(ValueError):
        LiveJSONFeed(default)
    settings = Settings(data_dir=tmp_path, live_competitor_enabled=True, live_competitor_url="https://feed.example/quotes")
    quote = {"sku": "SKU-1", "competitor": "Market", "price": "12.00", "observed_at": "2026-11-09"}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"items": [quote]}))
    assert await LiveJSONFeed(settings, transport).fetch() == [quote]
    invalid = httpx.MockTransport(lambda request: httpx.Response(200, json={"items": [{**quote, "email": "private@example.test"}]}))
    with pytest.raises(ValueError):
        await LiveJSONFeed(settings, invalid).fetch()
    redirect = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://other.example/"}))
    with pytest.raises(ValueError):
        await LiveJSONFeed(settings, redirect).fetch()
