"""Bounded runtime ingestion, current-corpus retrieval, and lifespan-owned RAG workers."""

import asyncio
import hashlib
import threading
from collections.abc import Callable

from platform_app.config import Settings
from platform_app.rag.embedding_common import EmbeddingUnavailable
from platform_app.rag.models import (
    CitationNotFound, Document, DocumentConflict, EmbeddingMismatch, GroundingUnavailable, RagError,
)
from platform_app.storage import Store

from .jobs import UploadJobs
from .schemas import GroundingServiceError, LOCAL_PREPARE_COMMAND, LOCAL_UNAVAILABLE
from .worker import OwnedWorkers, drain


class GroundingService:
    """Initialize inside the app lifespan; the embedding engine stays lazy until requested."""

    max_pending = 8

    def __init__(self, settings_provider: Callable[[], Settings], store: Store, rag_factory=None):
        self.settings_provider, self.jobs = settings_provider, UploadJobs(store)
        self._factory = rag_factory
        self._loop = asyncio.get_running_loop()
        self._guard = threading.Lock()
        self._submissions = threading.Condition(self._guard)
        self._lock = asyncio.Lock()
        self._queue = asyncio.Queue()
        self._workers = OwnedWorkers()
        self._pending = 0
        self._submitting = 0
        self._stopping = False
        self._rag = self._signature = None
        self._embedding_available = None
        self._stop_task = None
        self._consumer = asyncio.create_task(self._consume())

    def submit(self, document: Document, filename: str) -> dict:
        """Thread-safe; callers may use to_thread to keep the SQLite write off the event loop."""
        settings = self.settings_provider().model_copy(deep=True)
        with self._guard:
            if self._stopping:
                raise GroundingServiceError("grounding_stopping", "Grounding service is stopping. Retry after restart.")
            if self._pending >= self.max_pending:
                raise GroundingServiceError("upload_queue_full", "The upload queue is full. Wait for an upload to finish.", 409)
            self._pending += 1
            self._submitting += 1
        try:
            item = self.jobs.create(document, filename)
            self._loop.call_soon_threadsafe(self._queue.put_nowait, (item["id"], document, settings))
            return item
        except Exception as error:
            with self._guard:
                self._pending -= 1
            raise self._failure(error, settings) from None
        finally:
            with self._submissions:
                self._submitting -= 1
                self._submissions.notify_all()

    def list_uploads(self, limit=25) -> list[dict]:
        return self.jobs.list(limit)

    def get_upload(self, job_id: str) -> dict | None:
        return self.jobs.get(job_id)

    @staticmethod
    def _settings_signature(settings: Settings) -> bytes:
        # Pydantic deliberately excludes api_key from dumps; include it only in this in-memory digest.
        secret = settings.api_key.get_secret_value() if settings.api_key else ""
        return hashlib.sha256((settings.model_dump_json() + "\0" + secret).encode()).digest()

    def _open(self, settings: Settings):
        signature = self._settings_signature(settings)
        if signature != self._signature:
            self._close()
            if self._factory is None:
                from platform_app.rag.factory import create_store
                factory = create_store
            else:
                factory = self._factory
            self._rag = factory(settings)
            self._signature = signature
        return self._rag

    def _close(self):
        previous, self._rag = self._rag, None
        self._signature = self._embedding_available = None
        if previous is not None:
            previous.close()

    def _embedding(self, rag, settings: Settings) -> dict:
        if settings.embedding_provider == "gateway":
            available = self._embedding_available
            detail = ("Gateway embeddings are explicitly enabled; availability is checked on actual use."
                      if available is None else "Gateway embeddings succeeded on the latest embedding operation."
                      if available else "Gateway embeddings failed. Check gateway access, model, and TLS settings.")
            return {"provider": "gateway", "available": available, "detail": detail}
        check = getattr(rag.embedder, "check", None)
        available = check().get("available") is True if check else True
        self._embedding_available = available
        return {"provider": "local", "available": available,
                "detail": "Verified local embedding model is ready." if available else LOCAL_UNAVAILABLE,
                **({"prepare_command": LOCAL_PREPARE_COMMAND} if not available else {})}

    def _require_embedding(self, rag, settings: Settings):
        if settings.embedding_provider == "local" and not self._embedding(rag, settings)["available"]:
            raise GroundingServiceError("embeddings_unavailable", LOCAL_UNAVAILABLE)

    @staticmethod
    def _failure(error: Exception, settings: Settings) -> GroundingServiceError:
        if isinstance(error, GroundingServiceError):
            return error
        if isinstance(error, DocumentConflict):
            return GroundingServiceError("document_conflict", "This source version already exists with different content or metadata. Use a new version.", 409)
        if isinstance(error, CitationNotFound):
            return GroundingServiceError("citation_not_found", "The citation does not resolve to published grounding evidence.", 404)
        if isinstance(error, GroundingUnavailable):
            return GroundingServiceError("grounding_unavailable", "No published grounding documents exist. Upload a document before retrieving context.", 409)
        if isinstance(error, EmbeddingMismatch):
            return GroundingServiceError("embedding_mismatch", "The configured embedding model does not match the existing index. Restore the original model or use a new data directory.")
        if isinstance(error, EmbeddingUnavailable):
            detail = LOCAL_UNAVAILABLE if settings.embedding_provider == "local" else \
                "Gateway embeddings are unavailable. Check explicit opt-in, gateway access, model, dimensions, and TLS settings."
            return GroundingServiceError("embeddings_unavailable", detail)
        if isinstance(error, RagError):
            return GroundingServiceError("grounding_failed", "Grounding indexing or retrieval failed. Check embedding availability and the local index. Failed uploads do not replace published evidence.")
        if isinstance(error, ValueError):
            return GroundingServiceError("invalid_grounding_request", "The grounding request is invalid. Check the query, role, and document metadata.", 422)
        return GroundingServiceError("grounding_failed", "Unexpected grounding failure. Check the local index and embedding configuration, then retry.")

    def _index(self, job_id: str, document: Document, settings: Settings):
        self.jobs.update(job_id, "indexing")
        try:
            rag = self._open(settings)
            self._require_embedding(rag, settings)
            result = rag.ingest(document)
            self._embedding_available = True
        except Exception as error:
            failure = self._failure(error, settings)
            self.jobs.update(job_id, "failed", error_code=failure.code, error=failure.detail)
        else:
            self.jobs.update(job_id, "ready", result=result.model_dump())

    def _interrupt(self, job_id: str):
        self.jobs.update(job_id, "interrupted", error_code="upload_interrupted",
                         error="Application stopped before ingestion started. Upload the file again to retry.")

    async def _consume(self):
        while True:
            work = await self._queue.get()
            if work is None:
                return
            job_id, document, settings = work
            try:
                async with self._lock:
                    if self._stopping:
                        await self._workers.run(self._interrupt, job_id)
                    else:
                        await self._workers.run(self._index, job_id, document, settings)
            finally:
                with self._guard:
                    self._pending -= 1

    async def _operation(self, function):
        settings = self.settings_provider().model_copy(deep=True)
        async with self._lock:
            if self._stopping:
                raise GroundingServiceError("grounding_stopping", "Grounding service is stopping. Retry after restart.")
            try:
                return await self._workers.run(function, settings)
            except Exception as error:
                raise self._failure(error, settings) from None

    def _collection_snapshot(self, settings: Settings) -> dict:
        rag = self._open(settings)
        items = rag.collections()
        embedding = self._embedding(rag, settings)
        return {"items": items, "corpus_version": max((item["corpus_version"] for item in items), default=0),
                "embedding": embedding, "status": "unavailable" if embedding["available"] is False else "ready"}

    async def collections(self) -> dict:
        try:
            return await self._operation(self._collection_snapshot)
        except GroundingServiceError as error:
            if error.code == "grounding_stopping":
                raise
            settings = self.settings_provider()
            return {"items": [], "corpus_version": None, "status": "unavailable", "detail": error.detail,
                    "embedding": {"provider": settings.embedding_provider, "available": False,
                                  "detail": error.detail}}

    async def retrieve(self, query: str, role="analyst"):
        def retrieve_current(settings):
            rag = self._open(settings)
            self._require_embedding(rag, settings)
            token_count = getattr(rag.embedder, "token_count", None)
            token_limit = getattr(rag.embedder, "max_tokens", None)
            if token_count and token_limit and token_count(query) > token_limit:
                raise GroundingServiceError("query_too_long", "The query exceeds the embedding model's token limit. Use a shorter query; text was not truncated.", 422)
            try:
                context = rag.retrieve(query, role=role)
            except RagError:
                self._embedding_available = None
                raise
            self._embedding_available = True
            return context
        return await self._operation(retrieve_current)

    async def citation(self, citation_id: str):
        return await self._operation(lambda settings: self._open(settings).resolve_citation(citation_id))

    def _wait_submissions(self):
        with self._submissions:
            self._submissions.wait_for(lambda: self._submitting == 0)

    async def _shutdown(self):
        with self._guard:
            self._stopping = True
        # SQLite may still be committing an accepted submit. Wait in an owned thread; its queue
        # callback is posted before notifying completion, hence before we append the sentinel.
        await self._workers.run(self._wait_submissions)
        self._queue.put_nowait(None)
        await self._consumer
        async with self._lock:
            await self._workers.run(self._close)

    async def stop(self):
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._shutdown())
        await drain(self._stop_task)
