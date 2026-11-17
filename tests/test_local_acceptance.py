"""Portable process seams for the native runner; tests never start local services."""

from datetime import date
import json
from pathlib import Path
import subprocess
import socket
from types import SimpleNamespace

import pytest

from scripts import grounding_smoke, local_acceptance as acceptance, operations_smoke, smoke


def test_port_probe_distinguishes_free_loopback_port_from_real_listener(monkeypatch):
    with socket.socket() as listener, socket.socket() as available:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        occupied = listener.getsockname()[1]
        available.bind(("127.0.0.1", 0))
        free = available.getsockname()[1]
        available.close()
        monkeypatch.setattr(acceptance, "PORTS", (free, occupied))
        assert acceptance.port_states() == {str(free): True, str(occupied): False}


class Child:
    def __init__(self, number, events):
        self.number, self.events, self.code = number, events, None

    def poll(self):
        return self.code

    def terminate(self):
        self.events.append(self.number)
        self.code = 0

    def wait(self, timeout):
        return self.code


def args(tmp_path):
    return SimpleNamespace(model_cache=tmp_path / "models", seed=42, as_of=date(2026, 11, 14), timeout_seconds=30)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    children, stops, commands, readiness = [], [], [], []
    monkeypatch.setattr(acceptance, "source_digest", lambda: {"sha256": "fixed", "python_files": 0})
    monkeypatch.setattr(acceptance.platform, "platform", lambda: "explicit-native-process-seam")
    monkeypatch.setattr(acceptance, "port_states", lambda: {str(port): True for port in acceptance.PORTS})
    monkeypatch.setattr(acceptance, "node_runtime", lambda: (Path("node.exe"), Path("npm-cli.js"), "v24.4.1"))

    def popen(command, **options):
        child = Child(len(children), stops)
        children.append(child)
        commands.append((command, options))
        return child

    def ready(url, process):
        readiness.append((url, process.number))
        return {"status": "ok", "seeded": True}

    def command(command, environment, timeout):
        commands.append((command, {"env": environment, "timeout": timeout}))
        if "--output" in command:
            Path(command[command.index("--output") + 1]).write_text(json.dumps({"status": "passed"}))

    monkeypatch.setattr(acceptance.subprocess, "Popen", popen)
    monkeypatch.setattr(acceptance, "wait_ready", ready)
    monkeypatch.setattr(acceptance, "run_command", command)
    monkeypatch.setattr(acceptance, "safety_snapshot", lambda: {"prices": [{"sku": "fixture", "price_version": 1}], "price_count": 500, "history_total": 0})
    return SimpleNamespace(args=args(tmp_path), children=children, stops=stops, commands=commands, readiness=readiness)


def test_child_environment_strips_unrelated_provider_credentials_and_preserves_explicit_local_cache(tmp_path, monkeypatch):
    for key in ("GATEWAY_API_KEY", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "LANGFUSE_SECRET_KEY",
                "LANGSMITH_API_KEY", "HTTP_PROXY", "CUSTOM_PROVIDER_SECRET", "SSL_CERT_FILE"):
        monkeypatch.setenv(key, "must-not-reach-children")
    environment = acceptance.child_environment(tmp_path, tmp_path / "prepared-model")
    assert "must-not-reach-children" not in environment.values()
    assert environment["PRICING_STARTUP_MODE"] == "preview"
    assert environment["RAG_EMBEDDING_PROVIDER"] == "local"
    assert environment["RAG_MODEL_CACHE_DIR"] == str(tmp_path / "prepared-model")
    assert environment["COMMERCE_DB_PATH"] == str(tmp_path / "runtime/commerce.db")
    assert environment["HF_HUB_OFFLINE"] == "1"


def test_existing_listener_prevents_all_process_starts_and_is_never_terminated(isolated, monkeypatch):
    monkeypatch.setattr(acceptance, "port_states", lambda: {"8001": False, "8000": True, "5173": True})
    report = acceptance.run(isolated.args)
    assert report["status"] == "failed" and report["failure"] == "ports_unavailable_no_service_started"
    assert report["failed_stage"] == "port_preflight"
    assert not isolated.children and not isolated.commands and not isolated.stops
    assert report["temporary_storage_removed"]


def test_partial_startup_failure_stops_only_already_owned_children_in_reverse_order(isolated, monkeypatch):
    def ready(_url, process):
        if process.number == 1:
            raise acceptance.AcceptanceError("service_readiness_timeout")
        return {"status": "ok", "seeded": True}
    monkeypatch.setattr(acceptance, "wait_ready", ready)
    report = acceptance.run(isolated.args)
    assert report["status"] == "failed" and report["failed_stage"] == "startup"
    assert report["failure"] == "service_readiness_timeout"
    assert len(isolated.children) == 2 and isolated.stops == [1, 0]
    assert report["services_stopped"] and report["temporary_storage_removed"]


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired("isolated smoke", 30), KeyboardInterrupt(), RuntimeError("must-not-be-reported")])
def test_smoke_timeout_interrupt_and_unexpected_error_still_cleanup_owned_services(isolated, monkeypatch, failure):
    original = acceptance.run_command
    def command(command, environment, timeout):
        if "scripts.smoke" in command:
            raise failure
        return original(command, environment, timeout)
    monkeypatch.setattr(acceptance, "run_command", command)
    report = acceptance.run(isolated.args)
    assert report["status"] == "failed" and report["failed_stage"] == "smoke"
    assert isolated.stops == [2, 1, 0] and report["services_stopped"]
    assert report["temporary_storage_removed"]
    assert "must-not-be-reported" not in json.dumps(report)


def test_price_or_version_change_fails_acceptance_even_when_smoke_reports_pass(isolated, monkeypatch):
    count = 0
    def snapshot():
        nonlocal count
        count += 1
        return {"prices": [{"sku": "fixture", "price_version": count}], "price_count": 500, "history_total": count - 1}
    monkeypatch.setattr(acceptance, "safety_snapshot", snapshot)
    report = acceptance.run(isolated.args)
    assert report["status"] == "failed" and report["failure"] == "unexpected_commerce_change"
    assert report["actual_price_writes"] == 1 and not report["prices_and_versions_unchanged"]
    assert isolated.stops == [2, 1, 0]


def test_success_keeps_native_host_scope_and_does_not_claim_browser_gateway_or_other_os(isolated, monkeypatch):
    monkeypatch.setattr(acceptance.platform, "system", lambda: "Windows")
    monkeypatch.setattr(acceptance.platform, "platform", lambda: "Windows-simulated-seam")
    report = acceptance.run(isolated.args)
    assert report["status"] == "passed" and report["host_os"] == "Windows"
    assert set(report["checks"]) == {"preflight", "startup", *acceptance.SMOKES}
    assert report["prices_and_versions_unchanged"] and report["actual_price_writes"] == 0
    assert report["services_stopped"] and all(report["ports_free_after"].values())
    assert report["temporary_storage_removed"] and isolated.stops == [2, 1, 0]
    assert report["limits"]["browser_visual_qa"] == report["limits"]["gateway_generation"] == "not_run"
    assert report["limits"]["native_startup_sh_bat_wrapper"] == "not_run"
    assert report["limits"]["full_release_acceptance"] is False
    assert [number for _url, number in isolated.readiness] == [0, 1, 2]
    assert any("vite.js" in str(command) for command, _options in isolated.commands)


def test_cleanup_continues_after_one_owned_process_errors(isolated, monkeypatch):
    called = []
    def terminate(processes):
        [process] = processes
        called.append(process.number)
        if process.number == 1:
            raise OSError("fixture failure")
        process.terminate()
    children = [Child(number, []) for number in range(3)]
    monkeypatch.setattr(acceptance, "terminate_children", terminate)
    assert acceptance.stop_services(children) is False
    assert called == [2, 1, 0]


@pytest.mark.parametrize("module", [smoke, operations_smoke, grounding_smoke])
def test_smoke_commands_accept_isolated_output_and_avoid_ambient_proxy(module, tmp_path, monkeypatch):
    observed = {}
    class StopBeforeNetwork:
        def __init__(self, **options):
            observed.update(options)
        def __enter__(self):
            raise RuntimeError("explicit test seam")
        def __exit__(self, *_args):
            pass
    monkeypatch.setattr(module.httpx, "Client", StopBeforeNetwork)
    with pytest.raises(RuntimeError, match="explicit test seam"):
        module.main(["--output", str(tmp_path / "isolated.json"), "--base-url", "http://127.0.0.1:5173"])
    assert observed["trust_env"] is False and observed["base_url"] == "http://127.0.0.1:5173"
