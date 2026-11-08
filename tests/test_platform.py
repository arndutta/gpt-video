"""HTTP-level integration of the platform with a separate Commerce ASGI app."""

from datetime import datetime, timezone
import sqlite3
import time

from fastapi.testclient import TestClient
import httpx
import pytest

from commerce.app import create_app as create_commerce
from commerce.seed import seed_database
from platform_app.app import create_app
from platform_app.config import Settings


SECRET = "runtime-only-platform-secret-94831"


@pytest.fixture
def integrated(tmp_path):
    seed_database(tmp_path / "commerce.db", sku_count=9, days=120, data_dir=tmp_path,
                  as_of=datetime.now(timezone.utc).date())
    commerce = create_commerce(tmp_path / "commerce.db")
    settings = Settings(data_dir=tmp_path, commerce_url="http://commerce")
    transport = httpx.ASGITransport(app=commerce)
    platform = create_app(settings, commerce_transport=transport)
    with TestClient(commerce) as commerce_client, TestClient(platform) as client:
        yield client, platform, commerce_client, settings, transport, tmp_path


def complete_preview(client, payload=None):
    created = client.post("/api/runs", json=payload or {"iterations": 100, "seed": 51})
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] in {"completed", "failed", "interrupted"}:
            assert run["status"] == "completed", run
            return run
        time.sleep(.02)
    pytest.fail(f"Preview {run_id} did not reach a terminal state within 15 seconds")


def test_health_summary_catalog_search_and_pagination_use_http_adapter(integrated):
    client, _, commerce, _, _, _ = integrated
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["commerce"]["status"] == "ok"
    assert health["mode"] == "supervised" and health["loop"]["running"] is False
    assert health["capabilities"] == {
        "quantitative_preview": True, "grounded_recommendations": False,
        "price_execution": False, "continuous_loop": False,
    }
    summary = client.get("/api/catalog/summary").json()
    assert summary["sku_count"] == 9
    assert sum(category["sku_count"] for category in summary["categories"]) == 9
    assert summary["inventory_units"] > 0
    first = client.get("/api/catalog", params={"limit": 2}).json()
    second = client.get("/api/catalog", params={"limit": 2, "offset": 2}).json()
    assert first["total"] == second["total"] == 9
    assert not {item["sku"] for item in first["items"]} & {item["sku"] for item in second["items"]}
    needle = first["items"][0]["sku"].lower()
    found = client.get("/api/catalog", params={"q": needle}).json()
    assert [item["sku"] for item in found["items"]] == [needle.upper()]
    beverages = client.get("/api/catalog", params={"category": "Beverages", "q": "item", "limit": 2, "offset": 1}).json()
    assert beverages["total"] == 3 and len(beverages["items"]) == 2
    assert all(item["category"] == "Beverages" for item in beverages["items"])
    assert first["items"] == commerce.get("/catalog", params={"limit": 2}).json()["items"]


def test_preview_is_nonexecutable_and_persists_across_restart(integrated):
    client, _, commerce, settings, transport, _ = integrated
    before = commerce.get("/prices", params={"limit": 5000}).json()["items"]
    run = complete_preview(client, {"category": "Beverages", "iterations": 100, "seed": 51})
    result = run["result"]
    assert result["kind"] == "quantitative_preview" and result["executable"] is False
    assert result["quality"]["blocked"] is False
    assert len(result["recommendations"]) == 3
    for item in result["recommendations"]:
        assert item["executable"] is False
        assert item["compliance_status"] == "not_validated"
        assert item["forecast"]["revenue"]["lower"] <= item["forecast"]["revenue"]["upper"]
    assert commerce.get("/prices", params={"limit": 5000}).json()["items"] == before
    assert commerce.get("/price-history").json()["total"] == 0
    assert run["id"] in {item["id"] for item in client.get("/api/runs").json()["items"]}
    with TestClient(create_app(Settings(data_dir=settings.data_dir, commerce_url="http://commerce"),
                               commerce_transport=transport)) as restarted:
        assert restarted.get(f"/api/runs/{run['id']}").json() == run
        assert restarted.get("/api/health").json()["mode"] == "supervised"


def test_scenario_matches_preview_engine_and_has_no_price_side_effect(integrated):
    client, _, commerce, _, _, _ = integrated
    run = complete_preview(client, {"sku_ids": ["SKU-00001"], "iterations": 100, "seed": 51,
                                    "horizon_days": 14})
    modeled = run["result"]["recommendations"][0]
    payload = {"sku": modeled["sku"], "candidate_price": modeled["proposed_price"],
               "iterations": 100, "seed": 51, "horizon_days": 14}
    response = client.post("/api/scenarios/simulate", json=payload)
    assert response.status_code == 200, response.text
    scenario = response.json()
    assert scenario["kind"] == "quantitative_preview" and scenario["executable"] is False
    assert scenario["forecast"] == modeled["forecast"]
    assert scenario["configuration"]["engine_version"] == run["result"]["configuration"]["engine_version"]
    assert client.post("/api/scenarios/simulate", json=payload).json() == scenario
    assert commerce.get("/price-history").json()["total"] == 0


def test_missing_run_and_sku_are_explicit(integrated):
    client, *_ = integrated
    assert client.get("/api/runs/does-not-exist").status_code == 404
    assert client.post("/api/scenarios/simulate", json={
        "sku": "missing-sku", "candidate_price": "10.00", "iterations": 100,
    }).status_code == 404


@pytest.mark.parametrize("endpoint,payload", [
    ("/api/runs", {"iterations": 100, "customer_id": "consumer-123"}),
    ("/api/scenarios/simulate", {"sku": "SKU-00001", "candidate_price": "10.00", "email": "consumer@example.test"}),
])
def test_consumer_fields_are_rejected_before_processing(integrated, endpoint, payload):
    client, *_ = integrated
    response = client.post(endpoint, json=payload)
    assert response.status_code == 422
    assert "consumer-123" not in response.text and "consumer@example.test" not in response.text
    assert not client.get("/api/runs").json()["items"]


def test_unavailable_commerce_degrades_health_and_refuses_runs(tmp_path):
    def unavailable(_request):
        raise httpx.ConnectError("simulated connection refusal")

    with TestClient(create_app(Settings(data_dir=tmp_path, commerce_url="http://commerce"),
                               commerce_transport=httpx.MockTransport(unavailable))) as client:
        assert client.get("/api/health").json()["status"] == "degraded"
        response = client.post("/api/runs", json={"iterations": 100})
        assert response.status_code == 503 and "Commerce" in response.text
        assert not client.get("/api/runs").json()["items"]


def test_empty_commerce_refuses_runs_without_silent_seeding(tmp_path):
    commerce = create_commerce(tmp_path / "commerce.db")
    with TestClient(commerce), TestClient(create_app(
        Settings(data_dir=tmp_path, commerce_url="http://commerce"),
        commerce_transport=httpx.ASGITransport(app=commerce),
    )) as client:
        assert client.get("/api/health").json()["capabilities"]["quantitative_preview"] is False
        assert client.post("/api/runs", json={"iterations": 100}).status_code == 503
        assert not client.get("/api/runs").json()["items"]


def test_gateway_secret_is_memory_only_never_returned_or_echoed(integrated):
    client, _, _, _, transport, directory = integrated
    updated = client.patch("/api/settings", json={
        "gateway_url": "https://gateway.example.test/v1", "api_key": SECRET,
    })
    assert updated.status_code == 200
    assert updated.json()["key_configured"] is True
    assert SECRET not in updated.text and SECRET not in client.get("/api/settings").text
    assert SECRET not in client.get("/api/audit").text
    for invalid in ({"api_key": {"credential": SECRET}}, {"gateway_port": SECRET},
                    {"gateway_url": f"https://user:{SECRET}@gateway.example.test"}):
        response = client.patch("/api/settings", json=invalid)
        assert response.status_code == 422
        assert SECRET not in response.text and '"input"' not in response.text
    for file in directory.rglob("*"):
        if file.is_file():
            assert SECRET.encode() not in file.read_bytes(), file
    with TestClient(create_app(Settings(data_dir=directory, commerce_url="http://commerce"),
                               commerce_transport=transport)) as restarted:
        assert restarted.get("/api/settings").json()["key_configured"] is False


def test_tls_bypass_requires_explicit_environment_permission(integrated, tmp_path):
    client, *_ = integrated
    response = client.patch("/api/settings", json={"verify_tls": False})
    assert response.status_code == 422
    assert client.get("/api/settings").json()["verify_tls"] is True
    with TestClient(create_app(Settings(data_dir=tmp_path / "allowed", allow_insecure_tls=True))) as allowed:
        with pytest.warns(UserWarning, match="TLS verification disabled"):
            response = allowed.patch("/api/settings", json={"verify_tls": False})
        assert response.status_code == 200 and response.json()["verify_tls"] is False
        assert response.json()["allow_insecure_tls"] is True


def test_audit_is_persisted_and_append_only(integrated):
    client, platform, *_ = integrated
    client.patch("/api/settings", json={"gateway_port": 4443})
    audit = client.get("/api/audit").json()["items"]
    assert audit and audit[0]["action"] == "settings_changed"
    store = platform.state.store
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store.connection() as connection:
            connection.execute("UPDATE audit SET actor='edited'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store.connection() as connection:
            connection.execute("DELETE FROM audit")
    assert client.get("/api/audit").json()["items"] == audit
