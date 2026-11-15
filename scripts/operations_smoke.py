"""Exercise the running local controls and constrained scenarios without changing prices."""

import argparse
import json
from pathlib import Path
import time

import httpx


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, default=Path("data/operations_smoke_result.json"))
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as client:
        control = client.get("/api/control")
        control.raise_for_status()
        control = control.json()
        assert control["mode"] == "supervised" and not control["loop"]["running"], "Smoke requires explicit Supervised/off posture."
        before = client.get("/api/catalog", params={"limit": 500})
        before.raise_for_status()
        product = before.json()["items"][0]
        settings = client.get("/api/settings")
        settings.raise_for_status()
        monitor = client.get("/api/monitor")
        monitor.raise_for_status()
        assert "input_tokens" in monitor.json() and "cache" in monitor.json()
        for route in ("/api/recommendations", "/api/loop/history", "/api/feedback", "/api/scenarios/saved"):
            response = client.get(route)
            response.raise_for_status()
            assert isinstance(response.json()["items"], list)
        request = {"kind": "quantitative_preview", "sku_ids": [product["sku"]], "iterations": 100,
                   "seed": 17, "horizon_days": 7, "constraints": {"max_change_pct": 0.}}
        created = client.post("/api/runs", json=request)
        created.raise_for_status()
        run_id = created.json()["id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = client.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(.1)
        assert run["status"] == "completed", run.get("error")
        [item] = run["result"]["recommendations"]
        assert item["current_price"] == item["proposed_price"]
        result = client.post("/api/scenarios/batch", json={"items": [{"sku": product["sku"], "candidate_price": item["proposed_price"]}],
                                                          "iterations": 100, "seed": 17, "horizon_days": 7, "stress": "none"})
        result.raise_for_status()
        assert result.json()["items"][0]["forecast"] == item["forecast"]
        audit = client.get("/api/audit/export")
        audit.raise_for_status()
        assert isinstance(audit.json()["items"], list)
        card = client.get("http://127.0.0.1:8000/.well-known/agent-card.json")
        card.raise_for_status()
        assert card.json()["protocolVersion"] == "0.3.0"
        after = client.get("/api/catalog", params={"limit": 500})
        after.raise_for_status()
        assert before.json()["items"] == after.json()["items"]
        report = {"status": "passed", "mode": control["mode"], "loop_running": False,
                  "constrained_preview": True, "zero_change_cap_respected": True,
                  "shared_scenario_forecast": True, "prices_and_versions_unchanged": True,
                  "monitor_and_audit_available": True, "a2a_card_version": "0.3.0",
                  "live_gateway_verified": False, "browser_visual_qa": "separate verification"}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return report


if __name__ == "__main__":
    main()
