"""Legacy imports retain immutable citations and publish only complete SQLite evidence."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from platform_app.config import Settings
from platform_app.rag import migration
from platform_app.rag.factory import create_store
from platform_app.rag.ledger import Manifest
from platform_app.rag.models import COLLECTION_NAMES, RagError
from platform_app.rag.store import RagStore
from test_rag_store import TestEmbedder


@pytest.fixture
def legacy(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    from chromadb.config import Settings as ChromaSettings

    path = tmp_path / "chroma"
    path.mkdir()
    engine = TestEmbedder()
    manifest = Manifest(path / "manifest.sqlite3", engine.model_id, engine.dimensions)
    client = chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))
    for name in COLLECTION_NAMES:
        client.get_or_create_collection(name, embedding_function=None, metadata={"hnsw:space": "cosine"})
    citations = []
    for version, text in (("v1", "Original margin and cost policy."), ("v2", "Updated margin and stock policy.")):
        key = hashlib.sha256(json.dumps(["pricing_policy", "policy", version]).encode()).hexdigest()
        citation = f"rag:pricing_policy:{key}:0"
        digest = hashlib.sha256(text.encode()).hexdigest()
        _ready, expected = manifest.prepare("pricing_policy", "policy", version, key, digest, 1)
        metadata = {"document_key": key, "source_id": "policy", "version": version, "title": "Policy",
                    "collection": "pricing_policy", "content_hash": digest,
                    "chunk_index": 0, "start_char": 0, "end_char": len(text), "source_uri": "policy.md"}
        client.get_collection("pricing_policy", embedding_function=None).upsert(
            ids=[citation], documents=[text], metadatas=[metadata], embeddings=engine.embed([text]))
        manifest.publish("pricing_policy", "policy", version, expected)
        citations.append((citation, text))
    client.close()
    return tmp_path, citations


def source_hashes(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file() and not path.name.endswith(("-wal", "-shm"))}


def test_legacy_versions_vectors_and_citations_survive_migration_and_restart(legacy, monkeypatch):
    directory, citations = legacy
    before = source_hashes(directory / "chroma")
    result = migration.migrate_chroma(directory)
    assert result == {"status": "migrated", "migrated": True, "chunks": 2, "versions": 2, "active_documents": 1}
    assert source_hashes(directory / "chroma") == before
    assert not migration.requires_migration(directory)
    with RagStore(directory / "rag.db", TestEmbedder()) as store:
        context = store.retrieve("margin")
        assert context.corpus_version == 2
        assert {chunk.version for chunk in context.chunks} == {"v2"}
        for citation, text in citations:
            assert store.resolve_citation(citation).text == text
    with RagStore(directory / "rag.db", TestEmbedder()) as restarted:
        assert restarted.resolve_citation(citations[0][0]).version == "v1"
    monkeypatch.setattr(migration, "_chunks", lambda *args: pytest.fail("A repeated migration must not reopen Chroma"))
    assert migration.migrate_chroma(directory)["status"] == "already_migrated"


def test_incomplete_migration_keeps_source_and_blocks_empty_target_retrieval(legacy, monkeypatch):
    directory, _citations = legacy
    before = source_hashes(directory / "chroma")
    original = sqlite3.connect

    class Interrupted(sqlite3.Connection):
        def execute(self, query, *args, **kwargs):
            if query.startswith("INSERT INTO rag_migrations"):
                raise sqlite3.OperationalError("Explicit failure before commit")
            return super().execute(query, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(migration.sqlite3, "connect", lambda *args, **kwargs: original(*args, factory=Interrupted, **kwargs))
        with pytest.raises(RagError, match="without publication"):
            migration.migrate_chroma(directory)
    assert source_hashes(directory / "chroma") == before
    with closing(sqlite3.connect(directory / "rag.db")) as db:
        assert db.execute("SELECT count(*) FROM versions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM rag_chunks").fetchone()[0] == 0
    assert migration.requires_migration(directory)
    with pytest.raises(RagError, match="Migrate"):
        create_store(Settings(data_dir=directory))
    assert migration.migrate_chroma(directory)["migrated"]


def test_populated_sqlite_store_is_preserved_instead_of_overwritten(legacy):
    directory, _citations = legacy
    from test_rag_store import document

    with RagStore(directory / "rag.db", TestEmbedder()) as store:
        store.ingest(document(source_id="sqlite-only", version="v1"))
        citation = store.retrieve("margin").chunks[0].citation_id
    with pytest.raises(RagError, match="will not overwrite"):
        migration.migrate_chroma(directory)
    with RagStore(directory / "rag.db", TestEmbedder()) as store:
        assert store.resolve_citation(citation).source_id == "sqlite-only"


def test_missing_published_legacy_chunk_cannot_be_migrated(legacy):
    directory, citations = legacy
    import chromadb

    client = chromadb.PersistentClient(path=str(directory / "chroma"))
    client.get_collection("pricing_policy", embedding_function=None).delete(ids=[citations[1][0]])
    client.close()
    with pytest.raises(RagError, match="missing or duplicate"):
        migration.migrate_chroma(directory)
    assert not (directory / "rag.db").exists()


def test_fresh_sqlite_store_needs_no_legacy_dependency(tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "_chunks", lambda *args: pytest.fail("SQLite must not load a legacy reader"))
    assert migration.migrate_chroma(tmp_path)["status"] == "no_legacy_store"
    assert not migration.requires_migration(tmp_path)
