"""Continuous scheduling is explicit, serialized, bounded and stopped by failures."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from platform_app.config import RunRequest
from platform_app.loop import IntervalLoop, LoopRequest
from platform_app.storage import Store, now

REAL_SLEEP = asyncio.sleep


class WorkflowFixture:
    def __init__(self, store, outcomes=None):
        self.store, self.outcomes = store, list(outcomes or ["completed"])
        self.preview = SimpleNamespace(busy=False)
        self.requests, self.tasks, self.maximum_active, self.active = [], set(), 0, 0

    def start(self, request):
        if self.preview.busy:
            raise RuntimeError("Overlapping analysis")
        self.preview.busy = True
        self.requests.append(request)
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        run = self.store.create_run(request.model_dump())
        outcome = self.outcomes.pop(0) if self.outcomes else "completed"
        async def finish():
            await REAL_SLEEP(.005)
            self.store.update_run(run["id"], outcome, outcome,
                                  error="Fixture failed" if outcome == "failed" else None)
            self.active -= 1
            self.preview.busy = False
        task = asyncio.create_task(finish())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return run

    async def cancel_active(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        self.preview.busy = False


class FeedbackFixture:
    def __init__(self):
        self.count = 0
    async def refresh(self, _items):
        self.count += 1


@pytest.fixture
def loop_fixture(tmp_path, monkeypatch):
    async def quick_sleep(seconds):
        await REAL_SLEEP(.001 if seconds else 0)
    monkeypatch.setattr("platform_app.loop.asyncio.sleep", quick_sleep)
    store = Store(tmp_path)
    workflow, feedback = WorkflowFixture(store), FeedbackFixture()
    governance = SimpleNamespace(queue=lambda: [])
    return IntervalLoop(store, workflow, feedback, governance), workflow, feedback, store


def payload(**changes):
    return LoopRequest(request=RunRequest(kind="grounded", iterations=100, sku_ids=["SKU-1"]),
                       interval_seconds=5, **changes)


async def terminal(loop):
    for _ in range(100):
        if loop.task.done():
            return loop.state()
        await REAL_SLEEP(.005)
    raise AssertionError("The finite loop did not terminate")


async def test_loop_off_until_explicit_start_and_iteration_cap_serializes_runs(loop_fixture):
    loop, workflow, feedback, store = loop_fixture
    assert loop.state()["status"] == "off" and not workflow.requests
    initial = loop.start(payload(max_iterations=3))
    assert initial["running"] is True
    result = await terminal(loop)
    assert result["status"] == "completed" and not result["running"]
    assert result["iteration_count"] == 3 and len(workflow.requests) == feedback.count == 3
    assert workflow.maximum_active == 1 and result["next_run_at"] is None
    assert all(r.kind == "grounded" and r.sku_ids == ["SKU-1"] for r in workflow.requests)
    assert loop.history()[0]["session_id"] == result["session_id"]


async def test_first_failed_iteration_stops_without_another_schedule(loop_fixture):
    loop, workflow, feedback, _ = loop_fixture
    workflow.outcomes = ["failed", "completed"]
    loop.start(payload())
    result = await terminal(loop)
    await REAL_SLEEP(.03)
    assert result["status"] == "failed" and result["iteration_count"] == 1
    assert len(workflow.requests) == feedback.count == 1 and result["next_run_at"] is None
    assert loop.history()[0]["status"] == "failed"


async def test_review_interrupt_is_successful_iteration_not_scheduling_failure(loop_fixture):
    loop, workflow, _, _ = loop_fixture
    workflow.outcomes = ["awaiting_review"]
    loop.start(payload(max_iterations=1))
    result = await terminal(loop)
    assert result["status"] == "completed" and result["error"] is None
    assert result["iteration_count"] == 1


async def test_stop_cancels_timer_and_never_starts_another_iteration(loop_fixture):
    loop, workflow, _, _ = loop_fixture
    loop.start(payload())
    for _ in range(100):
        if loop.state()["status"] == "waiting":
            break
        await REAL_SLEEP(.001)
    result = await loop.stop("operator")
    count = len(workflow.requests)
    await REAL_SLEEP(.02)
    assert not result["running"] and result["status"] == "stopped"
    assert result["stop_reason"] == "operator" and len(workflow.requests) == count
    assert result["next_run_at"] is None


async def test_overlap_and_preview_request_are_refused(loop_fixture):
    loop, workflow, _, _ = loop_fixture
    with pytest.raises(ValueError, match="grounded"):
        loop.start(LoopRequest(request=RunRequest(), interval_seconds=5))
    workflow.preview.busy = True
    with pytest.raises(RuntimeError, match="active analysis"):
        loop.start(payload())
    workflow.preview.busy = False
    loop.start(payload(max_iterations=1))
    with pytest.raises(RuntimeError, match="already running"):
        loop.start(payload(max_iterations=1))
    await terminal(loop)


def test_reboot_marks_prior_session_interrupted_and_never_restarts_timer(loop_fixture):
    loop, workflow, feedback, store = loop_fixture
    state = {"session_id": "old-session", "created_at": now(), "running": True,
             "status": "waiting", "next_run_at": now(), "iteration_count": 2}
    with store.connection() as db:
        db.execute("INSERT INTO loop_sessions VALUES(?,?,?)", (state["session_id"], state["created_at"], json.dumps(state)))
    restarted = IntervalLoop(store, workflow, feedback, SimpleNamespace(queue=lambda: []))
    assert restarted.task is None and restarted.state()["status"] == "interrupted"
    assert restarted.state()["running"] is False and restarted.state()["next_run_at"] is None
    assert not workflow.requests
