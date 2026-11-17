"""SQLite evidence and vector store with versioned citations and fail-closed retrieval."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from .chunking import chunk_text
from .embedding_common import validate_vectors
from .ledger import Manifest
from .sqlite_index import SQLiteIndex
from .models import (
    COLLECTION_NAMES, DEFAULT_ROLE_BREADTHS, CitationNotFound, Document, EvidenceChunk,
    GroundingUnavailable, IngestResult, RagError, RetrievalContext,
)


class RagStore:
    def __init__(self, path: Path, embedder: object, *, chunk_size: int = 700,
                 chunk_overlap: int = 100, role_breadths: dict[str, int] | None = None):
        chunk_text("Configuration validation", chunk_size, chunk_overlap)
        policy = dict(DEFAULT_ROLE_BREADTHS)
        if role_breadths:
            if set(role_breadths) - set(DEFAULT_ROLE_BREADTHS):
                raise ValueError("Retrieval breadth may be configured only for known model roles")
            policy.update(role_breadths)
        if any(type(value) is not int or not 1 <= value <= 10 for value in policy.values()):
            raise ValueError("Every retrieval role requires between 1 and 10 results per populated collection")
        self._role_breadths = MappingProxyType(policy)
        self.embedder = embedder
        self.model_id = getattr(embedder, "model_id", None)
        self.dimensions = getattr(embedder, "dimensions", None)
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("Embedder must expose a non-empty model_id")
        if type(self.dimensions) is not int or self.dimensions < 1:
            raise ValueError("Embedder must expose a positive integer dimension count")
        self.path = Path(path).resolve()
        self.db_path = self.path if self.path.suffix in {".db", ".sqlite", ".sqlite3"} else self.path / "rag.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest = Manifest(self.db_path, self.model_id, self.dimensions)
        self.client = SQLiteIndex(self.db_path, self.dimensions)
        self._collections = {name: self.client.get_or_create_collection(name=name) for name in COLLECTION_NAMES}
        self.chunk_size, self.chunk_overlap = chunk_size, chunk_overlap
        self._closed = False

    @property
    def role_breadths(self) -> Mapping[str, int]:
        """A validated snapshot; caller mutations cannot widen or disable grounding retrieval."""
        return self._role_breadths

    def _ensure_open(self):
        if self._closed:
            raise RagError("The retrieval store is closed. Open a new store instance.")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = self.embedder.embed(texts)
            return validate_vectors(vectors, len(texts), self.dimensions)
        except Exception:
            raise RagError("Embedding failed. Check local model availability or explicitly configured "
                           "gateway embeddings; no ungrounded fallback was used.") from None

    @staticmethod
    def _evidence(citation_id: str, text: str, metadata: dict, distance=None) -> EvidenceChunk:
        return EvidenceChunk(citation_id=citation_id, text=text, distance=distance,
                             **{name: metadata[name] for name in ["source_id", "title", "collection", "version",
                                                                 "chunk_index", "start_char", "end_char"]},
                             source_uri=metadata.get("source_uri"))

    def ingest(self, document: Document) -> IngestResult:
        self._ensure_open()
        if not isinstance(document, Document):
            document = Document.model_validate(document)
        callback = getattr(self.embedder, "token_count", None)
        token_limit = getattr(self.embedder, "max_tokens", None)
        try:
            chunks = chunk_text(document.text, self.chunk_size, self.chunk_overlap,
                                token_count=callback, max_tokens=token_limit)
        except RagError:
            raise
        except Exception:
            raise RagError("Cannot chunk this document within the embedding model's token budget. "
                           "Check model availability and chunking settings.") from None
        content_hash = hashlib.sha256(document.text.encode()).hexdigest()
        version = document.version or content_hash
        key = hashlib.sha256(json.dumps([document.collection, document.source_id, version]).encode()).hexdigest()
        signature = hashlib.sha256(json.dumps({
            "text_hash": content_hash, "title": document.title, "source_uri": document.source_uri,
            "chunks": [(chunk.start_char, chunk.end_char) for chunk in chunks],
        }, sort_keys=True).encode()).hexdigest()
        ready, expected_active = self.manifest.prepare(
            document.collection, document.source_id, version, key, signature, len(chunks))
        changed = False
        if not ready:
            collection = self._collections[document.collection]
            for offset in range(0, len(chunks), 64):
                group = chunks[offset:offset + 64]
                ids = [f"rag:{document.collection}:{key}:{chunk.index}" for chunk in group]
                metadata = [{"document_key": key, "source_id": document.source_id, "version": version,
                             "title": document.title, "collection": document.collection,
                             "content_hash": content_hash, "chunk_index": chunk.index,
                             "start_char": chunk.start_char, "end_char": chunk.end_char,
                             **({"source_uri": document.source_uri} if document.source_uri is not None else {})}
                            for chunk in group]
                vectors = self._embed([chunk.text for chunk in group])
                try:
                    collection.upsert(ids=ids, documents=[chunk.text for chunk in group],
                                      metadatas=metadata, embeddings=vectors)
                    if set(collection.get(ids=ids, include=[])["ids"]) != set(ids):
                        raise ValueError("Incomplete chunk indexing")
                except Exception:
                    raise RagError("Document indexing failed before publication. The previous active "
                                   "version remains available; retry ingestion.") from None
            changed = self.manifest.publish(document.collection, document.source_id, version, expected_active)
        return IngestResult(source_id=document.source_id, collection=document.collection,
                            version=version, chunk_count=len(chunks),
                            corpus_version=self.manifest.revision(), changed=changed)

    def retrieve(self, query: str, role: str = "analyst") -> RetrievalContext:
        self._ensure_open()
        if not isinstance(query, str) or not query.strip():
            raise ValueError("A non-empty retrieval query is required")
        if role not in self.role_breadths:
            raise ValueError("Unknown retrieval role; use router, narrator, analyst, or strategist")
        revision, active = self.manifest.snapshot()
        if not any(active.values()):
            raise GroundingUnavailable("No published grounding documents exist. Ingest a policy or knowledge "
                                       "document before requesting grounded context.")
        vector = self._embed([query.strip()])
        chunks = []
        for name in COLLECTION_NAMES:
            documents = active[name]
            if not documents:
                continue
            keys = [item["document_key"] for item in documents]
            count = min(self.role_breadths[role], sum(item["chunk_count"] for item in documents))
            try:
                result = self._collections[name].query(query_embeddings=vector, n_results=count,
                                                        where={"document_key": {"$in": keys}},
                                                        include=["documents", "metadatas", "distances"])
                evidence = [self._evidence(identifier, text, metadata, distance) for identifier, text, metadata, distance in zip(
                    result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True)]
                if not evidence:
                    raise ValueError("The active manifest has no indexed evidence")
            except Exception:
                raise RagError("Published grounding evidence could not be read from the local index. "
                               "Repair or reindex the affected document; reasoning must not continue uncited.") from None
            chunks.extend(sorted(evidence, key=lambda item: (item.distance, item.citation_id)))
        return RetrievalContext(query=query.strip(), role=role, corpus_version=revision, chunks=chunks)

    def resolve_citation(self, citation_id: str) -> EvidenceChunk:
        self._ensure_open()
        parts = citation_id.split(":") if isinstance(citation_id, str) else []
        if len(parts) != 4 or parts[0] != "rag" or parts[1] not in COLLECTION_NAMES:
            raise CitationNotFound("The citation ID is not a known grounding source identifier")
        if not self.manifest.published(parts[2]):
            raise CitationNotFound("The citation does not belong to a published source version")
        try:
            result = self._collections[parts[1]].get(ids=[citation_id], include=["documents", "metadatas"])
            if not result["ids"]:
                raise ValueError("Missing chunk")
            return self._evidence(citation_id, result["documents"][0], result["metadatas"][0])
        except Exception:
            raise CitationNotFound("The citation does not resolve to stored immutable evidence") from None

    def collections(self) -> list[dict]:
        self._ensure_open()
        return self.manifest.statistics()

    def close(self):
        if not self._closed:
            self.client.close()
            self._closed = True

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, *_):
        self.close()
