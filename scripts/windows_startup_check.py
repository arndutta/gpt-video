"""Exercise startup.bat on a native Windows host with temporary synthetic storage.

No model gateway, browser automation, or real business outcomes are used. The root
starts suspended, enters an owned Job Object, then resumes. Descendant ownership
survives wrapper exit; any forced job cleanup fails graceful-shutdown acceptance.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time

from scripts.acceptance_demo import source_digest
from scripts.local_acceptance import (
    AcceptanceError, PORTS, ROOT, SMOKES, child_environment, port_states,
    run_command, safety_snapshot, termination_handlers, wait_ready,
)
from scripts.runtime import node_runtime
from scripts.windows_job import OwnedJob


def command_shell(environment):
    return next((value for name, value in environment.items() if name.upper() == "COMSPEC"), "cmd.exe")


def stop_group(process, job):
    result = {"process_exited": process is None, "ctrl_break_sent": False,
              "forced_job_cleanup": False, "job_closed": job is None, "all_processes_exited": job is None}
    try:
        if process is not None and process.poll() is None:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            result["ctrl_break_sent"] = True
            process.wait(timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        if job is not None:
            try:
                result.update(job.close())
            except (OSError, subprocess.SubprocessError):
                result["forced_job_cleanup"] = True
        if process is not None:
            try:
                result["process_exited"] = process.poll() is not None
            except (OSError, subprocess.SubprocessError):
                result["process_exited"] = False
    return result


def run(args):
    started, source_before = time.perf_counter(), source_digest()
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "host_os": platform.system(),
              "platform": platform.platform(), "python": platform.python_version(), "status": "failed",
              "scope": "Native startup.bat, real local HTTP preview/upload and owned process-group shutdown",
              "failure": None, "failed_stage": None, "checks": {}, "actual_price_writes": None,
              "prices_and_versions_unchanged": False, "temporary_storage_removed": False,
              "limits": {"browser_visual_qa": "not_run", "gateway_generation": "not_run",
                         "business_effectiveness": "not_measured", "other_operating_systems": "not_run",
                         "full_release_acceptance": False}}
    if platform.system() != "Windows":
        report["failure"] = "native_windows_required"
        return report
    process, job, stage = None, None, "port_preflight"
    with tempfile.TemporaryDirectory(prefix="pricing-windows-startup-", ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        environment = child_environment(directory, args.model_cache.resolve())
        try:
            report["ports_free_before"] = port_states()
            if not all(report["ports_free_before"].values()):
                raise AcceptanceError("ports_unavailable_no_service_started")
            node, _, _ = node_runtime()
            environment["PATH"] = str(node.parent) + os.pathsep + environment.get("PATH", "")
            stage = "startup_bat"
            command = [command_shell(environment), "/d", "/c", "startup.bat",
                       "--mode", "preview", "--require-embeddings", "--seed"]
            job = OwnedJob()
            process = job.start(command, cwd=ROOT, environment=environment)
            for url in ("http://127.0.0.1:8001/health", "http://127.0.0.1:8000/api/health",
                        "http://127.0.0.1:5173"):
                health = wait_ready(url, process, timeout=45)
                if health.get("status", "ok") != "ok" or (health.get("service") == "commerce" and not health.get("seeded")):
                    raise AcceptanceError("service_readiness_failed")
            report["checks"][stage] = {"status": "passed", "wrapper": "startup.bat"}
            stage = "initial_safety_snapshot"
            before = safety_snapshot()
            if before["price_count"] != 500 or before["history_total"] != 0:
                raise AcceptanceError("fresh_fixture_mismatch")
            for name in SMOKES:
                stage, output = name, directory / (name + ".json")
                run_command([sys.executable, "-m", "scripts." + name, "--output", str(output)],
                            environment, args.timeout_seconds)
                evidence = json.loads(output.read_text(encoding="utf-8"))
                if evidence.get("status") != "passed":
                    raise AcceptanceError("missing_passed_check_evidence")
                report["checks"][name] = evidence
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
            report["shutdown"] = stop_group(process, job)
            report["ports_free_after"] = port_states()
            if process is not None and (not report["shutdown"]["process_exited"]
                                        or not report["shutdown"]["ctrl_break_sent"]
                                        or report["shutdown"]["forced_job_cleanup"]
                                        or not report["shutdown"]["job_closed"]
                                        or not report["shutdown"]["all_processes_exited"]
                                        or not all(report["ports_free_after"].values())):
                report["status"], report["failure"] = "failed", "owned_group_shutdown_failed"
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
    parser.add_argument("--model-cache", type=Path, default=ROOT / "data/models")
    parser.add_argument("--output", type=Path, default=ROOT / "data/windows_startup_result.json")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args(argv)
    if not 30 <= args.timeout_seconds <= 600:
        parser.error("Use timeout 30–600 seconds.")
    with termination_handlers():
        report = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "host_os", "failure", "failed_stage")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
