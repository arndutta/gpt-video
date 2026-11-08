"""Lifespan-owned, bounded quantitative preview work. No price execution."""

import asyncio

from platform_app.commerce_client import CommerceClient, CommerceUnavailable, read_competitors
from platform_app.config import RunRequest, Settings
from platform_app.storage import Store
from platform_app.tools import AnalysisError, analyze_catalog


class RunManager:
    def __init__(self, settings: Settings, store: Store, commerce: CommerceClient):
        self.settings, self.store, self.commerce = settings, store, commerce
        self.tasks: set[asyncio.Task] = set()
        self.workers: set[asyncio.Task] = set()
        self.busy = False
        self.stopping = False

    def start(self, request: RunRequest) -> dict:
        if self.busy or self.stopping:
            raise RuntimeError("A preview is already running. Wait for it to finish.")
        self.busy = True
        try:
            run = self.store.create_run(request.model_dump())
            task = asyncio.create_task(self._execute(run["id"], request))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return run
        except Exception:
            self.busy = False
            raise

    async def _execute(self, run_id: str, request: RunRequest):
        try:
            self.store.update_run(run_id, "running", "ingesting")
            context, competitors = await asyncio.gather(
                self.commerce.context(category=request.category, sku_ids=request.sku_ids),
                asyncio.to_thread(read_competitors, self.settings.data_dir))
            skus = {item["sku"] for item in context["catalog"]}
            competitors = [item for item in competitors if item.get("sku") in skus]
            self.store.update_run(run_id, "running", "quantifying")
            report = await self.run_cpu(
                analyze_catalog, context["catalog"], context["sales"], context["inventory"], competitors,
                objective=request.objective, iterations=request.iterations, seed=request.seed,
                horizon_days=request.horizon_days)
            report["kind"] = "quantitative_preview"
            report["summary"] = report.get("aggregate", {})
            report["source_as_of"] = context["as_of"]
            self.store.update_run(run_id, "completed", "completed", result=report)
        except asyncio.CancelledError:
            self.store.update_run(run_id, "interrupted", "interrupted",
                                  error="Application stopped. Start a new preview to refresh input data.")
            raise
        except (AnalysisError, CommerceUnavailable, ValueError, OSError) as error:
            detail = str(error) if isinstance(error, (AnalysisError, CommerceUnavailable)) else \
                "The competitor feed is unreadable. Regenerate synthetic data or repair the feed."
            result = {"kind": "quantitative_preview", "executable": False,
                      "quality": getattr(error, "quality", None)}
            self.store.update_run(run_id, "failed", "failed", result=result, error=detail)
        except Exception:
            self.store.update_run(run_id, "failed", "failed", error=
                                  "Unexpected preview failure. Check service health and restart the preview.")
        finally:
            self.busy = False

    async def run_cpu(self, function, *args, **kwargs):
        """Cancellation waits for the owned finite numerical worker before releasing its slot."""
        worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        self.workers.add(worker)
        cancellation = None
        try:
            # Repeated stop/disconnect requests must not release a still-running thread.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError as error:
                    cancellation = error
                except Exception:
                    break
            if cancellation is not None:
                if not worker.cancelled():
                    worker.exception()  # Consume a late numerical error before propagating cancellation.
                raise cancellation
            return worker.result()
        finally:
            if worker.done():
                self.workers.discard(worker)

    async def stop(self):
        self.stopping = True
        pending = list(self.tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if self.workers:
            await asyncio.gather(*list(self.workers), return_exceptions=True)
