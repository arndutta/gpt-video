"""One-SKU real local graph probe in disposable storage; stops at human review.

No provider or embedding fixture is injected. An owned loopback forwarding bridge
adds native truncate=false/shift=false so oversized prompts fail instead of losing
facts. Only safe request-size, timing and token metadata survives the probe.
A longer explicitly selected deadline is a functional observation window; this
one-SKU probe never establishes the 500-SKU performance requirement.
"""

import argparse
import asyncio
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import sqlite3
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.local_gateway import LocalGateway, LocalGatewayError, ROOT, _sigterm_cleanup


def log_offsets(directory):
    return {(p.stat().st_dev, p.stat().st_ino): p.stat().st_size
            for p in directory.glob("server*.log")}


def native_log_result(directory, offsets):
    fragments = []
    complete = True
    for path in directory.glob("server*.log"):
        stat = path.stat()
        start = offsets.get((stat.st_dev, stat.st_ino), 0)
        with path.open("rb") as stream:
            stream.seek(start)
            content = stream.read(4_000_001)
        complete &= len(content) <= 4_000_000
        fragments.append(content[:4_000_000].decode(errors="replace"))
    content = "\n".join(fragments)
    return {"readable": bool(fragments), "scan_complete": complete,
            "truncation_marker": bool(re.search(r"truncating (?:input|native chat|prompt)|"
                                                 r"input length exceeds|prompt.*too long", content, re.I)),
            "runner_killed_marker": "signal: killed" in content}


@contextmanager
def guarded_native(ollama_port):
    """Forward actual native calls unchanged except disabling input/context loss."""
    # These native fields are verified in v0.40.16 api/types.go and server/routes.go.
    # Pin the diagnostic contract rather than assuming older servers reject unknown JSON.
    with urlopen(f"http://127.0.0.1:{ollama_port}/api/version", timeout=5) as response:
        version = json.load(response).get("version")
    if version != "0.40.16":
        raise LocalGatewayError("This no-truncation probe requires the verified Ollama 0.40.16 API contract.")
    observations, lock = [], threading.Lock()
    idle = threading.Event()
    idle.set()
    lifecycle = {"active_forwarders": 0, "server_thread_alive": True,
                 "forwarder_cleanup_timed_out": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            if self.path not in {"/api/tags", "/api/chat"}:
                self.send_error(404)
                return
            metadata, data = None, None
            if self.command == "POST":
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 2_000_000 or self.path != "/api/chat":
                    self.send_error(413)
                    return
                payload = json.loads(self.rfile.read(length))
                options = payload.get("options", {})
                if (options.get("num_ctx") != 4096 or options.get("num_batch") != 64
                        or options.get("num_predict") != 800 or not isinstance(payload.get("format"), dict)
                        or payload.get("stream") is not False):
                    self.send_error(422)
                    return
                payload.update(truncate=False, shift=False)
                data = json.dumps(payload).encode()
                metadata = {"request_bytes": len(data), "message_count": len(payload["messages"]),
                            "message_utf8_bytes": len(json.dumps(payload["messages"]).encode()),
                            "schema_utf8_bytes": len(json.dumps(payload["format"]).encode()),
                            "num_ctx": 4096, "num_batch": 64, "output_limit": 800,
                            "truncate": False, "shift": False}
            started = time.monotonic()
            request = Request(f"http://127.0.0.1:{ollama_port}" + self.path, data=data,
                              headers={"Content-Type": "application/json"}, method=self.command)
            with lock:
                lifecycle["active_forwarders"] += 1
                idle.clear()
                if metadata is not None:
                    metadata["status"] = "in_flight"
                    observations.append(metadata)
            try:
                try:
                    response = urlopen(request, timeout=125)
                except HTTPError as error:
                    response = error
                with response:
                    content = response.read(2_000_001)
                    if len(content) > 2_000_000:
                        raise ValueError("Native response exceeded the probe limit")
                    if metadata is not None:
                        result = json.loads(content)
                        metadata.update(status=response.status, seconds=round(time.monotonic() - started, 3),
                                        input_tokens=result.get("prompt_eval_count"),
                                        output_tokens=result.get("eval_count"), done_reason=result.get("done_reason"))
                    self.send_response(response.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
            except Exception as error:
                if metadata is not None:
                    if metadata.get("status") == "in_flight":
                        metadata["status"] = "forwarding_failed"
                    metadata.update(delivery_error_type=type(error).__name__,
                                    seconds=round(time.monotonic() - started, 3))
                try:
                    self.send_error(502, "Local native forwarding failed")
                except OSError:
                    pass  # The canceled caller may already have closed its socket.
            finally:
                with lock:
                    lifecycle["active_forwarders"] -= 1
                    if not lifecycle["active_forwarders"]:
                        idle.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="local-native-guard")
    thread.start()
    try:
        yield server.server_port, observations, lifecycle
    finally:
        server.shutdown()
        # HTTP cancellation cannot always recall an admitted native inference.
        # Let owned, already-sent requests settle within their 125s timeout; do
        # not claim cleanup merely because the listening socket has closed.
        lifecycle["forwarder_cleanup_timed_out"] = not idle.wait(timeout=130)
        server.server_close()
        thread.join(timeout=2)
        lifecycle["server_thread_alive"] = thread.is_alive()


async def graph_probe(gateway, directory, deadline):
    import httpx
    from commerce.app import create_app as create_commerce
    from commerce.seed import seed_database
    from platform_app.app import create_app
    from platform_app.config import RunRequest
    from platform_app.rag.models import Document
    from platform_app.workflow.nodes import digest

    commerce_dir, platform_dir = directory / "commerce", directory / "platform"
    platform_dir.mkdir()
    as_of = datetime.now(timezone.utc).date()
    await asyncio.to_thread(seed_database, commerce_dir / "commerce.db", sku_count=500, days=180,
                            seed=42, as_of=as_of, data_dir=commerce_dir, categories=("Beverages",))
    with closing(sqlite3.connect(commerce_dir / "market.db")) as source:
        with closing(sqlite3.connect(platform_dir / "market.db")) as target:
            source.backup(target)
    upstream = create_commerce(commerce_dir / "commerce.db")
    settings = gateway.settings(platform_dir).model_copy(update={
        "commerce_url": "http://local-graph-commerce", "startup_mode": "grounded"})
    await gateway.ready(settings)
    app = create_app(settings, commerce_transport=httpx.ASGITransport(app=upstream))
    failure = None
    started = time.monotonic()
    async with upstream.router.lifespan_context(upstream), app.router.lifespan_context(app):
        state = app.state
        before = (await state.commerce.all("/catalog"))["items"]
        history_before = (await state.commerce.all("/price-history"))["items"]
        job = await asyncio.to_thread(state.grounding.submit, Document(
            source_id="local-graph-policy", title="Public synthetic graph policy", collection="pricing_policy",
            version="v1", text=(ROOT / "examples/pricing-policy.md").read_text()), "pricing-policy.md")
        for _ in range(200):
            current = state.grounding.get_upload(job["id"])
            if current["status"] in {"ready", "failed", "interrupted"}:
                break
            await asyncio.sleep(.05)
        if current["status"] != "ready":
            raise LocalGatewayError("Real local grounding did not become ready; no graph generation started.")
        started = time.monotonic()
        run = state.workflow.start(RunRequest(kind="grounded", sku_ids=[before[0]["sku"]], iterations=1000))
        try:
            await asyncio.wait_for(asyncio.gather(*list(state.workflow.tasks)), timeout=deadline)
        except TimeoutError:
            failure = "graph_deadline"
        elapsed = time.monotonic() - started
        result = state.store.get_run(run["id"])
        snapshot = await state.workflow.graph.aget_state(state.workflow.config(run["id"]))
        items = state.governance.queue(run_id=run["id"])
        numeric = None
        async for checkpoint in state.workflow.graph.aget_state_history(state.workflow.config(run["id"])):
            if checkpoint.next == ("strategy_reasoning",):
                numeric = checkpoint.values.get("report")
                break
        keys = ("current_price", "proposed_price", "delta_pct", "confidence", "forecast", "baseline", "elasticity", "impact")
        integrity = bool(numeric and digest(numeric) == snapshot.values.get("numeric_hash") and len(items) == 1
                         and all(items[0].get(key) == numeric["recommendations"][0].get(key) for key in keys))
        after = (await state.commerce.all("/catalog"))["items"]
        history_after = (await state.commerce.all("/price-history"))["items"]
        unchanged = before == after and history_before == history_after
        model = state.llm.snapshot()
        report = {"status": "passed" if result["status"] == "awaiting_review" and snapshot.interrupts
                  and len(items) == 1 and integrity and unchanged and not failure else "failed",
                  "graph_status": result["status"], "last_stage": result["stage"],
                  "failure": failure or ("workflow_failed" if result["status"] == "failed" else None),
                  "detail": result.get("error"),
                  "seconds_to_human_review_or_failure": round(elapsed, 3), "graph_deadline_seconds": deadline,
                  "performance_scope": {"tested_skus": 1, "required_skus": 500,
                                        "required_seconds": 300, "acceptance": "not_measured"},
                  "fixture": {"seed": 42, "as_of": as_of.isoformat(), "catalog_skus": 500,
                              "scoped_skus": 1, "sales_days": 180, "iterations": 1000},
                  "transport": "Commerce ASGI HTTP adapter; real loopback LiteLLM and Ollama HTTP",
                  "model_provider_fixture": False, "embedding_fixture": False,
                  "mode_at_decision": state.governance.mode()["mode"], "human_interrupt_count": len(snapshot.interrupts),
                  "recommendations": len(items), "cited_recommendations": sum(bool(item.get("citations")) for item in items),
                  "numeric_artifact_unchanged": integrity, "commerce_prices_and_versions_unchanged": unchanged,
                  "actual_price_writes": len(history_after) - len(history_before), "usage": model,
                  "usage_snapshot_basis": "At graph settlement before application shutdown"}
    events = [json.loads(line) for line in (platform_dir / "telemetry.jsonl").read_text().splitlines()]
    report["stage_events"] = [{k: event[k] for k in ("agent", "status", "latency_ms") if k in event}
                              for event in events if event.get("event") == "agent_completed"]
    report["repair_events"] = sum(event.get("event") == "model_repair" for event in events)
    return report


def port_free(port):
    with socket.socket() as check:
        return check.connect_ex(("127.0.0.1", port)) != 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="phi3:mini")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--ollama-port", type=int, default=11434)
    parser.add_argument("--deadline-seconds", type=int, default=240,
                        help="Explicit functional observation window (30–600s); does not change the 500-SKU target.")
    parser.add_argument("--output", type=Path, default=ROOT / "data/local_graph_probe_result.json")
    args = parser.parse_args(argv)
    if not 30 <= args.deadline_seconds <= 600:
        parser.error("--deadline-seconds must be between 30 and 600")
    logs = Path.home() / ".ollama/logs"
    offsets = log_offsets(logs)
    guard_port, observations = None, []
    guard_state = {"active_forwarders": 0, "server_thread_alive": False,
                   "forwarder_cleanup_timed_out": False}
    try:
        with _sigterm_cleanup(), guarded_native(args.ollama_port) as (guard_port, observations, guard_state):
            gateway = LocalGateway(args.model, port=args.port, ollama_port=guard_port, batch_tokens=64)
            with gateway.running(), tempfile.TemporaryDirectory(prefix="pricing-local-graph-") as directory:
                report = asyncio.run(graph_probe(gateway, Path(directory), args.deadline_seconds))
    except LocalGatewayError as error:
        report = {"status": "failed", "failure": "local_gateway_unavailable", "detail": str(error)}
    except Exception as error:
        report = {"status": "failed", "failure": "probe_error", "error_type": type(error).__name__}
    native = native_log_result(logs, offsets)
    try:
        with urlopen(f"http://127.0.0.1:{args.ollama_port}/api/ps", timeout=5) as response:
            loaded = len(json.load(response).get("models", []))
    except Exception:
        loaded = None
    report.update(native_requests=observations, native_log=native,
                  context_loss_disabled=True, proxy_stopped=port_free(args.port),
                  native_guard_stopped=(guard_port is None or port_free(guard_port)) and not any(guard_state.values()),
                  native_guard_cleanup=guard_state, loaded_runner_count_after_probe=loaded,
                  native_server_version="0.40.16",
                  temporary_storage_removed=True, local_integration_only=True, corporate_tiers_certified=False)
    if (native["truncation_marker"] or native["runner_killed_marker"] or loaded != 0
            or not report["proxy_stopped"] or not report["native_guard_stopped"]):
        report["status"] = "failed"
    report["all_observed_token_budgets_fit"] = bool(observations) and all(
        item.get("status") == 200 and isinstance(item.get("input_tokens"), int)
        and item["input_tokens"] + item["output_limit"] <= item["num_ctx"] for item in observations)
    if not report["all_observed_token_budgets_fit"]:
        report["status"] = "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
