"""Data & Context owns and drains every concurrent request before it exits."""

import asyncio
from types import SimpleNamespace

import pytest

from platform_app.llm import GroundedLLMError
from platform_app.workflow.nodes import AgentNodes
import platform_app.workflow.nodes as module


def owner_fixture(monkeypatch):
    catalog = [{"sku": "SKU-1", "category": "Beverages"}]

    async def context(**_kwargs):
        return {"catalog": catalog, "sales": [], "inventory": [], "as_of": "2026-11-14"}

    async def all_rows(path):
        return {"items": catalog if path == "/catalog" else []}

    async def retrieve(*_args):
        return SimpleNamespace(corpus_version=1)

    async def fetch():
        return []

    async def run_cpu(function, *args):
        return function(*args)

    monkeypatch.setattr(module, "configured_feed", lambda _settings: SimpleNamespace(fetch=fetch))
    monkeypatch.setattr(module, "quality_report", lambda *_args: {"blocked": False, "checks": [], "status": "passed"})
    monkeypatch.setattr(module, "business_context", lambda *_args: {})
    return SimpleNamespace(store=SimpleNamespace(update_run=lambda *_a, **_k: None, audit=lambda *_a, **_k: None),
                           commerce=SimpleNamespace(context=context, all=all_rows),
                           grounding=SimpleNamespace(retrieve=retrieve), llm=SimpleNamespace(generate=None),
                           governance=SimpleNamespace(mode=lambda: {"policy_version": 1}),
                           settings_provider=lambda: None, run_cpu=run_cpu, emit=lambda *_a, **_k: None)


class BlockedPeer:
    def __init__(self):
        self.entered, self.cleaned = asyncio.Event(), asyncio.Event()
        self.tasks = []

    async def run(self):
        self.tasks.append(asyncio.current_task())
        self.entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            # Assert ownership includes awaiting asynchronous cancellation cleanup.
            await asyncio.sleep(0)
            self.cleaned.set()

    async def finish(self):
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


async def test_narrative_failure_cancels_and_drains_peer_before_preserving_original_error(monkeypatch):
    owner, peer = owner_fixture(monkeypatch), BlockedPeer()
    error = GroundedLLMError("gateway_call_failed", "Synthetic model failure")

    async def generate(_schema, *, role, **_kwargs):
        if role == "narrator":
            return await peer.run()
        await peer.entered.wait()
        raise error

    owner.llm.generate = generate
    try:
        with pytest.raises(GroundedLLMError) as caught:
            await AgentNodes(owner).data_context({"run_id": "fixture-run", "request": {}})
        assert caught.value is error
        assert peer.cleaned.is_set(), "The failed stage must await its remaining model request's cleanup."
        assert all(task.done() for task in peer.tasks)
    finally:
        await peer.finish()


async def test_input_failure_cancels_and_drains_other_reads_before_preserving_original_error(monkeypatch):
    owner, peer = owner_fixture(monkeypatch), BlockedPeer()
    error = RuntimeError("Synthetic required Commerce failure")

    async def context(**_kwargs):
        await peer.entered.wait()
        raise error

    async def retrieve(*_args):
        return await peer.run()

    owner.commerce.context, owner.grounding.retrieve = context, retrieve
    try:
        with pytest.raises(RuntimeError) as caught:
            await AgentNodes(owner).data_context({"run_id": "fixture-run", "request": {}})
        assert caught.value is error
        assert peer.cleaned.is_set(), "The failed stage must await outstanding required input reads."
        assert all(task.done() for task in peer.tasks)
    finally:
        await peer.finish()


@pytest.mark.parametrize("phase", ["inputs", "narratives"])
async def test_canceling_data_context_drains_the_current_concurrent_phase(monkeypatch, phase):
    owner, peer = owner_fixture(monkeypatch), BlockedPeer()
    if phase == "inputs":
        async def retrieve(*_args):
            return await peer.run()
        owner.grounding.retrieve = retrieve
    else:
        async def generate(*_args, **_kwargs):
            return await peer.run()
        owner.llm.generate = generate
    task = asyncio.create_task(AgentNodes(owner).data_context({"run_id": "fixture-run", "request": {}}))
    try:
        await peer.entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert peer.cleaned.is_set()
        assert all(child.done() for child in peer.tasks)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await peer.finish()
