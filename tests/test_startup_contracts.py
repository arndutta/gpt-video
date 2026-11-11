"""Portable startup seams; Windows layout is simulated, not claimed as Windows execution."""

from pathlib import Path
import subprocess

import httpx
import pytest

from platform_app.config import Settings
from scripts import launch, preflight, runtime


def settings(directory):
    return Settings(data_dir=directory, gateway_url="https://gateway.test/v1", api_key="fixture-preflight-key",
                    model_router="router", model_narrator="narrator", model_analyst="analyst", model_strategist="strategist")


@pytest.mark.parametrize("version,supported", [("v20.18.1", False), ("v20.19.0", True),
    ("v21.7.0", False), ("v22.11.0", False), ("v22.12.0", True), ("v24.4.1", True)])
def test_supported_node_versions_and_windows_npm_layout(tmp_path, monkeypatch, version, supported):
    node = tmp_path / "node.exe"
    node.write_text("isolated executable layout fixture")
    npm = tmp_path / "node_modules/npm/bin/npm-cli.js"
    npm.parent.mkdir(parents=True)
    npm.write_text("isolated npm entrypoint fixture")
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *_args, **_kwargs: version)
    if supported:
        assert runtime.node_runtime([str(node)]) == (node, npm, version)
    else:
        with pytest.raises(RuntimeError, match="supported version"):
            runtime.node_runtime([str(node)])


def test_explicit_node_binary_takes_precedence_over_path(tmp_path, monkeypatch):
    node = tmp_path / "node"
    node.write_text("fixture")
    npm = tmp_path / "npm-cli.js"
    npm.write_text("fixture")
    (tmp_path / "npm").symlink_to(npm)
    monkeypatch.setenv("NODE_BINARY", str(node))
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: "/unrelated/node")
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda command, **_kwargs: "v24.4.1")
    assert runtime.node_runtime()[0] == node


@pytest.fixture
def ready_preflight(tmp_path, monkeypatch):
    config = settings(tmp_path)
    monkeypatch.setattr(preflight.sys, "prefix", "isolated-venv")
    monkeypatch.setattr(preflight.Settings, "from_environment", lambda: config)
    monkeypatch.setattr(preflight, "version", lambda _name: "fixture-installed")
    monkeypatch.setattr(preflight, "node_runtime", lambda: (Path("node"), Path("npm-cli.js"), "v24.4.1"))
    return config


def test_grounded_preflight_requires_both_alias_and_embedding_probes(ready_preflight, monkeypatch):
    calls = []
    async def gateway(config):
        assert config is ready_preflight
        calls.append("gateway")
    def embedding(config):
        calls.append("embedding")
        return {"provider": "local", "dimensions": 384}
    monkeypatch.setattr(preflight, "gateway_probe", gateway)
    monkeypatch.setattr(preflight, "embedding_probe", embedding)
    _, messages = preflight.check(mode="grounded", skip_ports=True)
    assert calls == ["gateway", "embedding"] and "grounded" in " ".join(messages)
    calls.clear()
    preflight.check(require_gateway=True, skip_ports=True)
    assert calls == ["gateway", "embedding"]
    calls.clear()
    _, messages = preflight.check(mode="preview", skip_ports=True)
    assert not calls and "Gateway probe skipped" in " ".join(messages)


def test_missing_dependency_names_remedy_without_starting_a_probe(ready_preflight, monkeypatch):
    def missing(name):
        if name == "langgraph":
            raise preflight.PackageNotFoundError(name)
        return "fixture-installed"
    monkeypatch.setattr(preflight, "version", missing)
    with pytest.raises(RuntimeError, match="Missing langgraph.*requirements.lock"):
        preflight.check(mode="grounded", skip_ports=True)


async def test_gateway_alias_probe_uses_central_bounded_safe_contract(tmp_path):
    config = settings(tmp_path)
    requests = []
    def responder(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"id": role} for role in ("router", "narrator", "analyst", "strategist")]})
    report = await preflight.gateway_probe(config, httpx.MockTransport(responder))
    assert report["verified"] and not report["structured_output_verified"]
    assert requests[0].url.path == "/v1/models" and requests[0].headers["authorization"].startswith("Bearer ")
    assert config.api_key.get_secret_value() not in str(report)
    malformed = httpx.MockTransport(lambda _request: httpx.Response(200, json=[]))
    with pytest.raises(RuntimeError, match="Gateway model verification failed"):
        await preflight.gateway_probe(config, malformed)


class Child:
    def __init__(self, label, events):
        self.label, self.events, self.code = label, events, None
    def poll(self):
        return self.code
    def terminate(self):
        self.events.append(("terminate", self.label))
        self.code = 0
    def wait(self, timeout):
        self.events.append(("wait", self.label, timeout))
        return self.code


@pytest.mark.parametrize("platform_ready", [True, False])
def test_launcher_orders_health_before_next_service_and_owns_all_direct_children(tmp_path, monkeypatch, platform_ready):
    events, children, checks, environments = [], [], [], []
    monkeypatch.setattr(launch.os, "chdir", lambda _root: None)
    monkeypatch.setattr(launch.signal, "signal", lambda *_args: None)
    def check(**kwargs):
        checks.append(kwargs)
        return settings(tmp_path), ["Isolated startup seam"]
    monkeypatch.setattr(launch, "check", check)
    monkeypatch.setattr(launch, "node_runtime", lambda: (Path("node.exe"), Path("npm-cli.js"), "v24.4.1"))
    def spawn(command, cwd, env):
        child = Child(len(children), events)
        children.append(child)
        environments.append(env)
        events.append(("spawn", child.label, command))
        return child
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    def wait_for(url, process):
        events.append(("healthy", process.label))
        if process.label == 0:
            return {"service": "commerce", "seeded": True, "status": "ok"}
        return {"service": "pricing-platform", "status": "ok" if platform_ready else "degraded"}
    monkeypatch.setattr(launch, "wait_for", wait_for)
    def interrupted(_seconds):
        raise KeyboardInterrupt
    monkeypatch.setattr(launch.time, "sleep", interrupted)
    code = launch.main(["--mode", "grounded"])
    assert code == (0 if platform_ready else 1) and checks[0]["mode"] == "grounded"
    count = 3 if platform_ready else 2
    assert [event[:2] for event in events if event[0] in {"spawn", "healthy"}] == [
        pair for index in range(count) for pair in (("spawn", index), ("healthy", index))]
    assert [event[1] for event in events if event[0] == "terminate"] == list(reversed(range(count)))
    assert all(env["PRICING_STARTUP_MODE"] == "grounded" for env in environments)
    assert children[0].code == 0 and all(child.code is not None for child in children)
    if platform_ready:
        assert "vite.js" in str(events[4][2]) and "npm" not in events[4][2][0]


def test_shutdown_escalates_only_child_that_ignores_termination():
    events = []
    child = Child("stuck", events)
    child.terminate = lambda: events.append(("terminate", "stuck"))
    def wait(timeout):
        if child.code is None:
            raise subprocess.TimeoutExpired("fixture", timeout)
        return child.code
    child.wait = wait
    def kill():
        events.append(("kill", "stuck"))
        child.code = -9
    child.kill = kill
    launch.terminate_children([child])
    assert events == [("terminate", "stuck"), ("kill", "stuck")]
