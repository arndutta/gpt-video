"""Actionable, mode-specific readiness checks before any local service starts."""

import argparse
import asyncio
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import socket
import sys
import tempfile

from pydantic import ValidationError

from platform_app.config import Settings, tls_context
from scripts.runtime import node_runtime

ROOT = Path(__file__).resolve().parents[1]


async def gateway_probe(settings: Settings, transport=None):
    from platform_app.gateway import GatewayError, verify_gateway

    try:
        return await verify_gateway(settings, transport)
    except GatewayError as error:
        available = " Available aliases: " + ", ".join(error.available_models) if error.available_models else ""
        raise RuntimeError(error.detail + available) from None


def embedding_probe(settings: Settings) -> dict:
    from platform_app.rag.embeddings import EmbeddingUnavailable
    from platform_app.rag.factory import create_embedder

    try:
        embedder = create_embedder(settings)
        report = embedder.check()
        if not report["available"]:
            raise EmbeddingUnavailable(report["detail"])
        if settings.embedding_provider == "local":
            embedder.embed(["Embedding readiness check."])
        return report
    except EmbeddingUnavailable as error:
        raise RuntimeError("Embedding pre-flight failed: " + str(error)) from None


def check(*, mode=None, require_gateway=False, skip_ports=False, require_embeddings=False) -> tuple[Settings, list[str]]:
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("Activate .venv, or invoke startup.sh/startup.bat with its project interpreter.")
    try:
        settings = Settings.from_environment()
        tls_context(settings)
    except (ValidationError, OSError, ValueError):
        raise RuntimeError("Invalid environment. Check URLs, ports, booleans, and corporate CA paths.") from None
    mode = "grounded" if require_gateway else mode or getattr(settings, "startup_mode", "preview")
    if mode not in {"preview", "grounded"}:
        raise RuntimeError("Startup mode must be preview or grounded.")
    require_gateway = require_gateway or mode == "grounded"
    require_embeddings = require_embeddings or mode == "grounded"
    for dependency in ["fastapi", "pydantic", "httpx", "numpy", "scipy", "uvicorn", "structlog",
                       "chromadb", "onnxruntime", "tokenizers", "python-multipart", "langchain",
                       "langchain-openai", "langgraph", "langgraph-checkpoint-sqlite"]:
        try:
            version(dependency)
        except PackageNotFoundError:
            raise RuntimeError(f"Missing {dependency}. Install requirements.lock in .venv.") from None
    _, _, node_version = node_runtime()
    if not (ROOT / "web/node_modules/vite/bin/vite.js").exists():
        raise RuntimeError("UI dependencies are missing. Run npm ci in web/ using a supported Node runtime.")
    for directory in [settings.data_dir, settings.data_dir / "chroma"]:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=directory) as probe:
                probe.write(b"writable")
        except OSError:
            raise RuntimeError(f"Storage directory is not writable: {directory}") from None
    if not skip_ports:
        for port in [8000, 8001, 5173]:
            try:
                with socket.socket() as probe:
                    # Match the development servers: recently closed TCP connections must
                    # not be mistaken for an active listener during an immediate restart.
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe.bind(("127.0.0.1", port))
            except PermissionError:
                raise RuntimeError(f"Permission denied checking local port {port}. Allow local network access.") from None
            except OSError:
                raise RuntimeError(f"Port {port} is unavailable. Stop the process using it and retry.") from None
    messages = [f"Python {sys.version.split()[0]} in venv; Node {node_version}; storage writable.",
                f"Startup mode: {mode}. Published grounding evidence is still required for a grounded run."]
    if require_gateway:
        asyncio.run(gateway_probe(settings))
        messages.append("All four model aliases are advertised by the gateway. Structured generation requires a successful model call.")
    else:
        messages.append("Gateway probe skipped for the explicit quantitative-preview startup path.")
    if require_embeddings:
        report = embedding_probe(settings)
        messages.append(f"Embedding provider {report['provider']} and {report['dimensions']} dimensions verified.")
    else:
        messages.append("Embedding probe skipped. Use --require-embeddings to verify T14 readiness explicitly.")
    return settings, messages


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preview", "grounded"), help="Grounded mode requires gateway and embedding checks; defaults to PRICING_STARTUP_MODE or preview.")
    parser.add_argument("--require-gateway", action="store_true")
    parser.add_argument("--require-embeddings", action="store_true")
    parser.add_argument("--skip-ports", action="store_true", help="Check dependencies while services are running.")
    return parser, parser.parse_args(argv)


def main():
    parser, args = arguments()
    try:
        _, messages = check(mode=args.mode, require_gateway=args.require_gateway, skip_ports=args.skip_ports,
                            require_embeddings=args.require_embeddings)
    except (RuntimeError, OSError) as error:
        parser.exit(1, f"Pre-flight failed: {error}\n")
    print("\n".join(messages))


if __name__ == "__main__":
    main()
