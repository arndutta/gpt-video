"""Lifespan ownership of graph, holds, scheduling, telemetry and local clients."""

import asyncio

from platform_app.commerce_client import CommerceClient
from platform_app.discovery import init_discovery
from platform_app.feedback import Feedback
from platform_app.gateway import GatewayReadiness
from platform_app.feeds import optional_quotes
from platform_app.governance import Governance, GovernancePolicy
from platform_app.governance import GovernanceError
from platform_app.grounding.service import GroundingService
from platform_app.llm import GroundedLLM
from platform_app.llm.safety import redact
from platform_app.loop import IntervalLoop
from platform_app.runs import RunManager
from platform_app.scenarios import init_scenarios
from platform_app.storage import Store
from platform_app.telemetry import Telemetry
from platform_app.tools import simulate_sku
from platform_app.tools.context import effective_catalog
from platform_app.workflow import WorkflowManager


async def initialize(app, config, commerce_transport=None, rag_factory=None, llm_provider_factory=None):
    state = app.state
    state.settings, state.store = config, Store(config.data_dir)
    def redact_reason(value):
        secrets = [secret.get_secret_value() for secret in (state.settings.api_key,
                   state.settings.langfuse_public_key, state.settings.langfuse_secret_key) if secret]
        return redact(value, secrets=secrets)
    state.store.redact = redact_reason
    state.gateway = GatewayReadiness(lambda: state.settings, state.store)
    if config.startup_mode == "grounded":
        readiness = await state.gateway.check(actor="system")
        if not readiness["verified"]:
            raise RuntimeError("Grounded startup requires verified gateway aliases. " + readiness["detail"])
    state.commerce = CommerceClient(config.commerce_url, commerce_transport)
    state.runs = RunManager(config, state.store, state.commerce)
    state.telemetry = Telemetry(config.data_dir)
    state.grounding = GroundingService(lambda: state.settings, state.store, rag_factory=rag_factory)
    state.llm = GroundedLLM(lambda: state.settings, state.grounding, state.telemetry, config.data_dir,
                            provider_factory=llm_provider_factory)
    state.feedback = Feedback(state.store, state.commerce)

    async def override_forecast(item, price, product):
        if state.runs.busy or state.runs.stopping:
            raise GovernanceError("analysis_busy", "Wait for the active analysis before recalculating a price override.")
        state.runs.busy = True
        try:
            context, feed = await asyncio.gather(state.commerce.context(sku_ids=[item["sku"]]),
                                                optional_quotes(state.settings))
            run = state.store.get_run(item["run_id"])
            request = (run or {}).get("request", {})
            effective = effective_catalog([product], GovernancePolicy(**state.governance.policy()["thresholds"]))[0]
            return await state.runs.run_cpu(simulate_sku, effective, context["sales"], context["inventory"], feed, price,
                                            iterations=request.get("iterations", 1000), seed=request.get("seed", 42),
                                            horizon_days=request.get("horizon_days", 14),
                                            learning=state.feedback.states().get(item["sku"]))
        finally:
            state.runs.busy = False

    state.governance = Governance(state.store, state.commerce, override_forecast=override_forecast, redactor=redact_reason)
    state.runs.governance, state.runs.feedback = state.governance, state.feedback
    state.workflow = WorkflowManager(lambda: state.settings, state.store, state.commerce, state.grounding,
                                     state.llm, state.governance, state.feedback, state.telemetry, state.runs)
    await state.workflow.open()
    state.loop = IntervalLoop(state.store, state.workflow, state.feedback, state.governance)
    init_scenarios(state.store)
    init_discovery(state.store)
    state.maintenance = asyncio.create_task(_maintain(state))


async def _maintain(state):
    while True:
        await asyncio.sleep(1)
        try:
            await state.governance.dispatch_due()
            for run_id in list(state.workflow.active_runs):
                await state.workflow.decision_recorded(run_id)
            await state.loop.observe_failures()
        except asyncio.CancelledError:
            raise
        except Exception:
            state.telemetry.event("maintenance_failed", status="failed")


async def shutdown(state):
    await state.loop.stop("application_shutdown")
    state.maintenance.cancel()
    await asyncio.gather(state.maintenance, return_exceptions=True)
    await state.workflow.stop()
    await state.runs.stop()
    await state.grounding.stop()
    await state.llm.close()
    state.telemetry.close()
