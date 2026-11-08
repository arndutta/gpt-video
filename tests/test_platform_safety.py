"""Regression checks for malformed upstream data, secret handling, and work ownership."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import traceback

from fastapi.testclient import TestClient
import httpx
import pytest

from platform_app.app import create_app
from platform_app.config import RunRequest, Settings
from platform_app.runs import RunManager
from platform_app.storage import Store


AS_OF = "2026-11-08T00:00:00+00:00"
SECRET = "safety-runtime-secret-294017"


@pytest.mark.parametrize("payload", [
    b"{not-json", [], "unexpected string", None,
    {"items": {}, "total": 0, "as_of": AS_OF},
    {"items": [7], "total": 1, "as_of": AS_OF},
    {"items": [], "total": "0", "as_of": AS_OF},
    {"items": [], "total": -1, "as_of": AS_OF},
    {"items": [], "total": True, "as_of": AS_OF},
    {"items": [], "total": 0, "as_of": []},
])
def test_malformed_upstream_catalog_is_a_service_error_not_500(tmp_path, payload):
    def upstream(_request):
        if isinstance(payload, bytes):
            return httpx.Response(200, content=payload, headers={"Content-Type": "application/json"})
        return httpx.Response(200, json=payload)

    app = create_app(Settings(data_dir=tmp_path, commerce_url="http://commerce"),
                     commerce_transport=httpx.MockTransport(upstream))
    with TestClient(app) as client:
        response = client.get("/api/catalog")
        assert response.status_code == 503, response.text
        assert "Commerce" in response.text


@pytest.mark.parametrize("endpoint", ["/api/catalog?q=item", "/api/catalog/summary"])
def test_malformed_catalog_records_cannot_crash_catalog_views(tmp_path, endpoint):
    def upstream(request):
        if request.url.path == "/inventory":
            return httpx.Response(200, json={"items": [], "total": 0, "as_of": AS_OF})
        return httpx.Response(200, json={"items": [{}], "total": 1, "as_of": AS_OF})

    app = create_app(Settings(data_dir=tmp_path, commerce_url="http://commerce"),
                     commerce_transport=httpx.MockTransport(upstream))
    with TestClient(app) as client:
        response = client.get(endpoint)
        assert response.status_code == 503, response.text


def test_malformed_health_refuses_run_without_creating_a_record(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, commerce_url="http://commerce"),
                     commerce_transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[])))
    with TestClient(app) as client:
        assert client.post("/api/runs", json={"iterations": 100}).status_code == 503
        assert not client.get("/api/runs").json()["items"]
        assert client.get("/api/health").json()["status"] == "degraded"


def test_invalid_environment_error_omits_embedded_credentials(monkeypatch):
    monkeypatch.setenv("COMMERCE_URL", f"http://operator:{SECRET}@127.0.0.1:8001")
    with pytest.raises(ValueError) as caught:
        Settings.from_environment()
    assert "commerce_url" in str(caught.value)
    assert SECRET not in str(caught.value)
    rendered = "".join(traceback.format_exception(caught.type, caught.value, caught.tb))
    assert SECRET not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_before_stop", [False, True])
async def test_stop_owns_numeric_worker_and_busy_slot_until_thread_finishes(tmp_path, monkeypatch,
                                                                           cancel_before_stop):
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def blocked_analysis(*_args, **_kwargs):
        started.set()
        try:
            if not release.wait(timeout=5):
                raise RuntimeError("Test did not release numerical worker in time")
            return {"aggregate": {}, "executable": False}
        finally:
            finished.set()

    class CommerceFixture:
        async def context(self, **_kwargs):
            return {"catalog": [{"sku": "SKU-TEST"}], "sales": [], "inventory": [], "as_of": AS_OF}

    monkeypatch.setattr("platform_app.runs.analyze_catalog", blocked_analysis)
    manager = RunManager(Settings(data_dir=tmp_path), Store(tmp_path), CommerceFixture())
    run = manager.start(RunRequest(iterations=100))
    stop_task = None
    try:
        assert await asyncio.to_thread(started.wait, 2), "Numerical thread did not start"
        assert manager.busy and manager.workers
        if cancel_before_stop:
            next(iter(manager.tasks)).cancel()
            await asyncio.sleep(.02)
            assert manager.busy and manager.workers
        stop_task = asyncio.create_task(manager.stop())
        await asyncio.sleep(.03)
        assert manager.stopping and manager.busy
        assert not stop_task.done(), "Shutdown released ownership before the numerical thread finished"
        assert not finished.is_set()
        with pytest.raises(RuntimeError):
            manager.start(RunRequest(iterations=100))
        release.set()
        await asyncio.wait_for(stop_task, 2)
        assert finished.is_set() and not manager.busy and not manager.workers
        assert manager.store.get_run(run["id"])["status"] == "interrupted"
    finally:
        release.set()
        if stop_task is not None:
            await asyncio.wait_for(asyncio.gather(stop_task, return_exceptions=True), 3)
        else:
            await asyncio.wait_for(manager.stop(), 3)


def test_runtime_settings_swap_preserves_prior_snapshot(tmp_path):
    initial = Settings(data_dir=tmp_path, gateway_url="https://old-gateway.example.test/v1")
    app = create_app(initial)
    with TestClient(app) as client:
        previous = app.state.settings
        response = client.patch("/api/settings", json={
            "gateway_url": "https://new-gateway.example.test/v1", "gateway_port": 4443, "api_key": SECRET,
        })
        assert response.status_code == 200, response.text
        current = app.state.settings
        assert current is not previous, "Runtime update mutated the captured settings object"
        assert previous.gateway_url == "https://old-gateway.example.test/v1"
        assert previous.gateway_port is None and previous.api_key is None
        assert current.gateway_base_url == "https://new-gateway.example.test:4443/v1"
        assert current.api_key.get_secret_value() == SECRET
        assert app.state.runs.settings is current
        assert SECRET not in response.text


def test_concurrent_settings_updates_preserve_independent_fields(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        updates = [{"gateway_url": "https://gateway.example.test/v1"}, {"gateway_port": 4555}]
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda payload: client.patch("/api/settings", json=payload), updates))
        assert all(response.status_code == 200 for response in responses)
        settings = client.get("/api/settings").json()
        assert settings["gateway_url"] == "https://gateway.example.test/v1"
        assert settings["gateway_port"] == 4555
