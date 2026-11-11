"""Runtime grounding through HTTP, with real Chroma and offline deterministic vectors."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import math
import re
import threading
import time

from fastapi.testclient import TestClient
import httpx
import pytest

from platform_app.app import create_app
from platform_app.config import Settings
from platform_app.rag.store import RagStore


class Embedder:
    model_id = "http-test-bag-of-words-v1"
    dimensions = 8
    vocabulary = ("margin", "map", "competitor", "stock", "brand", "policy", "cost", "demand")

    def check(self):
        return {"available": True, "provider": "local", "detail": "Offline test model is ready."}

    def embed(self, texts):
        result = []
        for text in texts:
            words = re.findall(r"\w+", text.casefold())
            vector = [float(words.count(word)) + .01 for word in self.vocabulary]
            norm = math.sqrt(sum(value * value for value in vector))
            result.append([value / norm for value in vector])
        return result


@contextmanager
def application(directory, embedder=None, *, local_model=False):
    settings = Settings(data_dir=directory, commerce_url="http://commerce",
                        embedding_cache_dir=directory / "missing-model")
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, json={"status": "ok", "seeded": True}))
    factory = None if local_model else lambda config: RagStore(
        config.data_dir / "chroma", embedder or Embedder(),
        chunk_size=config.rag_chunk_size, chunk_overlap=config.rag_chunk_overlap)
    app = create_app(settings, commerce_transport=transport, rag_factory=factory)
    with TestClient(app) as client:
        yield client, app


def upload(client, text="Margin policy preserves cost recovery.", **fields):
    values = {"collection": "pricing_policy", "source_id": "margin-policy",
              "title": "Margin policy", "version": "v1", **fields}
    response = client.post("/api/grounding/uploads", data=values,
                           files={"file": ("policy.md", text.encode(), "text/markdown")})
    assert response.status_code == 202, response.text
    return response.json()


def complete(client, job):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        response = client.get(f"/api/grounding/uploads/{job['id']}")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in {"ready", "failed", "interrupted"}:
            return result
        time.sleep(.02)
    pytest.fail(f"Ingestion {job['id']} did not reach a terminal state within 12 seconds")


def retrieve(client, query="margin policy"):
    response = client.post("/api/grounding/retrieve", json={"query": query, "role": "analyst"})
    assert response.status_code == 200, response.text
    return response.json()


def test_uploaded_document_is_retrievable_in_same_app_with_current_collection_stats(tmp_path):
    with application(tmp_path) as (client, _):
        initial = client.get("/api/grounding/collections").json()
        assert {item["collection"] for item in initial["items"]} == {
            "pricing_policy", "market_intel", "product_kb", "user_uploads"}
        assert initial["corpus_version"] == 0
        assert all(item["document_count"] == item["chunk_count"] == 0 for item in initial["items"])
        assert all(item["last_updated"] is None for item in initial["items"])
        assert initial["embedding"]["available"] is True
        empty = client.post("/api/grounding/retrieve", json={"query": "margin"})
        assert empty.status_code == 409
        text = "Margin policy preserves cost recovery. " * 30
        job = complete(client, upload(client, text))
        assert job["status"] == "ready", job
        assert job["created_at"] and job["updated_at"] and job["completed_at"]
        assert job["result"]["chunk_count"] > 1
        current = client.get("/api/grounding/collections").json()
        policy = next(item for item in current["items"] if item["collection"] == "pricing_policy")
        assert policy["document_count"] == 1
        assert policy["chunk_count"] == job["result"]["chunk_count"]
        assert policy["last_updated"]
        context = retrieve(client)
        assert context["corpus_version"] == current["corpus_version"] == job["result"]["corpus_version"]
        for chunk in context["chunks"]:
            assert chunk["text"] == text[chunk["start_char"]:chunk["end_char"]]
            citation = client.get(f"/api/grounding/citations/{chunk['citation_id']}")
            assert citation.status_code == 200 and citation.json()["text"] == chunk["text"]


def test_replacement_changes_live_context_retains_old_citations_and_replay_is_idempotent(tmp_path):
    with application(tmp_path) as (client, _):
        first = complete(client, upload(client))
        assert first["status"] == "ready", first
        original = retrieve(client)["chunks"][0]
        text = "Revised margin policy now requires higher cost recovery."
        second = complete(client, upload(client, text, version="v2"))
        assert second["status"] == "ready", second
        assert second["result"]["corpus_version"] > first["result"]["corpus_version"]
        context = retrieve(client)
        assert context["corpus_version"] == second["result"]["corpus_version"]
        assert {chunk["version"] for chunk in context["chunks"]} == {"v2"}
        assert {chunk["text"] for chunk in context["chunks"]} == {text}
        archived = client.get(f"/api/grounding/citations/{original['citation_id']}")
        assert archived.status_code == 200 and archived.json()["text"] == original["text"]
        replay = complete(client, upload(client, text, version="v2"))
        assert replay["status"] == "ready" and replay["result"]["changed"] is False
        assert replay["result"]["corpus_version"] == second["result"]["corpus_version"]
        stats = client.get("/api/grounding/collections").json()["items"]
        assert sum(item["document_count"] for item in stats) == 1
        assert sum(item["chunk_count"] for item in stats) == second["result"]["chunk_count"]


def test_completed_upload_history_and_citations_survive_restart(tmp_path):
    with application(tmp_path) as (client, _):
        job = complete(client, upload(client))
        assert job["status"] == "ready", job
        context = retrieve(client)
    with application(tmp_path) as (client, _):
        assert client.get(f"/api/grounding/uploads/{job['id']}").json() == job
        assert job in client.get("/api/grounding/uploads").json()["items"]
        current = retrieve(client)
        assert current["corpus_version"] == context["corpus_version"]
        assert current["chunks"][0]["citation_id"] == context["chunks"][0]["citation_id"]


def test_unknown_ids_invalid_queries_and_roles_are_explicit(tmp_path):
    with application(tmp_path) as (client, _):
        assert client.get("/api/grounding/uploads/missing").status_code == 404
        assert client.get("/api/grounding/citations/missing").status_code == 404
        for payload in ({"query": ""}, {"query": " \n\t"}, {"query": 12},
                        {"query": "margin", "role": "execution"},
                        {"query": "margin", "credential": "DO-NOT-ECHO-346"}):
            response = client.post("/api/grounding/retrieve", json=payload)
            assert response.status_code == 422, response.text
            assert "DO-NOT-ECHO-346" not in response.text


def test_missing_local_model_fails_visibly_without_breaking_other_apis(tmp_path):
    with application(tmp_path, local_model=True) as (client, _):
        stats = client.get("/api/grounding/collections")
        assert stats.status_code == 200
        assert stats.json()["embedding"]["available"] is False
        job = complete(client, upload(client))
        assert job["status"] == "failed" and job["error_code"] and job["error"]
        assert "scripts.rag prepare" in job["error"]
        assert job["completed_at"] and job["result"] is None
        assert sum(item["document_count"] for item in client.get(
            "/api/grounding/collections").json()["items"]) == 0
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["capabilities"]["price_execution"] is True
        assert health.json()["capabilities"]["grounded_recommendations"] is False
        assert not (tmp_path / "missing-model").exists()


def test_health_remains_responsive_while_embedding_thread_is_busy(tmp_path):
    class BlockingEmbedder(Embedder):
        def __init__(self):
            self.entered, self.release = threading.Event(), threading.Event()

        def embed(self, texts):
            self.entered.set()
            if not self.release.wait(6):
                raise RuntimeError("Test worker timed out")
            return super().embed(texts)

    embedder = BlockingEmbedder()
    with application(tmp_path, embedder) as (client, _), ThreadPoolExecutor(max_workers=2) as pool:
        try:
            submitted = pool.submit(upload, client)
            job = submitted.result(timeout=2)
            assert embedder.entered.wait(3), "Upload never reached embedding worker"
            health = pool.submit(client.get, "/api/health").result(timeout=1)
            assert health.status_code == 200
            assert health.json()["capabilities"]["price_execution"] is True
            status = client.get(f"/api/grounding/uploads/{job['id']}").json()
            assert status["status"] == "indexing"
        finally:
            embedder.release.set()
        assert complete(client, job)["status"] == "ready"
