"""Explicit, lifecycle-owned LiteLLM/Ollama integration probe; never a fallback."""

import argparse
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("router", "narrator", "analyst", "strategist")
ALIASES = {role: "local-" + role for role in ROLES}
BATCH_SIZES = (16, 32, 64, 128, 256, 512)


class LocalGatewayError(RuntimeError):
    """Only safe, static operational messages cross this boundary."""


class _TerminationSignal(KeyboardInterrupt):
    def __init__(self, signum):
        self.signum = signum


@contextmanager
def _sigterm_cleanup():
    """Let CLI resource owners unwind instead of leaving a proxy after SIGTERM."""
    previous = signal.getsignal(signal.SIGTERM)

    def stop(signum, _frame):
        # A repeated termination must not interrupt the bounded child cleanup.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise _TerminationSignal(signum)

    signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def proxy_config(model, ollama_port, *, batch_tokens=512):
    return {
        "model_list": [{"model_name": alias, "litellm_params": {
            "model": "ollama_chat/" + model,
            "api_base": f"http://127.0.0.1:{ollama_port}",
            "num_ctx": 4096, "num_batch": batch_tokens, "max_tokens": 800, "keep_alive": 0,
            "timeout": 120,
        }, "model_info": {"input_cost_per_token": 0, "output_cost_per_token": 0}}
            for alias in ALIASES.values()],
        "general_settings": {
            "master_key": "os.environ/LOCAL_GATEWAY_MASTER_KEY",
            "disable_spend_logs": True, "disable_error_logs": True,
            "store_prompts_in_spend_logs": False, "disable_model_info_refresh": True,
            "disable_prisma_schema_update": True, "trusted_proxy_ranges": [],
        },
        "litellm_settings": {
            "callbacks": [], "success_callback": [], "failure_callback": [],
            "set_verbose": False, "turn_off_message_logging": True,
            "disable_hf_tokenizer_download": True, "num_retries": 0,
            "request_timeout": 120,
        },
        "router_settings": {"num_retries": 0, "timeout": 120},
    }


def child_environment(key):
    # Do not inherit cloud credentials, tracing destinations, proxy or database config.
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT",
               "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    environment.update({
        "LOCAL_GATEWAY_MASTER_KEY": key, "LITELLM_MODE": "PRODUCTION",
        "LITELLM_OFFLINE_MODE": "true", "LITELLM_LOCAL_MODEL_COST_MAP": "true",
        "LITELLM_TELEMETRY_DISABLED": "true", "LITELLM_LOG": "ERROR",
        "PRISMA_OFFLINE_MODE": "true", "CHECKPOINT_DISABLE": "1",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "NO_DOCS": "True", "NO_REDOC": "True", "DISABLE_ADMIN_UI": "True",
        "DO_NOT_TRACK": "1",
    })
    return environment


class LocalGateway:
    def __init__(self, model, *, port=4002, ollama_port=11434, proxy_python=None, batch_tokens=512):
        if not model or len(model) > 200 or any(c.isspace() for c in model):
            raise LocalGatewayError("Select one installed Ollama model identifier.")
        if not 1024 <= port <= 65535 or not 1 <= ollama_port <= 65535:
            raise LocalGatewayError("Invalid local port.")
        if type(batch_tokens) is not int or batch_tokens not in BATCH_SIZES:
            raise LocalGatewayError("Select a supported local prompt batch size.")
        self.model, self.port, self.ollama_port = model, port, ollama_port
        self.batch_tokens = batch_tokens
        # Preserve the venv executable directory; resolving its symlink loses sibling CLI scripts.
        self.proxy_python = Path(proxy_python or ROOT / ".cache/local-gateway-env/bin/python").absolute()
        self._key, self._process = "sk-" + secrets.token_urlsafe(48), None

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}/v1"

    def settings(self, data_dir):
        from platform_app.config import Settings
        return Settings(data_dir=data_dir, embedding_cache_dir=ROOT / "data/models",
                        gateway_url=self.base_url, api_key=self._key,
                        llm_timeout_seconds=120, llm_transport_retries=0,
                        **{"model_" + role: alias for role, alias in ALIASES.items()})

    def _preflight(self):
        if not self.proxy_python.is_file():
            raise LocalGatewayError("Install the isolated LiteLLM environment first; see docs/local-gateway.md.")
        with socket.socket() as check:
            try:
                check.bind(("127.0.0.1", self.port))
            except OSError:
                raise LocalGatewayError("Local gateway port is already occupied or unavailable.") from None
        try:
            with urlopen(f"http://127.0.0.1:{self.ollama_port}/api/tags", timeout=5) as response:
                payload = json.loads(response.read(1_000_001))
            models = {item["name"] for item in payload["models"]}
        except Exception:
            raise LocalGatewayError("The existing local Ollama model catalog is unavailable.") from None
        if self.model not in models:
            raise LocalGatewayError("The requested model is not installed; this helper never downloads models.")

    @contextmanager
    def running(self):
        self._preflight()
        with tempfile.TemporaryDirectory(prefix="pricing-local-gateway-") as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(proxy_config(self.model, self.ollama_port, batch_tokens=self.batch_tokens)))
            command = [str(self.proxy_python.with_name("litellm")), "--config", str(path),
                       "--host", "127.0.0.1", "--port", str(self.port), "--num_workers", "1"]
            try:
                self._process = subprocess.Popen(command, cwd=directory,
                    env=child_environment(self._key), stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                yield self
            finally:
                if self._process is not None and self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=5)
                self._process = None

    async def ready(self, settings, *, timeout=45):
        from platform_app.gateway import GatewayError, verify_gateway
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process is None or self._process.poll() is not None:
                raise LocalGatewayError("Local LiteLLM failed to start; no prompt or credential logs were retained.")
            try:
                return await verify_gateway(settings)
            except GatewayError:
                await asyncio.sleep(.3)
        raise LocalGatewayError("Local LiteLLM did not advertise the four aliases before the startup deadline.")


async def cited_probe(gateway, directory):
    from platform_app.llm import GroundedLLM, GroundedLLMError
    from platform_app.rag.factory import create_store
    from platform_app.rag.models import Document
    from platform_app.telemetry import Telemetry
    from platform_app.workflow.schemas import CitedNarrative

    settings = gateway.settings(directory)
    verified = await gateway.ready(settings)
    rag = await asyncio.to_thread(create_store, settings)
    telemetry = Telemetry(directory)
    class Grounding:
        async def retrieve(self, query, role):
            return await asyncio.to_thread(rag.retrieve, query, role=role)
    llm = GroundedLLM(lambda: settings, Grounding(), telemetry, directory)
    try:
        await asyncio.to_thread(rag.ingest, Document(
            source_id="local-probe-policy", title="Public synthetic policy", version="v1",
            collection="pricing_policy", text="Synthetic probe policy: a human must review every price change. "
            "This probe must leave prices unchanged. Evidence must be cited exactly."))
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(llm.generate(CitedNarrative, role="analyst",
                query="Who must review a synthetic price change?", facts={"probe": "public synthetic", "price_writes": 0},
                prompt="In one short sentence explain who reviews changes. Use empty assumptions and anomalies. "
                       "Copy the exact supplied citation_id into citations.", policy_version="local-probe-v1"), timeout=245)
            call = {"status": "passed", "citation_count": len(result.citations),
                    "citations": result.citations, "schema": CitedNarrative.__name__}
        except GroundedLLMError as error:
            call = {"status": "failed", "error_code": error.code}
        except TimeoutError:
            call = {"status": "failed", "error_code": "probe_deadline"}
        return {"gateway_aliases_verified": verified["verified"], "aliases": ALIASES,
                "backend_model": gateway.model, "structured_cited_call": call,
                "request_options": {"num_ctx": 4096, "num_batch": gateway.batch_tokens, "max_tokens": 800},
                "model_seconds": round(time.monotonic() - started, 3), "usage": llm.snapshot(),
                "actual_price_writes": 0, "local_integration_only": True,
                "corporate_tiers_certified": False}
    finally:
        await llm.close()
        telemetry.close()
        await asyncio.to_thread(rag.close)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Exact already installed Ollama identifier")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--ollama-port", type=int, default=11434)
    parser.add_argument("--proxy-python", type=Path)
    parser.add_argument("--batch-tokens", type=int, choices=BATCH_SIZES, default=512,
                        help="Explicit per-request Ollama prompt batch size; context stays at 4096")
    parser.add_argument("--output", type=Path, help="Optional metadata-only result JSON")
    args = parser.parse_args()
    try:
        gateway = LocalGateway(args.model, port=args.port, ollama_port=args.ollama_port,
                               proxy_python=args.proxy_python, batch_tokens=args.batch_tokens)
        with _sigterm_cleanup(), gateway.running(), tempfile.TemporaryDirectory(prefix="pricing-local-probe-") as directory:
            report = asyncio.run(cited_probe(gateway, Path(directory)))
        report["proxy_stopped"] = True
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 0 if report["structured_cited_call"]["status"] == "passed" else 1
    except LocalGatewayError as error:
        print(json.dumps({"status": "failed", "detail": str(error)}))
        return 1
    except _TerminationSignal as error:
        return 128 + error.signum
    except KeyboardInterrupt:
        return 130
    except Exception:
        print(json.dumps({"status": "failed", "detail": "Local probe failed safely; no provider response or credentials logged."}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
