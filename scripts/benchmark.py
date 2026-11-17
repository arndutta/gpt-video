"""Reproducible 500-SKU numerical and local-cache measurements; never changes live data."""

import argparse
import asyncio
from datetime import date, datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time

import httpx
from langchain_core.messages import AIMessage
import numpy as np
from pydantic import BaseModel, Field

from commerce.app import create_app as create_commerce
from commerce.evaluation import read_evaluation_truth
from commerce.seed import seed_database
from platform_app.commerce_client import CommerceClient, read_competitors
from platform_app.config import Settings
from platform_app.config import RunRequest
from platform_app.llm import GroundedLLM
from platform_app.rag.factory import create_store
from platform_app.rag.models import Document, EvidenceChunk, RetrievalContext
from platform_app.telemetry import Telemetry
from platform_app.tools import analyze_catalog, simulate_sku
from platform_app.tools.optimization import feasible_prices
import platform_app.tools.analysis as analysis_module
from scripts.benchmark_metrics import evaluate
from scripts.runtime import node_runtime


class BenchExplanation(BaseModel):
    rationale: str
    citations: list[str] = Field(min_length=1)


class ModelFixture:
    def with_structured_output(self, schema, **_options):
        class Chain:
            async def ainvoke(self, messages, **_kwargs):
                payload = json.loads(messages[1][1])
                citation = payload["evidence"][0]["citation_id"]
                if "recommendations" in schema.model_fields:
                    values = {"recommendations": [{"sku": i["sku"], "rationale": "Deterministic benchmark fixture explanation.",
                                                    "citations": [citation]} for i in payload["facts"]["recommendations"]],
                              "citations": [citation]}
                elif "interpretation" in schema.model_fields:
                    values = {"interpretation": "Deterministic benchmark fixture explanation.", "citations": [citation]}
                else:
                    values = {"rationale": "Deterministic benchmark fixture explanation.", "citations": [citation]}
                return {"parsed": schema(**values),
                        "raw": AIMessage(content=""), "parsing_error": None}
        return Chain()


class GroundingFixture:
    async def retrieve(self, query, role):
        return RetrievalContext(query=query, role=role, corpus_version=1, chunks=[EvidenceChunk(
            citation_id="benchmark-policy-v1:0", source_id="benchmark-policy", title="Synthetic policy",
            collection="pricing_policy", version="v1", chunk_index=0, start_char=0, end_char=43,
            text="Synthetic pricing requires margin compliance.")])


async def cache_measurements(directory, local_cache):
    settings = Settings(data_dir=directory, embedding_cache_dir=local_cache)
    telemetry, rag, grounding = Telemetry(directory), None, GroundingFixture()
    mode, unavailable = "model_and_retrieval_fixtures", None
    try:
        candidate = create_store(settings)
        if candidate.embedder.check()["available"]:
            candidate.ingest(Document(source_id="benchmark-policy", title="Synthetic policy", collection="pricing_policy",
                                      text="Synthetic pricing requires margin compliance, valid uncertainty and human review.", version="v1"))
            rag = candidate
            class LocalGrounding:
                async def retrieve(self, query, role):
                    return await asyncio.to_thread(rag.retrieve, query, role=role)
            grounding, mode = LocalGrounding(), "model_fixture_with_real_local_MiniLM_retrieval"
        else:
            candidate.close()
            unavailable = "Local model cache missing; retrieval fixture used and clearly excluded from real-RAG claims."
    except Exception:
        unavailable = "Local retrieval unavailable; retrieval fixture timing is not a real-RAG result."
    llm = GroundedLLM(lambda: settings, grounding, telemetry, directory, lambda *_: ModelFixture())
    measurements = []
    try:
        await llm.generate(BenchExplanation, role="analyst", query="Explain synthetic pricing.", facts={"price": "10.00"})
        for index in range(20):
            start = time.perf_counter()
            await llm.generate(BenchExplanation, role="analyst", facts={"price": "10.00"},
                               query="Explain synthetic pricing." if index % 2 == 0 else "  EXPLAIN  synthetic pricing. ")
            measurements.append((time.perf_counter() - start) * 1000)
        stats = llm.snapshot()["cache"]
        return {"mode": mode, "detail": unavailable, "samples": len(measurements),
                "median_ms": statistics.median(measurements), "p95_ms": float(np.quantile(measurements, .95)),
                "max_ms": max(measurements), "stats": stats,
                "max_under_100ms": max(measurements) < 100,
                "hit_rate": stats["hits"] / max(stats["hits"] + stats["misses"], 1),
                "p95_under_100ms": float(np.quantile(measurements, .95)) < 100,
                "warning": "Model provider is an explicit deterministic benchmark fixture; no live gateway latency, validity or effectiveness is inferred."}
    finally:
        await llm.close()
        telemetry.close()
        if rag:
            rag.close()


def hardware():
    result = {"os": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
              "logical_cpus": os.cpu_count(), "node": node_runtime()[2],
              "numpy": importlib.metadata.version("numpy"), "scipy": importlib.metadata.version("scipy")}
    if platform.system() == "Darwin":
        for key, command in (("cpu", ["sysctl", "-n", "machdep.cpu.brand_string"]),
                             ("memory_bytes", ["sysctl", "-n", "hw.memsize"])):
            try:
                result[key] = subprocess.check_output(command, text=True, timeout=2, stderr=subprocess.DEVNULL).strip()
            except (OSError, subprocess.SubprocessError):
                result[key] = "unavailable"
    return result


async def graph_measurements(directory, commerce_transport, args):
    from platform_app.app import create_app
    settings = Settings(data_dir=directory, commerce_url="http://benchmark-commerce",
                        embedding_cache_dir=args.local_model_cache, gateway_url="https://benchmark-fixture.invalid/v1",
                        api_key="benchmark-memory-only", model_router="fixture", model_narrator="fixture",
                        model_analyst="fixture", model_strategist="fixture")
    app = create_app(settings, commerce_transport=commerce_transport, llm_provider_factory=lambda *_: ModelFixture())
    async with app.router.lifespan_context(app):
        document = Document(source_id="graph-benchmark-policy", title="Synthetic graph policy", collection="pricing_policy",
                            text="Synthetic pricing requires margin compliance, uncertainty disclosure and human review.", version="v1")
        job = await asyncio.to_thread(app.state.grounding.submit, document, "benchmark-policy.md")
        for _ in range(300):
            current = app.state.grounding.get_upload(job["id"])
            if current["status"] in {"ready", "failed", "interrupted"}:
                break
            await asyncio.sleep(.05)
        if current["status"] != "ready":
            return {"status": "unavailable", "detail": "Real local grounding did not become ready; full graph benchmark skipped."}
        started = time.perf_counter()
        run = app.state.workflow.start(RunRequest(kind="grounded", category=args.category, iterations=args.iterations,
                                                 seed=args.seed, horizon_days=args.horizon, objective=args.objective))
        await asyncio.wait_for(asyncio.gather(*list(app.state.workflow.tasks)), timeout=240)
        duration = time.perf_counter() - started
        result = app.state.store.get_run(run["id"])
        items = app.state.governance.queue(run_id=run["id"])
        history = await app.state.commerce.all("/price-history")
        return {"mode": "actual_five_node_graph_with_typed_model_fixture_and_real_local_MiniLM",
                "status": result["status"], "seconds_to_human_review": duration, "under_300s": duration < 300,
                "sku_count": len(items), "cited_sku_count": sum(bool(i.get("citations")) for i in items),
                "model_fixture_calls": app.state.llm.snapshot()["calls"], "mode_at_decision": "supervised",
                "price_history_rows": len(history["items"]),
                "checkpoint_bytes": sum(p.stat().st_size for p in directory.glob("checkpoints.db*")),
                "warning": "Gateway is replaced only by the explicit test fixture. Timing ends at the real first human interrupt; no human latency, live model latency, or executed prices are included."}


async def benchmark(args):
    with tempfile.TemporaryDirectory(prefix="pricing-benchmark-") as temp:
        directory = Path(temp)
        seed_database(directory / "commerce.db", sku_count=args.skus, days=180, seed=args.seed,
                      as_of=args.as_of, data_dir=directory, categories=(args.category,))
        upstream = create_commerce(directory / "commerce.db")
        client = CommerceClient("http://benchmark-commerce", httpx.ASGITransport(app=upstream))
        async with upstream.router.lifespan_context(upstream):
            context = await client.context(category=args.category)
            competitors = read_competitors(directory)
            truth = read_evaluation_truth(directory / "commerce.db")
            mc_seconds, heartbeat, last, running = 0., [], time.perf_counter(), True
            original = analysis_module.sample_forecasts
            def timed(*positional, **keywords):
                nonlocal mc_seconds
                start = time.perf_counter()
                try:
                    return original(*positional, **keywords)
                finally:
                    mc_seconds += time.perf_counter() - start
            async def responsive():
                nonlocal last
                while running:
                    await asyncio.sleep(.01)
                    started = time.perf_counter()
                    await client.get("/health")
                    heartbeat.append({"gap_ms": (started - last) * 1000,
                                      "health_ms": (time.perf_counter() - started) * 1000})
                    last = started
            task = asyncio.create_task(responsive())
            analysis_module.sample_forecasts = timed
            start = time.perf_counter()
            try:
                report = await asyncio.to_thread(analyze_catalog, context["catalog"], context["sales"], context["inventory"],
                                                 competitors, iterations=args.iterations, seed=args.seed,
                                                 horizon_days=args.horizon, objective=args.objective)
                duration = time.perf_counter() - start
            finally:
                running = False
                await task
                analysis_module.sample_forecasts = original
            product, recommendation = context["catalog"][0], report["recommendations"][0]
            start = time.perf_counter()
            scenario = await asyncio.to_thread(simulate_sku, product, context["sales"], context["inventory"], competitors,
                                               recommendation["proposed_price"], args.iterations, args.seed, args.horizon)
            scenario_seconds = time.perf_counter() - start
            parity = scenario["forecast"] == recommendation["forecast"]
        cache = await cache_measurements(directory / "cache-benchmark", args.local_model_cache)
        graph = await graph_measurements(directory, httpx.ASGITransport(app=upstream), args)
        candidate_counts = [len(feasible_prices(p)) for p in context["catalog"]]
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "hardware": hardware(),
                "fixture": {"category": args.category, "skus": args.skus, "sales_days": 180, "seed": args.seed,
                            "as_of": args.as_of.isoformat(), "iterations": args.iterations, "horizon_days": args.horizon,
                            "objective": args.objective, "candidate_grid_points": 21,
                            "candidate_count_min": min(candidate_counts), "candidate_count_max": max(candidate_counts),
                            "source": "Fresh temporary Commerce SQLite, read via ASGI HTTP adapter"},
                "latency": {"quantitative_500_sku_seconds": duration, "quantitative_under_300s": duration < 300,
                            "monte_carlo_compute_seconds": mc_seconds, "monte_carlo_under_60s": mc_seconds < 60,
                            "single_sku_scenario_seconds": scenario_seconds, "scenario_under_5s": scenario_seconds < 5,
                            "scenario_recommendation_parity": parity, "health_samples": len(heartbeat),
                            "max_health_response_ms": max((i["health_ms"] for i in heartbeat), default=None),
                            "max_event_loop_gap_ms": max((i["gap_ms"] for i in heartbeat), default=None)},
                "effectiveness": evaluate(report, context, truth, args.horizon, args.objective), "cache": cache,
                "five_agent_graph_fixture": graph,
                "unverified": ["Full500-SKU grounded gateway latency and post-repair model validity",
                    "Browser action/render latency and visual QA", "Windows startup", "Human acceptance and escalation precision",
                    "Realized interval coverage and error convergence", "Longitudinal oscillation rate", "Assisted automatic share on operational decisions"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skus", type=int, default=500)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--horizon", type=int, default=14)
    parser.add_argument("--category", default="Beverages")
    parser.add_argument("--objective", choices=("balanced", "revenue", "margin"), default="balanced")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--local-model-cache", type=Path, default=Path("data/models"))
    parser.add_argument("--output", type=Path, default=Path("data/benchmark_result.json"))
    args = parser.parse_args()
    report = asyncio.run(benchmark(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "latency": report["latency"], "cache": report["cache"],
                      "five_agent_graph_fixture": report["five_agent_graph_fixture"]}, indent=2))


if __name__ == "__main__":
    main()
