"""Owned graph tasks, SQLite checkpoints, explicit recovery and per-item resume."""

import asyncio
import time
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from langgraph.errors import GraphInterrupt

from platform_app.tools import AnalysisError
from .nodes import AgentNodes
from .schemas import WorkflowState


class WorkflowManager:
    def __init__(self, settings_provider, store, commerce, grounding, llm, governance, feedback, telemetry, preview):
        self.settings_provider, self.store, self.commerce = settings_provider, store, commerce
        self.grounding, self.llm, self.governance = grounding, llm, governance
        self.feedback, self.telemetry, self.preview = feedback, telemetry, preview
        self.run_cpu = preview.run_cpu
        self.tasks = set()
        self.active_runs = set()
        self.stopping = False
        self.graph = None

    async def open(self):
        path = Path(self.settings_provider().data_dir) / "checkpoints.db"
        self._checkpoint_context = AsyncSqliteSaver.from_conn_string(str(path))
        saver = await self._checkpoint_context.__aenter__()
        nodes = AgentNodes(self)
        builder = StateGraph(WorkflowState)
        names = ["data_context", "quantitative", "strategy_reasoning", "validation_compliance", "execution"]
        functions = [nodes.data_context, nodes.quantitative, nodes.strategy, nodes.validation, nodes.execution]
        for name, function in zip(names, functions):
            builder.add_node(name, self._timed(name, function))
        for source, target in zip([START] + names[:-1], names):
            builder.add_edge(source, target)
        self.graph = builder.compile(checkpointer=saver, name="retail_five_agent_pipeline")

    def emit(self, event, **metadata):
        try:
            self.telemetry.event(event, **metadata)
        except Exception:
            pass

    def _timed(self, name, function):
        async def invoke(state):
            started, status = time.perf_counter(), "failed"
            try:
                result = await function(state)
                status = "completed"
                return result
            except GraphInterrupt:
                status = "awaiting_review"
                raise
            finally:
                elapsed = (time.perf_counter() - started) * 1000
                self.emit("agent_completed", run_id=state["run_id"], agent=name, status=status, latency_ms=elapsed)
        return invoke

    @staticmethod
    def config(run_id):
        return {"configurable": {"thread_id": run_id}, "recursion_limit": 30}

    def start(self, request):
        if self.preview.busy or self.stopping:
            raise RuntimeError("Another analysis is running. Wait for it to finish.")
        settings = self.settings_provider()
        if not settings.gateway_base_url or not settings.api_key:
            raise RuntimeError("Configure the gateway URL, API key and model aliases in Settings before a grounded run.")
        if not all(getattr(settings, "model_" + role) for role in ("router", "narrator", "analyst", "strategist")):
            raise RuntimeError("Configure all four gateway model aliases before a grounded run.")
        self.preview.busy = True
        try:
            run = self.store.create_run(request.model_dump())
            self.active_runs.add(run["id"])
            self._schedule(run["id"], {"run_id": run["id"], "request": request.model_dump()})
            return run
        except Exception:
            self.preview.busy = False
            raise

    def _schedule(self, run_id, value):
        task = asyncio.create_task(self._drive(run_id, value))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def resume(self, run_id, *, explicit=True):
        run = self.store.get_run(run_id)
        if not run or run["request"].get("kind") != "grounded":
            raise ValueError("Grounded run not found")
        if self.stopping or self.preview.busy:
            raise RuntimeError("Another analysis is running. Resume after it finishes.")
        if not explicit and run_id not in self.active_runs:
            return run
        snapshot = await self.graph.aget_state(self.config(run_id))
        if not snapshot.next:
            return run
        if snapshot.interrupts and not self._resolved(snapshot.interrupts[0].value["item_id"]):
            raise ValueError("Record a decision for the interrupted item before resuming this run.")
        self.preview.busy = True
        self.active_runs.add(run_id)
        command = Command(resume={"decision_recorded": True}) if snapshot.interrupts else None
        self._schedule(run_id, command)
        return self.store.get_run(run_id)

    def _resolved(self, item_id):
        items = self.governance.queue()
        item = next((i for i in items if i["id"] == item_id), None)
        return bool(item and item["status"] not in {"pending_review", "hold", "escalated", "draft"})

    async def _drive(self, run_id, value):
        try:
            result = await self.graph.ainvoke(value, self.config(run_id))
            snapshot = await self.graph.aget_state(self.config(run_id))
            # Decisions are durable and item-scoped; resume values are never approvals.
            while snapshot.interrupts and self._resolved(snapshot.interrupts[0].value["item_id"]):
                result = await self.graph.ainvoke(Command(resume={"decision_recorded": True}), self.config(run_id))
                snapshot = await self.graph.aget_state(self.config(run_id))
            report = dict(snapshot.values.get("report", result.get("report", {})))
            report["recommendations"] = self.governance.queue(run_id=run_id)
            report["pending_interrupts"] = [i.value for i in snapshot.interrupts]
            status = "awaiting_review" if snapshot.interrupts else "completed"
            self.store.update_run(run_id, status, "human_review" if snapshot.interrupts else "completed", result=report)
            if not snapshot.interrupts:
                self.active_runs.discard(run_id)
                await self.feedback.refresh(self.governance.queue(run_id=run_id))
        except asyncio.CancelledError:
            self.store.update_run(run_id, "interrupted", "interrupted",
                                  error="Run checkpoint saved. Explicitly resume after restart; scheduling remains off.")
            await self.governance.cancel_run(run_id, "run_interrupted")
            raise
        except Exception as error:
            safe = getattr(error, "detail", None)
            if isinstance(error, AnalysisError):
                safe = str(error)
            self.store.update_run(run_id, "failed", "failed", result={"quality": getattr(error, "quality", None)},
                                  error=safe or "The grounded pipeline failed. Check gateway, grounding and service health, then explicitly resume.")
            await self.governance.cancel_run(run_id, "run_failed")
            self.active_runs.discard(run_id)
        finally:
            self.preview.busy = False

    async def decision_recorded(self, run_id):
        run = self.store.get_run(run_id)
        if not run or run["status"] != "awaiting_review" or self.preview.busy:
            return
        snapshot = await self.graph.aget_state(self.config(run_id))
        if snapshot.interrupts and self._resolved(snapshot.interrupts[0].value["item_id"]):
            await self.resume(run_id, explicit=False)

    async def stop(self):
        self.stopping = True
        await self.cancel_active()
        if self.graph:
            await self._checkpoint_context.__aexit__(None, None, None)

    async def cancel_active(self):
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        self.active_runs.clear()
