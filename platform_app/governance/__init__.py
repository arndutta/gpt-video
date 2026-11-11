"""Deterministic validation, versioned review, and fenced Commerce execution."""

import asyncio

from . import control, decisions, registration, reverts
from .dispatch import Dispatcher
from .models import Decision, GovernanceError, GovernancePolicy, ModeUpdate
from .repository import Repository


class Governance:
    def __init__(self, store, commerce, override_forecast=None, redactor=None):
        self.store, self.commerce = store, commerce
        if redactor is None:
            from platform_app.llm.safety import redact
            redactor = redact
        self.redact = redactor
        self.repo = Repository(store)
        self.fence = asyncio.Lock()
        self.override_forecast = override_forecast
        self.dispatcher = Dispatcher(self.repo, commerce, self.fence)

    async def register(self, run_id, recommendations, catalog=None, history=None, activate=True):
        return await registration.register(self, run_id, recommendations, catalog, history, activate)

    async def activate(self, run_id):
        return await registration.activate(self, run_id)

    def queue(self, run_id=None, status=None, band=None, automatic=None, limit=5000):
        return self.repo.queue(run_id, status, band, automatic, limit)

    def get(self, item_id):
        return self.repo.get(item_id)

    def history(self, item_id):
        return self.repo.history(item_id)

    def mode(self):
        return self.repo.mode()

    def policy(self):
        return self.repo.policy()

    async def set_mode(self, mode, hold_seconds=None):
        return await control.set_mode(self, mode, hold_seconds)

    async def kill(self):
        return await control.kill(self)

    async def cancel_run(self, run_id, reason="run_failed"):
        return await control.cancel_run(self, run_id, reason)

    async def update_policy(self, changes):
        return await control.update_policy(self, changes)

    async def decide(self, item_id, decision):
        return await decisions.decide(self, item_id, decision)

    async def bulk(self, ids, expected_revisions):
        return await decisions.bulk(self, ids, expected_revisions)

    async def dispatch_due(self, item_ids=None):
        return await self.dispatcher.dispatch_due(item_ids)

    async def reconcile(self):
        return await self.dispatcher.reconcile()

    async def revert(self, item_id):
        return await reverts.revert(self, item_id)


__all__ = ["Governance", "Decision", "GovernancePolicy", "GovernanceError", "ModeUpdate"]
