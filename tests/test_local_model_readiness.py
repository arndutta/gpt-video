"""Fast readiness still detects model edits, replacement and missing cache files."""

import hashlib
import json
import os

import pytest

from platform_app.rag.embedding_download import ARCHIVE_SHA256, MODEL_FILES
from platform_app.rag.local_embeddings import LocalMiniLM
from platform_app.rag.embedding_common import EmbeddingUnavailable
import platform_app.rag.local_embeddings as local


def test_readiness_reuses_integrity_result_only_for_unchanged_files(tmp_path, monkeypatch):
    root = tmp_path / ARCHIVE_SHA256
    (root / "onnx").mkdir(parents=True)
    content = b"verified model fixture"
    files = {}
    for name in MODEL_FILES:
        (root / "onnx" / name).write_bytes(content)
        files[name] = hashlib.sha256(content).hexdigest()
    (root / "manifest.json").write_text(json.dumps({"archive_sha256": ARCHIVE_SHA256, "files": files}))
    original, calls = local.cache_ready, []
    def verify(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(local, "cache_ready", verify)
    embedder = LocalMiniLM(tmp_path)
    assert embedder.check()["available"] and embedder.check()["available"]
    assert len(calls) == 1, "Unchanged files should not be rehashed on every query"
    target = root / "onnx" / "model.onnx"
    before = target.stat()
    target.write_bytes(b"tampered model fixture")
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert not embedder.check()["available"] and len(calls) == 2
    target.write_bytes(content)
    assert embedder.check()["available"]
    target.unlink()
    assert not embedder.check()["available"]


def test_vector_memoization_keeps_token_and_integrity_checks_on_every_call(tmp_path, monkeypatch):
    embedder = LocalMiniLM(tmp_path)
    ready, calls = [True], []
    monkeypatch.setattr(embedder, "check", lambda: {"available": ready[0]})
    monkeypatch.setattr(embedder, "token_count", lambda text: len(text))
    def engine(texts):
        calls.append(texts)
        return [[1.] + [0.] * 383 for _ in texts]
    embedder.__dict__["_engine"] = engine
    original = embedder.embed(["policy", "policy"])
    assert calls == [["policy"]]
    original[0][0] = 0
    assert embedder.embed(["policy"])[0][0] == 1 and len(calls) == 1
    with pytest.raises(EmbeddingUnavailable, match="256-token"):
        embedder.embed(["x" * 257])
    ready[0] = False
    with pytest.raises(EmbeddingUnavailable, match="unavailable or corrupt"):
        embedder.embed(["policy"])
