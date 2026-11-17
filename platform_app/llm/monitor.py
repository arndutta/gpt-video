"""Nonblocking usage accounting and explicitly opted-in metadata-only Langfuse export."""

import queue
from collections import Counter
from collections.abc import Mapping
from contextlib import closing
import sqlite3
import threading
import time

from langchain_core.callbacks import AsyncCallbackHandler

from platform_app.config import tls_context
from platform_app.database import sql
from .safety import redact
from .pricing import catalog, estimate_cost, initialize_pricing


def usage(raw) -> tuple[int, int]:
    info = getattr(raw, "usage_metadata", None)
    if not isinstance(info, Mapping) or not info:
        response = getattr(raw, "response_metadata", None)
        info = response.get("token_usage") if isinstance(response, Mapping) else None
    if not isinstance(info, Mapping):
        info = {}

    def count(*names):
        value = next((info[name] for name in names if name in info), 0)
        return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1_000_000_000 else 0

    return count("input_tokens", "prompt_tokens"), count("output_tokens", "completion_tokens")


class MetadataOnlyCallback(AsyncCallbackHandler):
    """Never delegates prompt/message payloads to an external tracing integration."""
    run_inline = True

    def __init__(self, telemetry, metadata):
        self.telemetry, self.metadata = telemetry, metadata

    async def on_llm_end(self, _response, **_kwargs):
        try:
            self.telemetry.event("model_callback", **self.metadata, status="completed")
        except Exception:
            pass

    async def on_llm_error(self, _error, **_kwargs):
        try:
            self.telemetry.event("model_callback", **self.metadata, status="failed")
        except Exception:
            pass


class CallMonitor:
    def __init__(self, data_dir, telemetry, settings_provider):
        self.path, self.telemetry, self.settings_provider = data_dir / "app.db", telemetry, settings_provider
        self.lock, self.queue = threading.Lock(), queue.Queue(maxsize=1024)
        self.active = self.failed = self.calls = self.tokens_in = self.tokens_out = 0
        self.cost = 0.0
        self.cost_sources = Counter()
        self.available, self.dropped, self.langfuse = True, 0, None
        try:
            initialize_pricing(data_dir)
            with closing(sqlite3.connect(self.path, timeout=.2)) as db, db:
                db.executescript(sql("usage_ddl.sql"))
                columns = {row[1] for row in db.execute("PRAGMA table_info(llm_usage)")}
                if "pricing_source" not in columns:
                    db.execute("ALTER TABLE llm_usage ADD COLUMN pricing_source TEXT NOT NULL DEFAULT 'legacy_configured_fallback_rates'")
                if "pricing_model" not in columns:
                    db.execute("ALTER TABLE llm_usage ADD COLUMN pricing_model TEXT")
                row = db.execute("SELECT count(*),coalesce(sum(tokens_in),0),coalesce(sum(tokens_out),0),"
                                 "coalesce(sum(cost_usd),0),sum(status='failed') FROM llm_usage").fetchone()
                self.calls, self.tokens_in, self.tokens_out, self.cost, self.failed = row
                self.failed = self.failed or 0
                self.cost_sources.update(dict(db.execute("SELECT pricing_source,count(*) FROM llm_usage GROUP BY pricing_source")))
        except (OSError, sqlite3.Error):
            self.available = False
        self.worker = threading.Thread(target=self._consume, daemon=True, name="model-metadata")
        self.worker.start()

    def begin(self):
        with self.lock:
            self.active += 1
        return time.perf_counter()

    def complete(self, started, *, role, model, run_id, settings, raw=None, status="completed"):
        model = redact(model, [value.get_secret_value() for name in
                       ("api_key", "langfuse_public_key", "langfuse_secret_key")
                       if (value := getattr(settings, name, None))])
        tokens_in, tokens_out = usage(raw)
        try:
            priced = estimate_cost(settings, role, model, raw, tokens_in, tokens_out,
                                   data_dir=self.path.parent)
        except Exception:
            priced = {"cost_usd": (tokens_in * settings.llm_input_cost_per_million
                                  + tokens_out * settings.llm_output_cost_per_million) / 1_000_000,
                      "pricing_source": "configured_fallback_rates", "pricing_model": None}
        cost = priced["cost_usd"]
        item = {"timestamp": time.time(), "run_id": run_id, "agent": role, "model": model,
                "status": status, "tokens_in": tokens_in, "tokens_out": tokens_out,
                **priced, "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
        with self.lock:
            self.active -= 1
            self.calls += 1
            self.failed += status == "failed"
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            self.cost += cost
            self.cost_sources[priced["pricing_source"]] += 1
        try:
            self.telemetry.event("model_call", **{key: value for key, value in item.items() if key != "timestamp"})
        except Exception:
            self.available = False
        try:
            self.queue.put_nowait(item)
        except Exception:
            with self.lock:
                self.dropped += 1

    def _export(self, item):
        settings = self.settings_provider()
        if not settings.langfuse_enabled:
            return
        if not settings.langfuse_host or not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return
        if self.langfuse is None:
            import httpx
            from langfuse import Langfuse
            self.langfuse = Langfuse(base_url=settings.langfuse_host, timeout=1, debug=False,
                                    httpx_client=httpx.Client(verify=tls_context(settings), timeout=1),
                                    public_key=settings.langfuse_public_key.get_secret_value(),
                                    secret_key=settings.langfuse_secret_key.get_secret_value(),
                                    mask=lambda **kwargs: redact(kwargs.get("data"),
                                        [settings.api_key.get_secret_value()] if settings.api_key else []),
                                    should_export_span=lambda span: span.name == "pricing-model")
        observation = self.langfuse.start_observation(
            name="pricing-model", as_type="generation", model=item["model"],
            metadata={key: item[key] for key in ("run_id", "agent", "status", "latency_ms", "pricing_source", "pricing_model")},
            usage_details={"input": item["tokens_in"], "output": item["tokens_out"]},
            cost_details={"total": item["cost_usd"]})
        observation.end()

    def _consume(self):
        while True:
            item = self.queue.get()
            if item is None:
                if self.langfuse is not None:
                    try:
                        self.langfuse.flush()
                    except Exception:
                        self.available = False
                return
            try:
                with closing(sqlite3.connect(self.path, timeout=.2)) as db, db:
                    db.execute("INSERT INTO llm_usage(timestamp,run_id,agent,model,status,tokens_in,tokens_out,"
                               "cost_usd,latency_ms,pricing_source,pricing_model) VALUES(:timestamp,:run_id,:agent,:model,:status,:tokens_in,"
                               ":tokens_out,:cost_usd,:latency_ms,:pricing_source,:pricing_model)", item)
            except Exception:
                self.available = False
            try:
                self._export(item)
            except Exception:
                # No proprietary content is supplied to this integration, including error strings.
                self.available = False

    def snapshot(self):
        try:
            provenance = catalog(self.path.parent)["provenance"]
        except Exception:
            provenance = {"status": "unavailable"}
        with self.lock:
            return {"active_calls": self.active, "calls": self.calls, "failed_calls": self.failed,
                    "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                    "estimated_cost_usd": round(self.cost, 8),
                    "cost_source": next(iter(self.cost_sources)) if len(self.cost_sources) == 1 else "mixed" if self.cost_sources else "no_calls",
                    "pricing_sources": dict(self.cost_sources), "pricing_catalog": provenance,
                    "telemetry_available": self.available, "dropped_events": self.dropped}

    def close(self):
        try:
            self.queue.put(None, timeout=.1)
            self.worker.join(timeout=1)
        except queue.Full:
            self.available = False
