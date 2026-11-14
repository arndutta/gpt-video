"""Checkpoint inspection shares the analysis slot and cannot outlive a halt fence."""

import asyncio
from types import SimpleNamespace

import pytest

from platform_app.config import RunRequest, Settings
from platform_app.runs import RunManager
from platform_app.storage import Store
from platform_app.workflow.manager import WorkflowManager


class CheckpointFixture:
    def __init__(self, *, pending=True, interrupts=(), error=None):
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.snapshot = SimpleNamespace(next=("execution",) if pending else (), interrupts=interrupts)
        self.error = error

    async def aget_state(self, _config):
        self.entered.set()
        await self.release.wait()
        if self.error:
            raise self.error
        return self.snapshot


def manager_fixture(tmp_path, monkeypatch, **checkpoint):
    settings = Settings(data_dir=tmp_path, gateway_url="https://fixture.test/v1", api_key="fixture-key",
                        model_router="router", model_narrator="narrator", model_analyst="analyst",
                        model_strategist="strategist")
    store = Store(tmp_path)
    preview = RunManager(settings, store, None)
    governance = SimpleNamespace(queue=lambda: [])
    manager = WorkflowManager(lambda: settings, store, None, None, None, governance, None, None, preview)
    manager.graph = CheckpointFixture(**checkpoint)
    run = store.create_run(RunRequest(kind="grounded").model_dump())
    store.update_run(run["id"], "interrupted", "interrupted")
    scheduled = []
    monkeypatch.setattr(manager, "_schedule", lambda run_id, value: scheduled.append((run_id, value)))
    return manager, run["id"], scheduled


async def test_resume_reserves_slot_before_checkpoint_io_and_rejects_overlapping_work(tmp_path, monkeypatch):
    manager, run_id, scheduled = manager_fixture(tmp_path, monkeypatch)
    pending = asyncio.create_task(manager.resume(run_id))
    try:
        await manager.graph.entered.wait()
        assert manager.preview.busy
        with pytest.raises(RuntimeError, match="Another analysis"):
            await manager.resume(run_id)
        with pytest.raises(RuntimeError, match="Another analysis"):
            manager.start(RunRequest(kind="grounded"))
        with pytest.raises(RuntimeError, match="already running"):
            manager.preview.start(RunRequest())
        manager.graph.release.set()
        await pending
        assert len(scheduled) == 1 and manager.preview.busy
    finally:
        manager.graph.release.set()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("case", ["completed", "unresolved", "error", "cancelled"])
async def test_resume_releases_slot_when_inspection_does_not_schedule(tmp_path, monkeypatch, case):
    interrupts = (SimpleNamespace(value={"item_id": "undecided"}),) if case == "unresolved" else ()
    manager, run_id, scheduled = manager_fixture(tmp_path, monkeypatch, pending=case != "completed",
                                                interrupts=interrupts,
                                                error=OSError("Fixture checkpoint error") if case == "error" else None)
    pending = asyncio.create_task(manager.resume(run_id))
    await manager.graph.entered.wait()
    if case == "cancelled":
        pending.cancel()
    manager.graph.release.set()
    if case == "unresolved":
        with pytest.raises(ValueError, match="Record a decision"):
            await pending
    elif case == "error":
        with pytest.raises(OSError, match="checkpoint error"):
            await pending
    elif case == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        await pending
    assert not scheduled and not manager.preview.busy


async def test_automatic_resume_notification_is_noop_while_another_analysis_owns_slot(tmp_path, monkeypatch):
    manager, run_id, scheduled = manager_fixture(tmp_path, monkeypatch)
    manager.active_runs.add(run_id)
    manager.preview.busy = True
    assert (await manager.resume(run_id, explicit=False))["id"] == run_id
    assert not scheduled and not manager.graph.entered.is_set()
    assert manager.preview.busy


async def test_halt_during_checkpoint_inspection_prevents_delayed_resume_launch(tmp_path, monkeypatch):
    manager, run_id, scheduled = manager_fixture(tmp_path, monkeypatch)
    pending = asyncio.create_task(manager.resume(run_id))
    await manager.graph.entered.wait()
    await manager.cancel_active()
    manager.graph.release.set()
    with pytest.raises(RuntimeError, match="canceled"):
        await pending
    assert not scheduled and not manager.preview.busy
