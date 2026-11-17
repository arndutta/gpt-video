"""Measure warmed grounded-cache stages with real local retrieval and a model fixture.

Uses fresh temporary storage and the already prepared local MiniLM cache. It never
downloads a model, contacts a gateway, or changes the running application's data.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import tempfile
import time

import numpy as np

from platform_app.config import Settings
from platform_app.llm import GroundedLLM
from platform_app.rag.factory import create_store
from platform_app.rag.models import Document
from platform_app.telemetry import Telemetry
from scripts.benchmark import BenchExplanation, ModelFixture


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("platform_app/llm/cache.py", "platform_app/llm/runtime.py",
           "platform_app/rag/store.py", "platform_app/rag/local_embeddings.py",
           "scripts/cache_benchmark.py")


def source_digest():
    result = hashlib.sha256()
    for name in SOURCES:
        result.update(name.encode() + b"\0" + (ROOT / name).read_bytes() + b"\0")
    return result.hexdigest()


def summarize(values):
    return {"samples": len(values), "median_ms": round(statistics.median(values), 3),
            "p95_ms": round(float(np.quantile(values, .95)), 3),
            "max_ms": round(max(values), 3)}


async def benchmark(samples, model_cache):
    phases = {"retrieval": [], "cache_lookup": [], "total": []}
    source_before = source_digest()
    with tempfile.TemporaryDirectory(prefix="pricing-cache-benchmark-") as temporary:
        directory = Path(temporary)
        settings = Settings(data_dir=directory, embedding_cache_dir=model_cache.resolve())
        rag = create_store(settings)
        telemetry = llm = None
        try:
            if not rag.embedder.check()["available"]:
                raise RuntimeError("Prepare the local MiniLM cache before this real-retrieval benchmark.")
            await asyncio.to_thread(rag.ingest, Document(
                source_id="cache-benchmark-policy", title="Public synthetic cache policy",
                collection="pricing_policy", version="v1",
                text="Synthetic pricing requires margin compliance, uncertainty disclosure and human review."))

            class Grounding:
                async def retrieve(self, query, role):
                    started = time.perf_counter()
                    try:
                        return await asyncio.to_thread(rag.retrieve, query, role=role)
                    finally:
                        phases["retrieval"].append((time.perf_counter() - started) * 1000)

            telemetry = Telemetry(directory)
            llm = GroundedLLM(lambda: settings, Grounding(), telemetry, directory, lambda *_: ModelFixture())
            original_lookup = llm.cache.get

            def lookup(keys):
                started = time.perf_counter()
                try:
                    return original_lookup(keys)
                finally:
                    phases["cache_lookup"].append((time.perf_counter() - started) * 1000)

            llm.cache.get = lookup
            queries = ("Explain synthetic pricing.", "  EXPLAIN  synthetic pricing. ")
            # Warm both embeddings; all measured calls still retrieve the current manifest/evidence.
            for query in queries:
                await llm.generate(BenchExplanation, role="analyst", query=query, facts={"price": "10.00"})
            before = llm.snapshot()["cache"]
            for values in phases.values():
                values.clear()
            for index in range(samples):
                started = time.perf_counter()
                await llm.generate(BenchExplanation, role="analyst", query=queries[index % 2], facts={"price": "10.00"})
                phases["total"].append((time.perf_counter() - started) * 1000)
            after = llm.snapshot()["cache"]
            calls = {key: after[key] - before[key] for key in ("exact_hits", "semantic_hits", "misses", "hits")}
            source_after = source_digest()
            return {"status": "measured", "timestamp": datetime.now(timezone.utc).isoformat(),
                    "mode": "real_local_MiniLM_SQLite_RAG_with_explicit_model_fixture",
                    "hardware": {"platform": platform.platform(), "python": platform.python_version()},
                    "workload": {"samples": samples, "warmup_calls": len(queries),
                                 "repeated_equivalent_context": True, "concurrent_load": "not imposed by this runner"},
                    "phases": {key: summarize(values) for key, values in phases.items()},
                    "measured_cache_calls": calls,
                    "sampled_max_under_100ms": max(phases["total"]) < 100,
                    "source_sha256": source_after, "source_changed_during_run": source_before != source_after,
                    "isolation": {"temporary_storage": True, "live_gateway_requests": 0, "live_price_writes": 0},
                    "limitations": ["Warmed equivalent-context workload; hit ratio is not an operational traffic estimate.",
                                    "No real model-generation latency or post-repair validity measurement.",
                                    "Other system load is uncontrolled; passing samples do not guarantee every future hit is below 100ms."]}
        finally:
            if llm:
                await llm.close()
            if telemetry:
                telemetry.close()
            await asyncio.to_thread(rag.close)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--local-model-cache", type=Path, default=ROOT / "data/models")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 20 <= args.samples <= 10000:
        parser.error("--samples must be between 20 and 10000")
    try:
        report = asyncio.run(benchmark(args.samples, args.local_model_cache))
    except Exception:
        print(json.dumps({"status": "failed", "detail": "Real local cache benchmark could not complete. Check the prepared model and local storage; no retrieval fixture was substituted."}))
        return 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return int(report["source_changed_during_run"])


if __name__ == "__main__":
    raise SystemExit(main())
