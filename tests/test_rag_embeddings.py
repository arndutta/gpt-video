"""Embedding boundaries use synthetic text and mocked gateway/download transports."""

import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
from types import SimpleNamespace

import httpx
import pytest

from platform_app.config import Settings
from platform_app.rag import embedding_download as download
from platform_app.rag.embedding_common import validate_vectors
from platform_app.rag.embeddings import EmbeddingUnavailable, GatewayEmbedder, LocalMiniLM

SECRET = "embedding-test-memory-only-credential"


def gateway(handler, **overrides):
    settings = Settings(gateway_url="https://gateway.example.test/v1", api_key=SECRET)
    return GatewayEmbedder(settings, model="configured-embedding-alias", dimensions=3,
                           allow_external=True, transport=httpx.MockTransport(handler), **overrides)


def test_gateway_requires_explicit_opt_in_and_complete_configuration():
    settings = Settings(gateway_url="https://gateway.example.test/v1", api_key=SECRET)
    with pytest.raises(EmbeddingUnavailable, match="opt-in"):
        GatewayEmbedder(settings, model="embedding", dimensions=3)
    with pytest.raises(EmbeddingUnavailable, match="configured backend"):
        GatewayEmbedder(Settings(), model="embedding", dimensions=3, allow_external=True)
    with pytest.raises(ValueError, match="alias and dimensions"):
        GatewayEmbedder(settings, model=" ", dimensions=3, allow_external=True)


def test_gateway_uses_configured_backend_and_reorders_indexed_vectors():
    requests = []

    def reply(request):
        requests.append(request)
        assert str(request.url) == "https://gateway.example.test/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer " + SECRET
        assert json.loads(request.content) == {"model": "configured-embedding-alias", "input": ["first", "second"]}
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0.0, 1.0, 0.0]},
            {"index": 0, "embedding": [1.0, 0.0, 0.0]},
        ]})

    embedder = gateway(reply)
    assert embedder.embed(["first", "second"]) == [[1, 0, 0], [0, 1, 0]]
    assert len(requests) == 1


@pytest.mark.parametrize("data", [None, [], [{"index": 0, "embedding": [1, 2]}],
    [{"index": 1, "embedding": [1, 2, 3]}], [{"index": True, "embedding": [1, 2, 3]}],
    [{"index": 0, "embedding": [0, 0, 0]}], [{"index": 0, "embedding": [True, 1, 0]}],
    [{"index": 0, "embedding": ["1", 2, 3]}]])
def test_gateway_rejects_unusable_vectors_without_echoing_input(data):
    embedder = gateway(lambda _: httpx.Response(200, json={"data": data}))
    with pytest.raises(EmbeddingUnavailable) as error:
        embedder.embed(["retail document text"])
    assert "retail document text" not in str(error.value) and SECRET not in str(error.value)


def test_gateway_failure_and_probe_use_safe_operational_information():
    captured = []

    def reply(request):
        captured.append(json.loads(request.content))
        return httpx.Response(503, text=SECRET + " private source content")

    embedder = gateway(reply)
    result = embedder.check()
    assert result["available"] is False
    assert SECRET not in json.dumps(result) and "private source content" not in json.dumps(result)
    assert captured == [{"model": "configured-embedding-alias", "input": ["Embedding readiness check."]}]


def test_shared_tls_policy_remains_mandatory_for_gateway():
    settings = Settings(gateway_url="https://gateway.example.test/v1", api_key=SECRET, verify_tls=False)
    embedder = GatewayEmbedder(settings, model="embedding", dimensions=3, allow_external=True,
                               transport=httpx.MockTransport(lambda _: pytest.fail("TLS validation must happen first")))
    with pytest.raises(EmbeddingUnavailable, match="TLS"):
        embedder.embed(["safe synthetic input"])


def test_local_missing_model_never_downloads_or_creates_home_cache(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Availability checks/inference must never download implicitly")

    monkeypatch.setattr(httpx, "Client", forbidden)
    embedder = LocalMiniLM(tmp_path / "models")
    assert embedder.check()["available"] is False
    with pytest.raises(EmbeddingUnavailable, match="preparation"):
        embedder.embed(["local document"])
    assert not (tmp_path / "models").exists()


def test_local_prevents_silent_truncation_before_inference(tmp_path, monkeypatch):
    embedder = LocalMiniLM(tmp_path)
    monkeypatch.setattr(embedder, "check", lambda: {"available": True})
    embedder.__dict__["_tokenizer"] = SimpleNamespace(encode=lambda text: SimpleNamespace(ids=list(range(len(text)))))
    calls = []
    embedder.__dict__["_engine"] = lambda texts: calls.append(texts) or [[1.0] * 384 for _ in texts]
    assert embedder.token_count("hello") == 5
    assert len(embedder.embed(["hello"])[0]) == 384
    with pytest.raises(EmbeddingUnavailable, match="not truncated"):
        embedder.embed(["x" * 257])
    assert calls == [["hello"]]


def test_local_disables_vendor_telemetry_before_constructing_runtime(tmp_path, monkeypatch):
    events = []

    def disable():
        assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"
        events.append("disabled")

    def runtime(path, **kwargs):
        assert events == ["disabled"], "Telemetry must be disabled before runtime construction"
        assert path.endswith("onnx/model.onnx")
        assert kwargs["providers"] == ["CPUExecutionProvider"]
        return SimpleNamespace()

    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "0")
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        disable_telemetry_events=disable, SessionOptions=SimpleNamespace,
        GraphOptimizationLevel=SimpleNamespace(ORT_ENABLE_ALL=1), InferenceSession=runtime))
    embedder = LocalMiniLM(tmp_path)
    monkeypatch.setattr(embedder, "check", lambda: {"available": True})
    assert callable(embedder._engine)


def archive_bytes(names=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name in names or ["onnx/" + name for name in download.MODEL_FILES]:
            data = ("synthetic model fixture " + name).encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def install_download_transport(monkeypatch, body):
    original = httpx.Client
    seen = []

    def factory(**kwargs):
        seen.append(kwargs)
        return original(**kwargs, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body)))

    monkeypatch.setattr(download.httpx, "Client", factory)
    return seen


def test_explicit_preparation_verifies_checksum_and_publishes_complete_cache(tmp_path, monkeypatch):
    body = archive_bytes()
    digest = hashlib.sha256(body).hexdigest()
    monkeypatch.setattr(download, "ARCHIVE_SHA256", digest)
    requests = install_download_transport(monkeypatch, body)
    cache = tmp_path / "models"
    root = download.prepare_cache(cache, Settings())
    assert root == cache / digest and download.cache_ready(root)
    assert len(requests) == 1 and requests[0]["verify"].check_hostname
    assert download.prepare_cache(cache, Settings()) == root
    assert len(requests) == 1
    (root / "onnx/model.onnx").write_text("corrupted")
    assert not download.cache_ready(root)
    with pytest.raises(EmbeddingUnavailable, match="corrupt"):
        download.prepare_cache(cache, Settings())
    assert len(requests) == 1


def test_download_checksum_failure_leaves_no_active_cache(tmp_path, monkeypatch):
    install_download_transport(monkeypatch, b"invalid archive")
    with pytest.raises(EmbeddingUnavailable, match="checksum"):
        download.prepare_cache(tmp_path / "models", Settings())
    assert not (tmp_path / "models" / download.ARCHIVE_SHA256).exists()
    assert list((tmp_path / "models").iterdir()) == []


def test_unsafe_archive_members_cannot_escape_cache(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    archive.write_bytes(archive_bytes(["../escaped.txt"]))
    with pytest.raises(EmbeddingUnavailable, match="unsafe"):
        download.extract_verified_archive(archive, tmp_path / "prepared")
    assert not (tmp_path / "escaped.txt").exists()


def test_embedding_validation_rejects_nonfinite_vectors():
    with pytest.raises(EmbeddingUnavailable, match="nonfinite"):
        validate_vectors([[float("nan"), 1, 2]], 1, 3)
