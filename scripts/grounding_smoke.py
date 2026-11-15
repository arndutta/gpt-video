"""Exercise runtime upload, published statistics, and immediate citable retrieval."""

import argparse
import json
from pathlib import Path
import time

import httpx


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, default=Path("data/grounding_smoke_result.json"))
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.base_url, timeout=60, trust_env=False) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        assert health.json()["commerce"]["status"] == "ok"
        before = client.get("/api/grounding/collections")
        before.raise_for_status()
        before = before.json()
        assert before["embedding"]["available"] is True, before["embedding"]["detail"]
        path = Path("examples/pricing-policy.md")
        started = time.perf_counter()
        with path.open("rb") as content:
            response = client.post("/api/grounding/uploads", files={
                "file": (path.name, content, "text/markdown")}, data={
                "collection": "user_uploads", "source_id": "runtime-demo-policy",
                "title": "Runtime upload example", "version": "demo-v1"})
        response.raise_for_status()
        job = response.json()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = client.get(f"/api/grounding/uploads/{job['id']}")
            response.raise_for_status()
            job = response.json()
            if job["status"] in {"ready", "failed", "interrupted"}:
                break
            time.sleep(.2)
        assert job["status"] == "ready", job.get("error", "Upload timed out")
        current = client.get("/api/grounding/collections")
        current.raise_for_status()
        current = current.json()
        assert current["corpus_version"] == job["result"]["corpus_version"]
        uploaded = next(item for item in current["items"] if item["collection"] == "user_uploads")
        assert uploaded["document_count"] >= 1 and uploaded["chunk_count"] >= 1 and uploaded["last_updated"]
        result = client.post("/api/grounding/retrieve", json={
            "query": "What minimum margin and maximum price change apply?", "role": "strategist"})
        result.raise_for_status()
        context = result.json()
        assert context["corpus_version"] == current["corpus_version"]
        chunks = [chunk for chunk in context["chunks"] if chunk["source_id"] == "runtime-demo-policy"]
        assert chunks, "New upload was not retrievable in the running app"
        citation = client.get("/api/grounding/citations/" + chunks[0]["citation_id"])
        citation.raise_for_status()
        assert citation.json()["text"] == chunks[0]["text"]
        report = {"status": "passed", "job_id": job["id"], "job_status": job["status"],
                  "corpus_version_before": before["corpus_version"],
                  "corpus_version_after": current["corpus_version"],
                  "published_new_version": job["result"]["changed"],
                  "upload_and_retrieval_seconds": round(time.perf_counter() - started, 3),
                  "retrievable_without_restart": True, "citation_resolves": True,
                  "browser_visual_qa": "unverified"}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return report


if __name__ == "__main__":
    main()
