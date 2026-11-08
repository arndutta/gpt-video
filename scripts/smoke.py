"""Check the running three-service preview without applying any prices."""

import json
from pathlib import Path
import time

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:5173", timeout=30) as client:
        response = client.get("/")
        response.raise_for_status()
        ui_status = response.status_code
        assert '<div id="root">' in response.text, "UI entry point is missing"
        health = client.get("/api/health")
        health.raise_for_status()
        assert health.json()["capabilities"]["quantitative_preview"]
        before = client.get("/api/catalog", params={"limit": 500}).json()
        started = time.perf_counter()
        created = client.post("/api/runs", json={"iterations": 1000, "seed": 42})
        created.raise_for_status()
        run_id = created.json()["id"]
        # This request runs while the numerical preview is active.
        ping_started = time.perf_counter()
        client.get("/api/health").raise_for_status()
        ping_ms = (time.perf_counter() - ping_started) * 1000
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = client.get(f"/api/runs/{run_id}")
            response.raise_for_status()
            run = response.json()
            if run["status"] in {"completed", "failed", "interrupted"}:
                break
            time.sleep(.2)
        assert run["status"] == "completed", run.get("error", "Preview timed out")
        elapsed = time.perf_counter() - started
        report = run["result"]
        assert report["executable"] is False
        assert len(report["recommendations"]) > 0
        candidate = report["recommendations"][0]
        scenario = client.post("/api/scenarios/simulate", json={
            "sku": candidate["sku"], "candidate_price": candidate["proposed_price"],
            "iterations": 1000, "seed": 42,
        })
        scenario.raise_for_status()
        assert scenario.json()["forecast"] == candidate["forecast"], "Scenario/preview engine mismatch"
        after = client.get("/api/catalog", params={"limit": 500}).json()
        assert before["items"] == after["items"], "Analysis changed the Commerce catalog"
        evidence = {"status": "passed", "sku_count": len(report["recommendations"]),
                    "source_as_of": report.get("source_as_of"), "iterations": 1000, "seed": 42,
                    "preview_seconds": round(elapsed, 3), "concurrent_health_ms": round(ping_ms, 2),
                    "scenario_matches_preview": True, "prices_unchanged": True,
                    "ui_http_status": ui_status,
                    "browser_visual_qa": "unverified"}
        Path("data/smoke_result.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
