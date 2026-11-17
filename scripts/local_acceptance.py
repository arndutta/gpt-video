"""Native local service acceptance with fresh temporary data, real retrieval and no price writes.

Run this on each target host. It does not establish browser, gateway, business KPI,
batch-wrapper or another operating system's acceptance from the current host's result.
"""

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time

import httpx

from scripts.acceptance_demo import fixture_environment, source_digest
from scripts.launch import terminate_children
from scripts.preflight import ROOT
from scripts.runtime import node_runtime

PORTS = (8001, 8000, 5173)
SMOKES = ("smoke", "operations_smoke", "grounding_smoke")


class AcceptanceError(RuntimeError):
    """A static failure code; child output and configuration never enter reports."""


def child_environment(directory, model_cache):
    # Reuse the fixture scrubber, then allow only native process/runtime necessities.
    inherited = fixture_environment(directory)
    allowed = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT",
               "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
               "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "NODE_BINARY"}
    environment = {name: value for name, value in inherited.items() if name.upper() in allowed}
    environment.update({"DATA_DIR": str(directory / "runtime"), "PRICING_STARTUP_MODE": "preview",
                        "COMMERCE_DB_PATH": str(directory / "runtime/commerce.db"),
                        "COMMERCE_URL": "http://127.0.0.1:8001", "RAG_EMBEDDING_PROVIDER": "local",
                        "RAG_MODEL_CACHE_DIR": str(model_cache), "HF_HUB_OFFLINE": "1",
                        "TRANSFORMERS_OFFLINE": "1", "DO_NOT_TRACK": "1"})
    return environment


def port_states():
    result = {}
    for port in PORTS:
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", port))
            # Windows SO_REUSEADDR can share an occupied address. Reject a listener too.
            try:
                # Winsock can take about a second to reject a closed loopback
                # port. A 200ms timeout misclassified every free CI port as busy.
                with socket.create_connection(("127.0.0.1", port), timeout=2):
                    result[str(port)] = False
            except ConnectionRefusedError:
                result[str(port)] = True
            except OSError:
                result[str(port)] = False
        except OSError:
            result[str(port)] = False
    return result


def run_command(command, environment, timeout):
    completed = subprocess.run(command, cwd=ROOT, env=environment, timeout=timeout,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if completed.returncode:
        raise AcceptanceError("child_check_failed")


def wait_ready(url, process, timeout=30):
    # Use a direct loopback client rather than inherited proxy configuration.
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=1, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AcceptanceError("service_exited_before_ready")
            try:
                response = client.get(url)
                if response.status_code == 200:
                    return response.json() if "json" in response.headers.get("content-type", "") else {}
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(.2)
    raise AcceptanceError("service_readiness_timeout")


def start_services(environment, processes):
    node, _, _ = node_runtime()
    environment = {**environment, "PATH": str(node.parent) + os.pathsep + environment.get("PATH", "")}
    services = [
        ([sys.executable, "-m", "uvicorn", "commerce.app:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"], ROOT, "http://127.0.0.1:8001/health"),
        ([sys.executable, "-m", "uvicorn", "platform_app.app:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"], ROOT, "http://127.0.0.1:8000/api/health"),
        ([str(node), str(ROOT / "web/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], ROOT / "web", "http://127.0.0.1:5173"),
    ]
    for command, directory, url in services:
        process = subprocess.Popen(command, cwd=directory, env=environment,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(process)
        health = wait_ready(url, process)
        if health.get("status", "ok") != "ok" or (health.get("service") == "commerce" and not health.get("seeded")):
            raise AcceptanceError("service_readiness_failed")


def safety_snapshot():
    with httpx.Client(timeout=10, trust_env=False) as client:
        def read(url):
            response = client.get(url)
            response.raise_for_status()
            return response.json()
        control = read("http://127.0.0.1:8000/api/control")
        settings = read("http://127.0.0.1:8000/api/settings")
        if control["mode"] != "supervised" or control["loop"]["running"] or settings["key_configured"]:
            raise AcceptanceError("unsafe_fixture_posture")
        prices = read("http://127.0.0.1:8001/prices?limit=5000")
        history = read("http://127.0.0.1:8001/price-history?limit=5000")
        return {"prices": prices["items"], "price_count": prices["total"], "history_total": history["total"]}


def stop_services(processes):
    errors = False
    # Continue cleanup even when one owned child fails to stop or reap normally.
    for process in reversed(processes):
        try:
            terminate_children([process])
        except (OSError, subprocess.SubprocessError):
            errors = True
    return not errors and all(process.poll() is not None for process in processes)


@contextmanager
def termination_handlers():
    signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)
    previous = {number: signal.getsignal(number) for number in signals}

    def stop(_number, _frame):
        for number in signals:
            signal.signal(number, signal.SIG_IGN)
        raise KeyboardInterrupt

    for number in signals:
        signal.signal(number, stop)
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run(args):
    started, source_before = time.perf_counter(), source_digest()
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "status": "failed",
              "host_os": platform.system(), "platform": platform.platform(), "python": platform.python_version(),
              "scope": "Native three-service startup, HTTP preview/operations, real local upload/retrieval and owned shutdown",
              "fixture": {"skus": 500, "history_days": 180, "seed": args.seed, "as_of": args.as_of.isoformat()},
              "checks": {}, "failure": None, "failed_stage": None, "prices_and_versions_unchanged": False,
              "actual_price_writes": None, "services_stopped": True, "temporary_storage_removed": False,
              "limits": {"browser_visual_qa": "not_run", "gateway_generation": "not_run",
                         "business_effectiveness": "not_measured", "native_startup_sh_bat_wrapper": "not_run",
                         "other_operating_systems": "not_run", "full_release_acceptance": False}}
    processes, stage = [], "port_preflight"
    with tempfile.TemporaryDirectory(prefix="pricing-native-acceptance-", ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        environment = child_environment(directory, args.model_cache.resolve())
        try:
            report["ports_free_before"] = port_states()
            if not all(report["ports_free_before"].values()):
                raise AcceptanceError("ports_unavailable_no_service_started")
            stage = "preflight"
            run_command([sys.executable, "-m", "scripts.preflight", "--mode", "preview", "--require-embeddings"], environment, args.timeout_seconds)
            report["checks"][stage] = {"status": "passed", "real_local_embeddings": True}
            stage = "seed"
            run_command([sys.executable, "-m", "commerce.seed", "--sku-count", "500", "--days", "180",
                         "--seed", str(args.seed), "--as-of", args.as_of.isoformat(), "--category", "Beverages",
                         "--data-dir", environment["DATA_DIR"]], environment, args.timeout_seconds)
            stage = "startup"
            start_services(environment, processes)
            report["checks"][stage] = {"status": "passed", "direct_children": len(processes)}
            stage = "initial_safety_snapshot"
            before = safety_snapshot()
            if before["price_count"] != 500 or before["history_total"] != 0:
                raise AcceptanceError("fresh_fixture_mismatch")
            for name in SMOKES:
                stage, output = name, directory / (name + ".json")
                check_started = time.perf_counter()
                run_command([sys.executable, "-m", "scripts." + name, "--output", str(output)], environment, args.timeout_seconds)
                evidence = json.loads(output.read_text(encoding="utf-8"))
                if evidence.get("status") != "passed":
                    raise AcceptanceError("missing_passed_check_evidence")
                report["checks"][name] = {"seconds": round(time.perf_counter() - check_started, 3), **evidence}
            stage = "final_safety_snapshot"
            after = safety_snapshot()
            report["prices_and_versions_unchanged"] = before["prices"] == after["prices"]
            report["actual_price_writes"] = after["history_total"]
            if not report["prices_and_versions_unchanged"] or after["history_total"] != 0:
                raise AcceptanceError("unexpected_commerce_change")
            report["status"] = "passed"
        except KeyboardInterrupt:
            report["failure"], report["failed_stage"] = "interrupted", stage
        except Exception as error:
            report["failure"] = str(error) if isinstance(error, AcceptanceError) else "check_timeout" if isinstance(error, subprocess.TimeoutExpired) else "check_failed"
            report["failed_stage"] = stage
        finally:
            report["services_stopped"] = stop_services(processes)
            report["ports_free_after"] = port_states()
            if not report["services_stopped"] or (processes and not all(report["ports_free_after"].values())):
                report["status"], report["failure"] = "failed", "owned_service_cleanup_failed"
    report["temporary_storage_removed"] = not directory.exists()
    if not report["temporary_storage_removed"]:
        report["status"], report["failure"] = "failed", "temporary_storage_cleanup_failed"
    report["source"] = source_digest()
    report["source_changed_during_run"] = source_before["sha256"] != report["source"]["sha256"]
    if report["source_changed_during_run"]:
        report["status"], report["failure"] = "failed", "source_changed_during_run"
    report["seconds"] = round(time.perf_counter() - started, 3)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/local_acceptance_result.json")
    parser.add_argument("--model-cache", type=Path, default=ROOT / "data/models")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Bound each preflight, seed and smoke subprocess.")
    args = parser.parse_args(argv)
    if not 30 <= args.timeout_seconds <= 600 or not 0 <= args.seed <= 2**32 - 1:
        parser.error("Use timeout 30–600 seconds and a seed in 0–4294967295.")
    with termination_handlers():
        report = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "host_os", "seconds", "failure", "failed_stage",
                                                 "services_stopped", "prices_and_versions_unchanged", "actual_price_writes")}))
    return 0 if report["status"] == "passed" else 130 if report["failure"] == "interrupted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
