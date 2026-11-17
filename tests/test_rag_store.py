"""Persistent SQLite integration uses deterministic test vectors, never downloaded models."""

import inspect
import json
import math
from pathlib import Path
import re
import subprocess
import sys

import pytest

from platform_app.rag.models import (
    CitationNotFound, Document, DocumentConflict, EmbeddingMismatch,
    GroundingUnavailable, RagError,
)
from platform_app.rag.store import RagStore


COLLECTIONS = {"pricing_policy", "market_intel", "product_kb", "user_uploads"}


class TestEmbedder:
    """Small semantic fixture; production never selects this embedding implementation."""

    __test__ = False
    model_id = "test-bag-of-words-v1"
    dimensions = 8
    vocabulary = ("margin", "map", "competitor", "stock", "brand", "policy", "cost", "demand")

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        result = []
        for text in texts:
            words = re.findall(r"\w+", text.casefold())
            vector = [float(words.count(word)) + .01 for word in self.vocabulary]
            norm = math.sqrt(sum(value * value for value in vector))
            result.append([value / norm for value in vector])
        return result


def document(text="The margin floor protects profit and cost recovery.", **changes):
    values = {"source_id": "margin-policy", "title": "Pricing policy", "text": text,
              "collection": "pricing_policy", "source_uri": "policy://margin-policy"}
    values.update(changes)
    return Document(**values)


@pytest.fixture
def make_store(tmp_path):
    opened = []

    def create(**kwargs):
        store = RagStore(tmp_path / "rag.db", kwargs.pop("embedder", TestEmbedder()), **kwargs)
        opened.append(store)
        return store

    yield create
    for store in reversed(opened):
        store.close()


def test_four_collections_are_persistent_and_return_citable_source_evidence(make_store):
    store = make_store()
    assert len(store.collections()) == 4
    for collection in sorted(COLLECTIONS):
        store.ingest(document(collection=collection, source_id=f"source-{collection}"))
    context = store.retrieve("margin policy", role="router")
    assert {chunk.collection for chunk in context.chunks} == COLLECTIONS
    assert len(context.chunks) == 4  # A breadth of one applies to every populated collection.
    for chunk in context.chunks:
        assert chunk.citation_id and chunk.version and chunk.title
        assert chunk.source_uri == "policy://margin-policy"
        assert chunk.text == document().text[chunk.start_char:chunk.end_char]
        assert chunk.distance is not None and math.isfinite(chunk.distance)
        resolved = store.resolve_citation(chunk.citation_id)
        assert resolved.text == chunk.text and resolved.source_id == chunk.source_id
    store.close()
    restarted = make_store()
    assert restarted.retrieve("margin policy").corpus_version == context.corpus_version
    assert restarted.resolve_citation(context.chunks[0].citation_id).text == context.chunks[0].text


def test_unchanged_ingestion_is_idempotent_and_does_not_advance_corpus(make_store):
    store = make_store()
    first = store.ingest(document())
    first_context = store.retrieve("margin")
    repeated = store.ingest(document())
    assert first.changed is True and repeated.changed is False
    assert first.chunk_count == repeated.chunk_count == 1
    assert repeated.version == first.version
    assert repeated.corpus_version == first.corpus_version
    assert [chunk.citation_id for chunk in store.retrieve("margin").chunks] == [
        chunk.citation_id for chunk in first_context.chunks]


def test_published_citation_survives_a_fresh_python_process(make_store, tmp_path):
    store = make_store()
    store.ingest(document(version="v1"))
    citation = store.retrieve("margin").chunks[0]
    store.close()
    code = """
import json, runpy, sys
from pathlib import Path
from platform_app.rag.store import RagStore
helper = runpy.run_path(sys.argv[1])
store = RagStore(Path(sys.argv[2]), helper['TestEmbedder']())
try:
    chunk = store.resolve_citation(sys.argv[3])
    print(json.dumps({'text': chunk.text, 'version': chunk.version,
                      'citations': [item.citation_id for item in store.retrieve('margin').chunks]}))
finally:
    store.close()
"""
    result = subprocess.run([sys.executable, "-c", code, str(Path(__file__).resolve()),
                             str(tmp_path / "rag.db"), citation.citation_id],
                            capture_output=True, text=True, check=True, timeout=20)
    output = json.loads(result.stdout)
    assert output["text"] == citation.text and output["version"] == "v1"
    assert citation.citation_id in output["citations"]


@pytest.mark.parametrize("replacement", [
    {"text": "The margin floor is now different."},
    {"title": "A different attribution"},
    {"source_uri": "policy://different-attribution"},
])
def test_explicit_versions_are_immutable_and_conflict_does_not_change_active_evidence(make_store,
                                                                                     replacement):
    store = make_store()
    first = store.ingest(document(version="v1"))
    with pytest.raises(DocumentConflict):
        store.ingest(document(version="v1", **replacement))
    context = store.retrieve("margin")
    assert context.corpus_version == first.corpus_version
    assert {chunk.text for chunk in context.chunks} == {document().text}


def test_new_version_replaces_active_retrieval_but_keeps_old_citations_resolvable(make_store):
    store = make_store()
    first = store.ingest(document(version="v1"))
    original = store.retrieve("margin").chunks[0]
    updated = "Updated margin policy: every price must preserve the revised floor."
    second = store.ingest(document(updated, version="v2"))
    assert second.corpus_version != first.corpus_version
    current = store.retrieve("margin").chunks
    assert {chunk.version for chunk in current} == {"v2"}
    assert {chunk.text for chunk in current} == {updated}
    assert current[0].citation_id != original.citation_id
    assert store.resolve_citation(original.citation_id).text == document().text
    # Repeating an archived import must not silently roll the policy back.
    archived = store.ingest(document(version="v1"))
    assert archived.changed is False
    assert {chunk.version for chunk in store.retrieve("margin").chunks} == {"v2"}
    store.close()
    restarted = make_store()
    assert restarted.resolve_citation(original.citation_id).version == "v1"
    assert {chunk.version for chunk in restarted.retrieve("margin").chunks} == {"v2"}


def test_source_ids_are_scoped_by_collection(make_store):
    store = make_store()
    store.ingest(document(source_id="shared-source", version="v1"))
    store.ingest(document("Competitor margin and demand research.", collection="market_intel",
                          source_id="shared-source", version="v1"))
    chunks = store.retrieve("margin").chunks
    assert len(chunks) == 2
    assert len({chunk.citation_id for chunk in chunks}) == 2
    assert {store.resolve_citation(chunk.citation_id).collection for chunk in chunks} == {
        "pricing_policy", "market_intel"}


def test_role_breadth_changes_context_without_omitting_populated_mandatory_collections(make_store):
    store = make_store(role_breadths={"router": 1, "analyst": 2})
    for collection in ("pricing_policy", "user_uploads"):
        for index in range(4):
            store.ingest(document(f"Margin policy paragraph {index}.", collection=collection,
                                  source_id=f"policy-{index}"))
    narrow = store.retrieve("margin", role="router")
    wide = store.retrieve("margin", role="analyst")
    assert len(narrow.chunks) == 2 and len(wide.chunks) == 4
    assert {chunk.collection for chunk in narrow.chunks} == {"pricing_policy", "user_uploads"}


def test_validated_role_policy_cannot_be_mutated_to_add_roles_or_unbounded_context(make_store):
    supplied = {"router": 1}
    store = make_store(role_breadths=supplied)
    store.ingest(document())
    supplied["router"] = 100
    supplied["execution"] = 1
    assert store.role_breadths["router"] == 1 and "execution" not in store.role_breadths
    for role, value in (("router", 100), ("execution", 1)):
        with pytest.raises(TypeError):
            store.role_breadths[role] = value
    with pytest.raises(AttributeError):
        store.role_breadths = {"execution": 1}
    with pytest.raises(ValueError):
        store.retrieve("margin", role="execution")
    assert len(store.retrieve("margin", role="router").chunks) == 1


@pytest.mark.parametrize("breadth", [0, -1, 11])
def test_zero_or_unbounded_role_breadth_cannot_disable_grounding(make_store, breadth):
    with pytest.raises(ValueError):
        make_store(role_breadths={"analyst": breadth})


def test_missing_context_and_invalid_queries_fail_explicitly(make_store):
    store = make_store()
    with pytest.raises(GroundingUnavailable):
        store.retrieve("margin")
    store.ingest(document())
    for query in ("", " \n\t"):
        with pytest.raises(ValueError):
            store.retrieve(query)
    with pytest.raises(ValueError):
        store.retrieve("margin", role="execution")
    with pytest.raises(CitationNotFound):
        store.resolve_citation("does-not-exist")


@pytest.mark.parametrize("change", ["model", "dimensions"])
def test_reopening_with_incompatible_embeddings_fails_before_vector_reuse(make_store, change):
    store = make_store()
    store.ingest(document())
    store.close()
    incompatible = TestEmbedder()
    if change == "model":
        incompatible.model_id = "different-embedding-model"
    else:
        incompatible.dimensions = 16
    with pytest.raises(EmbeddingMismatch):
        make_store(embedder=incompatible)
    assert {chunk.text for chunk in make_store().retrieve("margin").chunks} == {document().text}


def test_failed_embedding_cannot_replace_ready_version(make_store):
    embedder = TestEmbedder()
    store = make_store(embedder=embedder)
    first = store.ingest(document(version="v1"))
    original_embed = embedder.embed

    def fail(_texts):
        raise RuntimeError("Simulated embedding service outage")

    embedder.embed = fail
    with pytest.raises(RagError):
        store.ingest(document("New margin policy must remain unpublished.", version="v2"))
    embedder.embed = original_embed
    context = store.retrieve("margin")
    assert context.corpus_version == first.corpus_version
    assert {chunk.version for chunk in context.chunks} == {"v1"}


@pytest.mark.parametrize("vectors", [
    [[0.0] * 8], [[True] * 8], [["0.5"] * 8],
    [[float("nan")] * 8], [[1.0] * 7], [],
])
def test_invalid_injected_embedding_vectors_never_publish_grounding(make_store, vectors):
    embedder = TestEmbedder()
    valid_embed = embedder.embed
    embedder.embed = lambda texts: vectors
    store = make_store(embedder=embedder)
    with pytest.raises(RagError):
        store.ingest(document(version="v1"))
    assert all(item["document_count"] == 0 for item in store.collections())
    with pytest.raises(GroundingUnavailable):
        store.retrieve("margin")
    embedder.embed = valid_embed
    assert store.ingest(document(version="v1")).changed is True
    assert store.retrieve("margin").chunks[0].version == "v1"


def test_partial_sqlite_write_is_not_published_and_retry_can_finish(make_store, monkeypatch):
    from platform_app.rag.sqlite_index import SQLiteCollection as Collection

    store = make_store(chunk_size=90, chunk_overlap=15)
    first = store.ingest(document(version="v1"))
    original_upsert = Collection.upsert

    def interrupted_upsert(collection, *args, **kwargs):
        if collection.name == "pricing_policy":
            bound = inspect.signature(original_upsert).bind(collection, *args, **kwargs)
            fields = {name: value for name, value in bound.arguments.items() if name != "self"}
            partial = {name: values[:1] if isinstance(values, list) else values
                       for name, values in fields.items()}
            original_upsert(collection, **partial)
            raise RuntimeError("Simulated interruption after one vector was written")
        return original_upsert(collection, *args, **kwargs)

    replacement = document("New margin policy and cost controls. " * 12, version="v2")
    with monkeypatch.context() as patch:
        patch.setattr(Collection, "upsert", interrupted_upsert)
        with pytest.raises(RagError):
            store.ingest(replacement)
    context = store.retrieve("margin")
    assert context.corpus_version == first.corpus_version
    assert {chunk.version for chunk in context.chunks} == {"v1"}
    retried = store.ingest(replacement)
    assert retried.changed is True and retried.chunk_count > 1
    assert {chunk.version for chunk in store.retrieve("margin").chunks} == {"v2"}
