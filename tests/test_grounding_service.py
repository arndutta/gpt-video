"""Runtime grounding uses real SQLite publication and deterministic offline test vectors."""

import asyncio
import inspect
import threading

import pytest

from platform_app.config import Settings
from platform_app.grounding.jobs import UploadJobs
from platform_app.grounding.schemas import GroundingServiceError
from platform_app.grounding.service import GroundingService
from platform_app.rag.models import Document
from platform_app.rag.store import RagStore
from platform_app.storage import Store


class Embedder:
    model_id, dimensions = "runtime-test-v1", 8

    def __init__(self):
        self.available = True
        self.started = threading.Event()
        self.release = None

    def check(self):
        return {"available": self.available}

    def embed(self, texts):
        self.started.set()
        if self.release is not None:
            assert self.release.wait(10), "Test did not release its embedding worker"
        return [[1.0, .2, .3, .4, .5, .6, .7, .8] for _ in texts]


def document(text="Margin policy protects cost recovery.", **changes):
    return Document(**{"source_id": "upload-policy", "title": "Uploaded policy", "text": text,
                       "collection": "user_uploads", **changes})


def setup_service(tmp_path, embedder=None):
    settings, store = Settings(data_dir=tmp_path), Store(tmp_path)
    engine = embedder or Embedder()
    opened = []

    def factory(current):
        rag = RagStore(current.data_dir / "rag.db", engine, chunk_size=90, chunk_overlap=15)
        opened.append(rag)
        return rag

    service = GroundingService(lambda: settings, store, factory)
    return service, engine, opened, store


async def wait_job(service, job_id):
    async with asyncio.timeout(10):
        while True:
            item = await asyncio.to_thread(service.get_upload, job_id)
            if item["status"] not in {"queued", "indexing"}:
                return item
            await asyncio.sleep(.01)


@pytest.mark.asyncio
async def test_upload_is_retrievable_immediately_and_statistics_match_published_version(tmp_path):
    service, _, opened, store = setup_service(tmp_path)
    try:
        assert not opened  # Application startup has not opened SQLite or loaded a model.
        queued = await asyncio.to_thread(service.submit, document(version="v1"), "policy.md")
        assert queued["status"] == "queued" and queued["result"] is None
        ready = await wait_job(service, queued["id"])
        assert ready["status"] == "ready" and ready["completed_at"]
        assert ready["error_code"] is None and ready["error"] is None
        context = await service.retrieve("margin policy")
        assert context.chunks[0].version == "v1"
        assert context.corpus_version == ready["result"]["corpus_version"]
        assert (await service.citation(context.chunks[0].citation_id)).text == document().text
        stats = await service.collections()
        uploads = next(item for item in stats["items"] if item["collection"] == "user_uploads")
        assert uploads["document_count"] == uploads["chunk_count"] == 1
        assert uploads["last_updated"] and stats["corpus_version"] == context.corpus_version
        assert len(opened) == 1
        details = [event["detail"] for event in store.list_audit()]
        assert document().text not in str(details)
        assert {event["action"] for event in store.list_audit()} >= {
            "grounding_upload_queued", "grounding_upload_indexing", "grounding_upload_ready"}
    finally:
        await service.stop()
    restarted = GroundingService(lambda: Settings(data_dir=tmp_path), Store(tmp_path))
    try:
        assert restarted.get_upload(ready["id"])["result"] == ready["result"]
    finally:
        await restarted.stop()


@pytest.mark.asyncio
async def test_partial_replacement_failure_is_visible_and_preserves_active_context(tmp_path, monkeypatch):
    from platform_app.rag.sqlite_index import SQLiteCollection as Collection

    service, _, _, _ = setup_service(tmp_path)
    try:
        first = service.submit(document(version="v1"), "policy.md")
        initial = await wait_job(service, first["id"])
        original = Collection.upsert

        def partial_write(collection, *args, **kwargs):
            bound = inspect.signature(original).bind(collection, *args, **kwargs)
            fields = {key: value for key, value in bound.arguments.items() if key != "self"}
            original(collection, **{key: values[:1] if isinstance(values, list) else values
                                    for key, values in fields.items()})
            raise RuntimeError("Secret document content must never escape")

        with monkeypatch.context() as patch:
            patch.setattr(Collection, "upsert", partial_write)
            replacement = service.submit(document("New margin policy. " * 25, version="v2"), "policy.md")
            failed = await wait_job(service, replacement["id"])
        assert failed["status"] == "failed" and failed["completed_at"]
        assert failed["result"] is None and failed["error_code"] == "grounding_failed"
        assert "Secret document" not in str(failed)
        context = await service.retrieve("margin")
        assert {chunk.version for chunk in context.chunks} == {"v1"}
        assert context.corpus_version == initial["result"]["corpus_version"]
        retry = service.submit(document("New margin policy. " * 25, version="v2"), "policy.md")
        ready = await wait_job(service, retry["id"])
        assert ready["status"] == "ready"
        assert (await service.retrieve("margin")).corpus_version > context.corpus_version
        assert {chunk.version for chunk in (await service.retrieve("margin")).chunks} == {"v2"}
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_missing_model_is_actionable_and_counts_still_available(tmp_path):
    settings = Settings(data_dir=tmp_path)
    service = GroundingService(lambda: settings, Store(tmp_path))
    try:
        job = service.submit(document(), "policy.md")
        failed = await wait_job(service, job["id"])
        assert failed["status"] == "failed" and failed["error_code"] == "embeddings_unavailable"
        assert "scripts.rag prepare" in failed["error"]
        stats = await service.collections()
        assert stats["status"] == "unavailable" and stats["embedding"]["available"] is False
        assert len(stats["items"]) == 4 and all(item["document_count"] == 0 for item in stats["items"])
        assert not settings.embedding_path.exists()  # Inference never invokes a downloader.
    finally:
        await service.stop()


def test_restart_marks_abandoned_uploads_interrupted_without_resubmitting_text(tmp_path):
    store = Store(tmp_path)
    jobs = UploadJobs(store)
    queued = jobs.create(document("Never persist this document body."), "queued.md")
    indexing = jobs.create(document(), "indexing.md")
    jobs.update(indexing["id"], "indexing")
    restarted = UploadJobs(store)
    for job_id in (queued["id"], indexing["id"]):
        item = restarted.get(job_id)
        assert item["status"] == "interrupted" and item["completed_at"]
        assert item["error_code"] == "upload_interrupted"
        assert "text" not in item
    assert b"Never persist this document body." not in store.path.read_bytes()


@pytest.mark.asyncio
async def test_worker_does_not_block_loop_and_shutdown_finishes_active_but_interrupts_queued(tmp_path):
    embedder = Embedder()
    embedder.release = threading.Event()
    service, _, opened, _ = setup_service(tmp_path, embedder)
    first = await asyncio.to_thread(service.submit, document(version="v1"), "first.md")
    second = await asyncio.to_thread(service.submit, document(source_id="queued"), "second.md")
    assert await asyncio.to_thread(embedder.started.wait, 5)
    # Event-loop work is still responsive while the embedding worker is blocked.
    await asyncio.wait_for(asyncio.sleep(.01), .2)
    stop = asyncio.create_task(service.stop())
    await asyncio.sleep(.02)
    assert not stop.done() and not opened[0]._closed
    embedder.release.set()
    await stop
    assert service.get_upload(first["id"])["status"] == "ready"
    assert service.get_upload(second["id"])["status"] == "interrupted"
    assert opened[0]._closed
    with pytest.raises(GroundingServiceError, match="stopping"):
        service.submit(document(), "late.md")


@pytest.mark.asyncio
async def test_repeated_request_cancellation_drains_worker_before_releasing_store(tmp_path):
    service, embedder, opened, _ = setup_service(tmp_path)
    try:
        first = service.submit(document(), "policy.md")
        await wait_job(service, first["id"])
        embedder.started.clear()
        embedder.release = threading.Event()
        query = asyncio.create_task(service.retrieve("margin"))
        assert await asyncio.to_thread(embedder.started.wait, 5)
        query.cancel()
        await asyncio.sleep(.01)
        query.cancel()
        stats = asyncio.create_task(service.collections())
        await asyncio.sleep(.02)
        assert not query.done() and not stats.done() and not opened[0]._closed
        embedder.release.set()
        with pytest.raises(asyncio.CancelledError):
            await query
        assert (await stats)["corpus_version"] == 1
    finally:
        if embedder.release:
            embedder.release.set()
        await service.stop()


@pytest.mark.asyncio
async def test_gateway_stats_never_probe_and_key_changes_replace_cached_store(tmp_path):
    current = Settings(data_dir=tmp_path, embedding_provider="gateway", allow_gateway_embeddings=True,
                       gateway_url="https://gateway.example/v1", api_key="first-secret")
    embedder, created_keys, opened = Embedder(), [], []

    def forbidden_probe():
        pytest.fail("Collection statistics must never issue a gateway embedding probe")

    embedder.check = forbidden_probe

    def factory(settings):
        created_keys.append(settings.api_key.get_secret_value())
        rag = RagStore(settings.data_dir / "rag.db", embedder)
        opened.append(rag)
        return rag

    service = GroundingService(lambda: current, Store(tmp_path), factory)
    try:
        assert (await service.collections())["embedding"]["available"] is None
        current = current.model_copy(update={"api_key": Settings(api_key="second-secret").api_key})
        assert (await service.collections())["embedding"]["available"] is None
        assert created_keys == ["first-secret", "second-secret"] and opened[0]._closed
        item = service.submit(document(), "policy.md")
        assert (await wait_job(service, item["id"]))["status"] == "ready"
        assert (await service.collections())["embedding"]["available"] is True
        assert "secret" not in str(service.list_uploads())
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_upload_queue_is_bounded(tmp_path):
    service, _, _, _ = setup_service(tmp_path)
    try:
        items = [service.submit(document(source_id=f"upload-{index}"), "policy.md")
                 for index in range(service.max_pending)]
        with pytest.raises(GroundingServiceError) as error:
            service.submit(document(), "excess.md")
        assert error.value.code == "upload_queue_full" and error.value.status_code == 409
        assert len(service.list_uploads()) == len(items)
    finally:
        await service.stop()
    assert all(item["status"] == "interrupted" for item in service.list_uploads())


@pytest.mark.asyncio
async def test_shutdown_waits_for_a_submitting_thread_without_blocking_the_loop(tmp_path, monkeypatch):
    service, _, opened, _ = setup_service(tmp_path)
    started, release = threading.Event(), threading.Event()
    original = service.jobs.create

    def slow_commit(*args):
        started.set()
        assert release.wait(10)
        return original(*args)

    monkeypatch.setattr(service.jobs, "create", slow_commit)
    submit = asyncio.create_task(asyncio.to_thread(service.submit, document(), "policy.md"))
    assert await asyncio.to_thread(started.wait, 5)
    stop = asyncio.create_task(service.stop())
    try:
        await asyncio.wait_for(asyncio.sleep(.02), .2)
        assert not stop.done()
    finally:
        release.set()
        item = await submit
        await stop
    assert service.get_upload(item["id"])["status"] == "interrupted"
    assert not opened and service._pending == 0


@pytest.mark.asyncio
async def test_unknown_provider_failures_never_echo_documents_or_credentials(tmp_path):
    settings = Settings(data_dir=tmp_path)

    def broken_factory(_):
        raise RuntimeError("sensitive-api-key and confidential uploaded body")

    service = GroundingService(lambda: settings, Store(tmp_path), broken_factory)
    try:
        item = service.submit(document(), "policy.md")
        failed = await wait_job(service, item["id"])
        assert failed["status"] == "failed" and failed["error_code"] == "grounding_failed"
        stats = await service.collections()
        with pytest.raises(GroundingServiceError) as error:
            await service.retrieve("margin")
        assert "sensitive" not in str((failed, stats, error.value.detail))
        assert "confidential" not in str((failed, stats, error.value.detail))
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_cancelled_shutdown_still_drains_and_records_actual_ingestion_outcome(tmp_path):
    embedder = Embedder()
    embedder.release = threading.Event()
    service, _, opened, _ = setup_service(tmp_path, embedder)
    item = service.submit(document(), "policy.md")
    assert await asyncio.to_thread(embedder.started.wait, 5)
    stop = asyncio.create_task(service.stop())
    # Let stop start before cancellation so this exercises cancellation of the drain.
    await asyncio.sleep(.01)
    stop.cancel()
    await asyncio.sleep(.01)
    stop.cancel()
    assert not opened[0]._closed
    embedder.release.set()
    with pytest.raises(asyncio.CancelledError):
        await stop
    await service.stop()
    assert service.get_upload(item["id"])["status"] == "ready" and opened[0]._closed


@pytest.mark.asyncio
async def test_over_token_query_is_rejected_without_truncating_or_embedding(tmp_path):
    service, embedder, _, _ = setup_service(tmp_path)
    embedder.max_tokens, embedder.token_count = 2, lambda text: len(text.split())
    try:
        embedder.started.clear()
        with pytest.raises(GroundingServiceError) as error:
            await service.retrieve("query is too long")
        assert error.value.code == "query_too_long" and error.value.status_code == 422
        assert not embedder.started.is_set()
    finally:
        await service.stop()
