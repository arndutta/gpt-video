"""SQLite vectors retain source text, filter active versions and fail closed on damage."""

import sqlite3
import struct

import pytest

from platform_app.rag.embedding_common import EmbeddingUnavailable
from platform_app.rag.models import EmbeddingMismatch
from platform_app.rag.sqlite_index import SQLiteIndex


def metadata(key, **changes):
    return {"document_key": key, "source_id": "policy", "version": key,
            "title": "Margin policy", "content_hash": "hash", "collection": "policy",
            "chunk_index": 0, "start_char": 0, "end_char": 12, **changes}


def test_vectors_and_metadata_persist_exactly_and_query_filters_active_versions(tmp_path):
    path = tmp_path / "rag.db"
    index = SQLiteIndex(path, 3)
    collection = index.get_or_create_collection("policy")
    vectors = [[1.2345678901234567, 0, 0], [0, 1, 0], [-1, 0, 0]]
    collection.upsert(ids=["a", "b", "c"], documents=["A policy", "B policy", "C policy"],
                      metadatas=[metadata("v1"), metadata("v2"), metadata("v2")], embeddings=vectors)
    assert collection.get(ids=["a"], include=[]) == {"ids": ["a"]}
    index.close()
    restarted = SQLiteIndex(path, 3)
    collection = restarted.get_or_create_collection("policy")
    saved = collection.get(include=["documents", "metadatas", "embeddings"])
    assert saved["embeddings"] == vectors
    assert saved["documents"] == ["A policy", "B policy", "C policy"]
    assert saved["metadatas"][0]["document_key"] == "v1"
    result = collection.query(query_embeddings=[[1, 0, 0]], n_results=3)
    assert result["ids"] == [["a", "b", "c"]]
    assert result["distances"][0] == pytest.approx([0, 1, 2])
    active = collection.query(query_embeddings=[[1, 0, 0]], n_results=3,
                              where={"document_key": {"$in": ["v2"]}})
    assert active["ids"] == [["b", "c"]]
    assert collection.query(query_embeddings=[[1, 0, 0]], where={"document_key": {"$in": []}})["ids"] == [[]]
    other = restarted.get_or_create_collection("other")
    assert other.count() == 0
    collection.delete(ids=["b"], where={"document_key": "v1"})
    assert collection.count() == 3
    collection.delete(where={"document_key": "v2"})
    assert collection.count() == 1
    restarted.close()


@pytest.mark.parametrize("bad", [[0, 0, 0], [1, 2], [float("nan"), 1, 1], [True, 1, 1]])
def test_invalid_batch_vectors_write_no_partial_chunks(tmp_path, bad):
    index = SQLiteIndex(tmp_path / "rag.db", 3)
    collection = index.get_or_create_collection("policy")
    with pytest.raises(EmbeddingUnavailable):
        collection.upsert(ids=["a", "b"], documents=["A policy", "B policy"],
                          metadatas=[metadata("v1"), metadata("v1")], embeddings=[[1, 0, 0], bad])
    assert collection.count() == 0
    index.close()


def test_corrupt_embedding_cannot_be_retrieved_or_resolved(tmp_path):
    path = tmp_path / "rag.db"
    index = SQLiteIndex(path, 3)
    collection = index.get_or_create_collection("policy")
    collection.upsert(ids=["a"], documents=["A policy"], metadatas=[metadata("v1")], embeddings=[[1, 0, 0]])
    with sqlite3.connect(path) as db:
        db.execute("UPDATE rag_chunks SET embedding=?", (struct.pack("<3d", float("inf"), 0, 0),))
    with pytest.raises(ValueError, match="embedding"):
        collection.get(ids=["a"])
    with pytest.raises(sqlite3.OperationalError):
        collection.query(query_embeddings=[[1, 0, 0]])
    index.close()


def test_wrong_dimensions_and_closed_index_fail_before_vector_reuse(tmp_path):
    path = tmp_path / "rag.db"
    index = SQLiteIndex(path, 3)
    collection = index.get_or_create_collection("policy")
    incompatible = SQLiteIndex(path, 4)
    with pytest.raises(EmbeddingMismatch):
        incompatible.get_or_create_collection("policy")
    incompatible.close()
    index.close()
    with pytest.raises(RuntimeError, match="closed"):
        collection.count()
