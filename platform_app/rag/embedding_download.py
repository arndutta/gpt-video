"""Explicit, checksum-verified preparation of the official Chroma MiniLM ONNX model."""

import hashlib
import json
import os
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

import httpx

from platform_app.config import Settings, tls_context
from platform_app.rag.embedding_common import EmbeddingUnavailable

# Same public artifact and checksum as Chroma's ONNXMiniLM_L6_V2 implementation.
MODEL_URL = "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
ARCHIVE_SHA256 = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"
MODEL_FILES = ("config.json", "model.onnx", "special_tokens_map.json",
               "tokenizer_config.json", "tokenizer.json", "vocab.txt")
MAX_DOWNLOAD_BYTES = 100_000_000
MAX_EXTRACTED_BYTES = 200_000_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_ready(root: Path) -> bool:
    """Validate both completeness and per-file integrity without accessing the network."""
    try:
        manifest = json.loads((root / "manifest.json").read_text())
        if manifest.get("archive_sha256") != ARCHIVE_SHA256:
            return False
        files = manifest.get("files", {})
        return all((root / "onnx" / name).is_file()
                   and files.get(name) == sha256_file(root / "onnx" / name) for name in MODEL_FILES)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def download_archive(destination: Path, settings: Settings) -> None:
    digest, size = hashlib.sha256(), 0
    with httpx.Client(verify=tls_context(settings), timeout=30, follow_redirects=True) as client:
        with client.stream("GET", MODEL_URL) as response:
            response.raise_for_status()
            with destination.open("wb") as stream:
                for block in response.iter_bytes(chunk_size=1024 * 1024):
                    size += len(block)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise EmbeddingUnavailable("Embedding model download exceeded its size limit.")
                    digest.update(block)
                    stream.write(block)
    if digest.hexdigest() != ARCHIVE_SHA256:
        raise EmbeddingUnavailable("Embedding model archive checksum failed; no model was activated.")


def extract_verified_archive(archive: Path, destination: Path) -> dict:
    """Extract allowlisted regular files only, independent of tarfile filter availability."""
    total, found = 0, set()
    (destination / "onnx").mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            name = member.name.removeprefix("./")
            if member.isdir() and name.rstrip("/") == "onnx":
                continue
            allowed = {"onnx/" + item for item in MODEL_FILES}
            if not member.isfile() or name not in allowed or name in found:
                raise EmbeddingUnavailable("Embedding archive contains an unexpected or unsafe member.")
            total += member.size
            if member.size < 1 or total > MAX_EXTRACTED_BYTES:
                raise EmbeddingUnavailable("Embedding archive exceeds its safe extraction limits.")
            source = bundle.extractfile(member)
            if source is None:
                raise EmbeddingUnavailable("Embedding archive has an unreadable member.")
            with source, (destination / name).open("wb") as target:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    target.write(block)
            found.add(name)
    if found != {"onnx/" + name for name in MODEL_FILES}:
        raise EmbeddingUnavailable("Embedding archive is incomplete.")
    return {name: sha256_file(destination / "onnx" / name) for name in MODEL_FILES}


def prepare_cache(cache_dir: Path, settings: Settings) -> Path:
    root = cache_dir / ARCHIVE_SHA256
    if cache_ready(root):
        return root
    if root.exists():
        raise EmbeddingUnavailable("Embedding cache is incomplete or corrupt. Select a new cache directory and prepare it.")
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="minilm-prepare-", dir=cache_dir) as temporary:
            stage = Path(temporary)
            archive, payload = stage / "model.tar.gz", stage / "payload"
            download_archive(archive, settings)
            files = extract_verified_archive(archive, payload)
            (payload / "manifest.json").write_text(json.dumps({"archive_sha256": ARCHIVE_SHA256, "files": files}))
            try:
                os.replace(payload, root)
            except OSError:
                if not cache_ready(root):
                    raise
        return root
    except EmbeddingUnavailable:
        raise
    except (httpx.HTTPError, OSError, tarfile.TarError, ValueError):
        raise EmbeddingUnavailable("Embedding model preparation failed. Check network access, corporate CA trust, and cache permissions.") from None
