"""T14 provider selection and CLI checks never imply permission for external embeddings."""

import pytest
from pydantic import ValidationError

from platform_app.config import Settings
from platform_app.rag.embeddings import EmbeddingUnavailable, LocalMiniLM
from platform_app.rag.factory import create_embedder
from scripts import preflight, rag


def test_local_default_and_explicit_gateway_opt_in(monkeypatch, tmp_path):
    settings = Settings(data_dir=tmp_path)
    local = create_embedder(settings)
    assert isinstance(local, LocalMiniLM) and local.cache_dir == tmp_path / "models"
    assert not local.check()["available"]
    with pytest.raises(EmbeddingUnavailable, match="ALLOW_GATEWAY_EMBEDDINGS"):
        create_embedder(Settings(embedding_provider="gateway"))
    with pytest.raises(EmbeddingUnavailable, match="RAG_GATEWAY_EMBEDDING_MODEL"):
        create_embedder(Settings(embedding_provider="gateway", allow_gateway_embeddings=True))
    with pytest.raises(RuntimeError, match="RAG_GATEWAY_EMBEDDING_MODEL"):
        preflight.embedding_probe(Settings(embedding_provider="gateway", allow_gateway_embeddings=True,
                                           gateway_embedding_model=" "))
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "gateway")
    monkeypatch.setenv("ALLOW_GATEWAY_EMBEDDINGS", "true")
    monkeypatch.setenv("RAG_GATEWAY_EMBEDDING_MODEL", "corporate-embedding-alias")
    configured = Settings.from_environment()
    assert configured.embedding_provider == "gateway" and configured.allow_gateway_embeddings
    assert configured.gateway_embedding_model == "corporate-embedding-alias"


@pytest.mark.parametrize("field", ["rag_router_top_k", "rag_narrator_top_k", "rag_analyst_top_k", "rag_strategist_top_k"])
def test_role_breadth_cannot_disable_retrieval(field):
    for value in (0, -1, 11):
        with pytest.raises(ValidationError):
            Settings(**{field: value})
    assert Settings(**{field: 2}).retrieval_breadths[field.removeprefix("rag_").removesuffix("_top_k")] == 2


def test_invalid_chunk_environment_is_sanitized(monkeypatch):
    monkeypatch.setenv("RAG_CHUNK_SIZE", "64")
    monkeypatch.setenv("RAG_CHUNK_OVERLAP", "64")
    with pytest.raises(ValueError, match="Invalid environment settings for: configuration"):
        Settings.from_environment()


def test_explicit_model_probe_is_actionable_without_downloading(tmp_path):
    with pytest.raises(RuntimeError, match="Embedding pre-flight failed"):
        preflight.embedding_probe(Settings(data_dir=tmp_path))
    assert not (tmp_path / "models").exists()


def test_cli_reports_missing_cache_and_omits_invalid_environment_values(monkeypatch, capsys, tmp_path):
    assert rag.main(["--data-dir", str(tmp_path), "check"]) == 1
    assert '"available": false' in capsys.readouterr().out
    secret = "not-a-real-secret-test-marker"
    monkeypatch.setenv("RAG_ANALYST_TOP_K", secret)
    assert rag.main(["check"]) == 1
    output = capsys.readouterr()
    assert secret not in output.err + output.out


def test_role_overrides_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("RAG_ANALYST_TOP_K", "5")
    assert Settings.from_environment().retrieval_breadths == {
        "router": 1, "narrator": 2, "analyst": 5, "strategist": 4}
