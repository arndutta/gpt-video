"""Portable Windows process seams; a simulated host is never native evidence."""

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from packaging.requirements import Requirement
import pytest
import yaml

from scripts import launch, windows_startup_check as check


def test_locked_uvloop_is_excluded_only_for_native_windows():
    root = Path(__file__).resolve().parents[1]
    [uvloop] = [Requirement(line) for line in (root / "requirements.lock").read_text().splitlines()
                if line.startswith("uvloop==")]
    assert str(uvloop.specifier) == "==0.23.0"
    assert not uvloop.marker.evaluate({"sys_platform": "win32"})
    assert uvloop.marker.evaluate({"sys_platform": "darwin"})
    assert uvloop.marker.evaluate({"sys_platform": "linux"})


def test_launcher_handles_windows_break_and_ignores_repeated_break_during_cleanup(monkeypatch, tmp_path):
    from platform_app.config import Settings
    registered, cleaned = {}, []
    sentinel = 9876
    monkeypatch.setattr(launch.signal, "SIGBREAK", sentinel, raising=False)
    monkeypatch.setattr(launch.signal, "signal", lambda number, handler: registered.__setitem__(number, handler))
    monkeypatch.setattr(launch.os, "chdir", lambda *_args: None)
    monkeypatch.setattr(launch, "check", lambda **_kwargs: (Settings(data_dir=tmp_path), []))
    monkeypatch.setattr(launch, "node_runtime", lambda: (Path("node.exe"), Path("npm-cli.js"), "v24.4.1"))
    child = SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(launch.subprocess, "Popen", lambda *_args, **_kwargs: child)
    monkeypatch.setattr(launch, "wait_for", lambda *_args: {})
    monkeypatch.setattr(launch.time, "sleep", lambda *_args: registered[sentinel](sentinel, None))
    def cleanup(processes):
        assert registered[sentinel] is launch.signal.SIG_IGN
        cleaned.extend(processes)
    monkeypatch.setattr(launch, "terminate_children", cleanup)
    assert launch.main(["--mode", "preview"]) == 0
    assert len(cleaned) == 3


class Child:
    pid = 12345

    def __init__(self, *, timeout=False):
        self.code, self.signals, self.timeout = None, [], timeout

    def poll(self):
        return self.code

    def send_signal(self, number):
        self.signals.append(number)

    def wait(self, timeout):
        if self.timeout:
            self.timeout = False
            raise subprocess.TimeoutExpired("owned fixture", timeout)
        self.code = 0
        return 0


class Job:
    def __init__(self, child):
        self.child, self.command, self.closed = child, None, False

    def start(self, command, **options):
        self.command, self.options = command, options
        return self.child

    def close(self):
        forced = self.child.poll() is None
        self.child.code, self.closed = 0, True
        return {"job_closed": True, "forced_job_cleanup": forced,
                "all_processes_exited": True, "active_at_close": 0}


@pytest.fixture
def windows_seams(monkeypatch, tmp_path):
    monkeypatch.setattr(check.platform, "system", lambda: "Windows")
    monkeypatch.setattr(check.platform, "platform", lambda: "simulated-windows-seam")
    monkeypatch.setattr(check.signal, "CTRL_BREAK_EVENT", 1, raising=False)
    monkeypatch.setattr(check.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr(check, "source_digest", lambda: {"sha256": "fixed", "python_files": 0})
    monkeypatch.setattr(check, "port_states", lambda: {str(port): True for port in check.PORTS})
    monkeypatch.setattr(check, "node_runtime", lambda: (Path("node.exe"), Path("npm-cli.js"), "v24.4.1"))
    monkeypatch.setattr(check, "wait_ready", lambda *_args, **_kwargs: {"status": "ok", "seeded": True})
    monkeypatch.setattr(check, "safety_snapshot", lambda: {"price_count": 500, "history_total": 0, "prices": [{"version": 1}]})
    def command(command, *_args):
        Path(command[command.index("--output") + 1]).write_text(json.dumps({"status": "passed"}))
    monkeypatch.setattr(check, "run_command", command)
    return SimpleNamespace(model_cache=tmp_path / "models", timeout_seconds=30)


def test_non_windows_host_cannot_claim_native_batch_acceptance(monkeypatch, tmp_path):
    monkeypatch.setattr(check.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(check.platform, "platform", lambda: "explicit-host-fixture")
    monkeypatch.setattr(check.subprocess, "Popen", lambda *_a, **_k: pytest.fail("No process may start."))
    report = check.run(SimpleNamespace(model_cache=tmp_path, timeout_seconds=30))
    assert report["status"] == "failed" and report["failure"] == "native_windows_required"
    assert report["host_os"] == "Darwin"


def test_batch_wrapper_receives_owned_job_and_graceful_break(windows_seams, monkeypatch):
    child = Child()
    job = Job(child)
    monkeypatch.setattr(check, "OwnedJob", lambda: job)
    report = check.run(windows_seams)
    assert report["status"] == "passed"
    assert job.command[1:] == ["/d", "/c", "startup.bat", "--mode", "preview", "--require-embeddings", "--seed"]
    assert child.signals == [1]
    assert report["shutdown"]["job_closed"] and not report["shutdown"]["forced_job_cleanup"]
    assert report["prices_and_versions_unchanged"] and report["actual_price_writes"] == 0
    assert report["temporary_storage_removed"] and report["limits"]["full_release_acceptance"] is False


def test_failed_batch_readiness_still_stops_the_owned_group(windows_seams, monkeypatch):
    child = Child()
    job = Job(child)
    monkeypatch.setattr(check, "OwnedJob", lambda: job)
    def fail(*_args, **_kwargs):
        raise check.AcceptanceError("service_readiness_timeout")
    monkeypatch.setattr(check, "wait_ready", fail)
    report = check.run(windows_seams)
    assert report["status"] == "failed" and report["failed_stage"] == "startup_bat"
    assert child.signals == [1] and report["shutdown"]["process_exited"]
    assert report["temporary_storage_removed"] and job.closed


def test_forced_job_cleanup_fails_graceful_acceptance(windows_seams, monkeypatch):
    child = Child(timeout=True)
    job = Job(child)
    monkeypatch.setattr(check, "OwnedJob", lambda: job)
    report = check.run(windows_seams)
    assert report["status"] == "failed" and report["failure"] == "owned_group_shutdown_failed"
    assert report["shutdown"]["forced_job_cleanup"] and job.closed


def test_exited_wrapper_cannot_claim_controlled_graceful_shutdown(windows_seams, monkeypatch):
    child = Child()
    child.code = 0
    monkeypatch.setattr(check, "OwnedJob", lambda: Job(child))
    report = check.run(windows_seams)
    assert report["status"] == "failed" and report["failure"] == "owned_group_shutdown_failed"
    assert not report["shutdown"]["ctrl_break_sent"]


def test_windows_workflow_limits_triggers_and_permissions_and_pins_official_actions():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load((root / ".github/workflows/windows-acceptance.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"workflow_dispatch", "push"}
    assert workflow["on"]["push"] == {"branches": ["codex/windows-acceptance"]}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["windows"]
    assert job["runs-on"] == "windows-2025" and job["timeout-minutes"] == "30"
    actions = [step["uses"] for step in job["steps"] if "uses" in step]
    assert len(actions) >= 4 and all(value.startswith("actions/") and len(value.split("@")[1]) == 40 for value in actions)
    assert job["steps"][0]["with"]["persist-credentials"] == "false"
    assert not any("secrets." in str(step) for step in job["steps"])
    assert all(len(step["run"].splitlines()) == 1 and ";" not in step["run"]
               for step in job["steps"] if "run" in step), "Each PowerShell step must expose its command's exit status."
