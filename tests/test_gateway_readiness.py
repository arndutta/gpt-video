"""Availability checks use the current secret snapshot without claiming generation."""

import asyncio
import json

import httpx
import pytest

from platform_app.config import Settings
from platform_app.gateway import GatewayError, GatewayReadiness, ROLES, verify_gateway
from platform_app.storage import Store
from platform_app.app import create_app
from fastapi.testclient import TestClient
from test_platform import integrated

SECRET = "private-gateway-check-827481"


def settings(tmp_path):
    return Settings(data_dir=tmp_path, gateway_url="https://gateway.test/v1", api_key=SECRET,
                    **{"model_" + role: role for role in ROLES})


async def test_four_roles_verified_with_safe_authenticated_model_list(tmp_path):
    def response(request):
        assert str(request.url) == "https://gateway.test/v1/models"
        assert request.headers["authorization"] == "Bearer " + SECRET
        return httpx.Response(200, json={"data": [{"id": r} for r in ROLES]})
    result = await verify_gateway(settings(tmp_path), httpx.MockTransport(response))
    assert result["verified"] and not result["structured_output_verified"]
    assert SECRET not in json.dumps(result)


async def test_missing_aliases_report_actual_safe_available_models(tmp_path):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"data": [{"id": "router"}, {"id": SECRET}]}))
    with pytest.raises(GatewayError) as caught:
        await verify_gateway(settings(tmp_path), transport)
    assert caught.value.code == "missing_models"
    assert caught.value.missing_models == ["analyst", "narrator", "strategist"]
    assert SECRET not in repr(caught.value.available_models)


@pytest.mark.parametrize("payload", [{}, {"data": "invalid"}, {"data": [1]}, {"data": [{"id": True}]},
                                     {"data": [{"id": "x" * 201}]}, {"data": [{"id": "x"}] * 4097}])
async def test_invalid_model_list_fails_safely(tmp_path, payload):
    with pytest.raises(GatewayError, match="Gateway model verification failed"):
        await verify_gateway(settings(tmp_path), httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))


async def test_transient_http_errors_do_not_echo_gateway_response_or_credentials(tmp_path):
    transport = httpx.MockTransport(lambda _: httpx.Response(401, text=SECRET))
    with pytest.raises(GatewayError) as caught:
        await verify_gateway(settings(tmp_path), transport)
    assert SECRET not in str(caught.value)


async def test_unconfigured_check_never_opens_a_connection(tmp_path):
    def forbidden(_):
        raise AssertionError("An unconfigured gateway must not make a request")
    with pytest.raises(GatewayError) as caught:
        await verify_gateway(Settings(data_dir=tmp_path), httpx.MockTransport(forbidden))
    assert caught.value.code == "unconfigured"


async def test_verified_state_invalidates_when_current_key_or_alias_changes(tmp_path):
    current = settings(tmp_path)
    store = Store(tmp_path)
    checker = GatewayReadiness(lambda: current, store, httpx.MockTransport(lambda _: httpx.Response(
        200, json={"data": [{"id": r} for r in ROLES]})))
    assert (await checker.check())["verified"]
    assert checker.current()["verified"]
    current = current.model_copy(update={"model_analyst": "replacement"})
    assert not checker.current()["verified"] and checker.current()["checked_at"] is None
    assert SECRET not in json.dumps(store.list_audit())


async def test_settings_changed_during_probe_never_publish_stale_verified_status(tmp_path):
    current = settings(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    async def delayed(_):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"data": [{"id": r} for r in ROLES]})
    checker = GatewayReadiness(lambda: current, Store(tmp_path), httpx.MockTransport(delayed))
    work = asyncio.create_task(checker.check())
    await entered.wait()
    current = current.model_copy(update={"api_key": None})
    release.set()
    result = await work
    assert not result["verified"] and result["status"] == "configuration_changed"
    assert not checker.current()["verified"]


def test_runtime_gateway_check_reports_missing_settings_without_fake_success(integrated):
    client, *_ = integrated
    result = client.post("/api/gateway/check")
    assert result.status_code == 200
    assert result.json()["status"] == "unconfigured" and not result.json()["verified"]
    assert client.get("/api/health").json()["gateway"]["verified"] is False


def test_explicit_grounded_startup_fails_before_accepting_unconfigured_runs(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, startup_mode="grounded"))
    with pytest.raises(RuntimeError, match="Grounded startup requires verified"):
        with TestClient(app):
            pytest.fail("An unverified grounded application must not finish startup")


def test_startup_mode_environment_is_typed(monkeypatch):
    monkeypatch.setenv("PRICING_STARTUP_MODE", "grounded")
    assert Settings.from_environment().startup_mode == "grounded"
    monkeypatch.setenv("PRICING_STARTUP_MODE", "unbounded")
    with pytest.raises(ValueError, match="Invalid environment settings"):
        Settings.from_environment()


def test_verified_grounded_lifespan_reports_actual_child_check(tmp_path, monkeypatch):
    from platform_app.gateway import verify_gateway as real_verify
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"data": [{"id": r} for r in ROLES]}))
    async def verify(config, _transport=None):
        return await real_verify(config, transport)
    monkeypatch.setattr("platform_app.gateway.verify_gateway", verify)
    config = settings(tmp_path).model_copy(update={"startup_mode": "grounded"})
    app = create_app(config, commerce_transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with TestClient(app) as client:
        gateway = client.get("/api/health").json()["gateway"]
        assert gateway["verified"] and gateway["startup_mode"] == "grounded"
        events = app.state.store.list_audit()
        assert any(e["action"] == "gateway_verified" and e["actor"] == "system" for e in events)
        assert SECRET not in json.dumps(events)
