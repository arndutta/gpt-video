"""Actionable pre-flight for the initial local quantitative-preview release."""

import argparse
import asyncio
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import socket
import sys
import tempfile

import httpx
from pydantic import ValidationError

from platform_app.config import Settings, tls_context
from scripts.runtime import node_runtime

ROOT = Path(__file__).resolve().parents[1]


async def gateway_probe(settings: Settings):
    if not settings.gateway_base_url or not settings.api_key:
        raise RuntimeError("Export GATEWAY_URL and GATEWAY_API_KEY before requiring a gateway probe.")
    aliases = [settings.model_analyst, settings.model_strategist]
    if not all(aliases):
        raise RuntimeError("Set LLM_MODEL_ANALYST and LLM_MODEL_STRATEGIST to gateway aliases.")
    try:
        headers = {"Authorization": f"Bearer {settings.api_key.get_secret_value()}"}
        async with httpx.AsyncClient(verify=tls_context(settings), timeout=10) as client:
            response = await client.get(settings.gateway_base_url + "/models", headers=headers)
            response.raise_for_status()
            available = {item["id"] for item in response.json().get("data", [])}
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise RuntimeError("Gateway probe failed. Check network access, URL, credential, and corporate CA.") from None
    missing = set(aliases) - available
    if missing:
        raise RuntimeError("Configured aliases are unavailable. Gateway models: " + ", ".join(sorted(available)))


def check(*, require_gateway=False, skip_ports=False) -> tuple[Settings, list[str]]:
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("Activate .venv, or invoke startup.sh/startup.bat with its project interpreter.")
    try:
        settings = Settings.from_environment()
        tls_context(settings)
    except (ValidationError, OSError, ValueError):
        raise RuntimeError("Invalid environment. Check URLs, ports, booleans, and corporate CA paths.") from None
    for dependency in ["fastapi", "pydantic", "httpx", "numpy", "scipy", "uvicorn", "structlog"]:
        try:
            version(dependency)
        except PackageNotFoundError:
            raise RuntimeError(f"Missing {dependency}. Install requirements.lock in .venv.") from None
    _, _, node_version = node_runtime()
    if not (ROOT / "web/node_modules/vite/bin/vite.js").exists():
        raise RuntimeError("UI dependencies are missing. Run npm ci in web/ using a supported Node runtime.")
    for directory in [settings.data_dir, settings.data_dir / "chroma"]:
        directory.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryFile(dir=directory) as probe:
                probe.write(b"writable")
        except OSError:
            raise RuntimeError(f"Storage directory is not writable: {directory}") from None
    if not skip_ports:
        for port in [8000, 8001, 5173]:
            try:
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", port))
            except PermissionError:
                raise RuntimeError(f"Permission denied checking local port {port}. Allow local network access.") from None
            except OSError:
                raise RuntimeError(f"Port {port} is unavailable. Stop the process using it and retry.") from None
    messages = [f"Python {sys.version.split()[0]} in venv; Node {node_version}; storage writable.",
                "Initial release: quantitative preview; grounded agents, execution, and loop are unavailable."]
    if require_gateway:
        asyncio.run(gateway_probe(settings))
        messages.append("Configured analyst/strategist aliases verified at the gateway.")
    else:
        messages.append("Gateway probe skipped for the explicit quantitative-preview startup path.")
    return settings, messages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-gateway", action="store_true")
    parser.add_argument("--skip-ports", action="store_true", help="Check dependencies while services are running.")
    args = parser.parse_args()
    try:
        _, messages = check(require_gateway=args.require_gateway, skip_ports=args.skip_ports)
    except (RuntimeError, OSError) as error:
        parser.exit(1, f"Pre-flight failed: {error}\n")
    print("\n".join(messages))


if __name__ == "__main__":
    main()
