"""Local helper isolation, credential privacy, and owned child cleanup."""

import json
from pathlib import Path
import signal
import subprocess

import pytest

from scripts.local_gateway import LocalGateway, LocalGatewayError, child_environment, proxy_config
from scripts import local_gateway


def test_child_cannot_inherit_external_credentials_or_logging(monkeypatch):
    for name in ("OPENAI_API_KEY", "LANGFUSE_SECRET_KEY", "DATABASE_URL", "HTTP_PROXY",
                 "LITELLM_TELEMETRY_ENDPOINT", "LITELLM_LICENSE", "LANGCHAIN_TRACING_V2"):
        monkeypatch.setenv(name, "must-not-inherit")
    environment = child_environment("memory-only-key")
    assert "must-not-inherit" not in json.dumps(environment)
    assert environment["LITELLM_OFFLINE_MODE"] == "true"
    assert environment["LITELLM_TELEMETRY_DISABLED"] == "true"


def test_configuration_contains_no_key_and_only_one_local_backend(tmp_path):
    gateway = LocalGateway("installed:model")
    config = proxy_config(gateway.model, 11434)
    encoded = json.dumps(config)
    assert gateway._key not in encoded
    assert gateway._key not in gateway.settings(tmp_path).model_dump_json()
    assert gateway._key not in repr(gateway.settings(tmp_path))
    rows = config["model_list"]
    assert {row["litellm_params"]["model"] for row in rows} == {"ollama_chat/installed:model"}
    assert all(row["litellm_params"]["api_base"] == "http://127.0.0.1:11434" for row in rows)
    assert config["general_settings"]["master_key"] == "os.environ/LOCAL_GATEWAY_MASTER_KEY"


def test_explicit_smaller_batch_preserves_context_output_limit_and_local_routing(monkeypatch):
    gateway = LocalGateway("installed:model", batch_tokens=64)
    monkeypatch.setattr(gateway, "_preflight", lambda: None)
    observed = {}
    class Process:
        def poll(self):
            return 0
    def start(command, **_options):
        path = Path(command[command.index("--config") + 1])
        observed.update(json.loads(path.read_text()))
        return Process()
    monkeypatch.setattr(subprocess, "Popen", start)
    with gateway.running():
        pass
    for row in observed["model_list"]:
        params = row["litellm_params"]
        assert params["num_batch"] == 64
        assert params["num_ctx"] == 4096 and params["max_tokens"] == 800
        assert params["model"] == "ollama_chat/installed:model"
        assert params["api_base"] == "http://127.0.0.1:11434"
    assert proxy_config("installed:model", 11434)["model_list"][0]["litellm_params"]["num_batch"] == 512


@pytest.mark.parametrize("batch_tokens", [0, 513, 64.0, "64", True])
def test_invalid_prompt_batch_size_fails_before_start(batch_tokens):
    with pytest.raises(LocalGatewayError, match="batch"):
        LocalGateway("installed:model", batch_tokens=batch_tokens)


def test_venv_path_keeps_sibling_cli_when_python_is_symlink(tmp_path):
    python = tmp_path / "bin/python"
    python.parent.mkdir()
    python.symlink_to(Path("/usr/bin/python3"))
    assert LocalGateway("installed:model", proxy_python=python).proxy_python.with_name("litellm") == python.with_name("litellm")


@pytest.mark.parametrize("port", [80, 65536])
def test_invalid_proxy_bind_port_fails_before_start(port):
    with pytest.raises(LocalGatewayError, match="port"):
        LocalGateway("installed:model", port=port)


def test_context_stops_owned_proxy_even_when_probe_raises(monkeypatch):
    gateway = LocalGateway("installed:model")
    monkeypatch.setattr(gateway, "_preflight", lambda: None)
    class Process:
        terminated, killed, waits = False, False, 0
        def poll(self):
            return None
        def terminate(self):
            self.terminated = True
        def kill(self):
            self.killed = True
        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("local-proxy", timeout)
            return 0
    process, observed = Process(), {}
    def start(command, **options):
        observed.update(options)
        config_path = Path(command[command.index("--config") + 1])
        observed["config_path"] = config_path
        assert gateway._key not in config_path.read_text()
        assert command[command.index("--host") + 1] == "127.0.0.1"
        return process
    monkeypatch.setattr(subprocess, "Popen", start)
    with pytest.raises(RuntimeError, match="probe failed"):
        with gateway.running():
            raise RuntimeError("probe failed")
    assert process.terminated and process.killed and process.waits == 2
    assert observed["stdout"] == observed["stderr"] == subprocess.DEVNULL
    assert not observed["config_path"].exists() and gateway._process is None


@pytest.mark.parametrize("terminate", [False, True])
def test_cli_sigterm_unwinds_owned_resources_and_restores_prior_handler(monkeypatch, terminate, capsys):
    monkeypatch.setattr(LocalGateway, "_preflight", lambda _self: None)
    monkeypatch.setattr(local_gateway.sys, "argv", ["local_gateway", "--model", "installed:model"])
    observed = {}

    class Process:
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
            # SIGTERM is ignored while its first invocation unwinds cleanup.
            if terminate:
                assert signal.getsignal(signal.SIGTERM) == signal.SIG_IGN
        def wait(self, timeout):
            assert self.stopped
            return 0

    process = Process()
    def start(command, **options):
        observed.update(config_path=Path(command[command.index("--config") + 1]), options=options)
        return process
    monkeypatch.setattr(subprocess, "Popen", start)

    async def probe(gateway, directory):
        observed.update(directory=directory, key=gateway._key)
        if terminate:
            handler = signal.getsignal(signal.SIGTERM)
            assert callable(handler)
            handler(signal.SIGTERM, None)
        return {"structured_cited_call": {"status": "passed"}, "fixture": True}
    monkeypatch.setattr(local_gateway, "cited_probe", probe)
    previous = signal.getsignal(signal.SIGTERM)
    def caller_handler(_signum, _frame):
        raise AssertionError("The caller handler should be restored after helper exit")
    signal.signal(signal.SIGTERM, caller_handler)
    try:
        assert local_gateway.main() == (143 if terminate else 0)
        assert signal.getsignal(signal.SIGTERM) is caller_handler
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert process.stopped and not observed["config_path"].exists() and not observed["directory"].exists()
    assert observed["options"]["stdout"] == observed["options"]["stderr"] == subprocess.DEVNULL
    output = capsys.readouterr()
    assert observed["key"] not in output.out + output.err
