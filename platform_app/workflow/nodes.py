"""The five agents. Execution reads durable authorizations and never calls a model."""

import asyncio
from collections import Counter
import hashlib
import json
import time

from langgraph.types import Command, interrupt
from langgraph.graph import END

from platform_app.commerce_client import read_competitors
from platform_app.feeds import configured_feed
from platform_app.governance import GovernancePolicy
from platform_app.governance.stability import analyze_stability, damping_bounds
from platform_app.tools import AnalysisError, analyze_catalog
from platform_app.tools.quality import quality_report
from platform_app.tools.context import business_context, effective_catalog
from .prompts import narrative_prompt, strategy_prompt
from .schemas import CitedNarrative, StrategyNarrative
from .validation import narrate_verdicts, require_policy


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


async def owned_gather(*requests):
    """A stage cannot exit while a sibling request is still using its resources."""
    tasks = [asyncio.ensure_future(request) for request in requests]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


class AgentNodes:
    def __init__(self, owner):
        self.owner = owner

    def stage(self, state, name):
        self.owner.store.update_run(state["run_id"], "running", name,
                                    result=state.get("report"))
        self.owner.store.audit("agent_started", {"agent": name}, actor="system", run_id=state["run_id"])

    async def data_context(self, state):
        self.stage(state, "data_context")
        o, request = self.owner, state["request"]
        started = time.perf_counter()

        async def competitors():
            try:
                return await configured_feed(o.settings_provider()).fetch(), None
            except (ValueError, OSError):
                return [], "Optional competitor feed unavailable; uncertainty increased and confidence reduced."

        context, optional, grounding, history, family_catalog = await owned_gather(
            o.commerce.context(category=request.get("category"), sku_ids=request.get("sku_ids")),
            competitors(), o.grounding.retrieve("Retail pricing policy market inventory safety guidance", "analyst"),
            o.commerce.all("/price-history"), o.commerce.all("/catalog"))
        skus = {p["sku"] for p in context["catalog"]}
        feed, warning = optional
        feed = [r for r in feed if r.get("sku") in skus]
        quality = await o.run_cpu(quality_report, context["catalog"], context["sales"], context["inventory"], feed)
        if warning:
            quality["checks"].append({"check": "competitor_availability", "severity": "warning",
                                      "affected_records": len(skus), "message": warning})
            quality["status"] = "failed" if quality["blocked"] else "degraded"
        o.store.audit("quality_gate", quality, actor="system", run_id=state["run_id"])
        if quality["blocked"]:
            raise AnalysisError("Required Commerce inputs failed the data quality gate.", quality=quality)
        facts = {"quality": quality, "sku_count": len(skus), "sales_observations": len(context["sales"]),
                 "category_counts": dict(Counter(p["category"] for p in context["catalog"])),
                 "competitor_observations": len(feed), "source_as_of": context["as_of"],
                 "corpus_version": grounding.corpus_version,
                 "business_signals": await o.run_cpu(business_context, context, feed)}
        narrative, anomaly_narrative = await owned_gather(
            o.llm.generate(CitedNarrative, role="analyst", query="Retail pricing market and inventory context",
                           facts=facts, run_id=state["run_id"],
                           prompt=narrative_prompt("Explain the competitive and inventory context. Do not invent observations."),
                           policy_version=str(o.governance.mode()["policy_version"])),
            o.llm.generate(CitedNarrative, role="narrator", query="Retail pricing data quality and anomaly commentary",
                           facts={"quality": quality, "business_signals": facts["business_signals"]}, run_id=state["run_id"],
                           prompt=narrative_prompt("Describe observed quality warnings and anomalies in business language, retaining pending or missing information."),
                           policy_version=str(o.governance.mode()["policy_version"])))
        o.emit("tool_completed", run_id=state["run_id"], agent="data_context",
                          latency_ms=(time.perf_counter() - started) * 1000, status="ok")
        o.store.audit("input_evidence", {"input_hash": digest(context), "competitor_hash": digest(feed),
                                         "corpus_version": grounding.corpus_version,
                                         "citations": list(set(narrative.citations + anomaly_narrative.citations))}, actor="system", run_id=state["run_id"])
        return {"context": context, "competitors": feed, "history": history["items"], "family_catalog": family_catalog["items"],
                "quality": quality, "data_narrative": {**narrative.model_dump(), "anomaly_commentary": anomaly_narrative.model_dump()}}

    async def quantitative(self, state):
        self.stage(state, "quantitative")
        o, context, request = self.owner, state["context"], state["request"]
        policy = GovernancePolicy(**o.governance.policy()["thresholds"])
        policy_version = o.governance.mode()["policy_version"]
        learning = o.feedback.states()
        effective = effective_catalog(context["catalog"], policy)
        damping = {p["sku"]: damping_bounds(p, state["history"], policy)[:2] for p in effective}
        report = await o.run_cpu(analyze_catalog, effective, context["sales"], context["inventory"],
                                 state["competitors"], objective=request["objective"], iterations=request["iterations"],
                                 seed=request["seed"], horizon_days=request["horizon_days"],
                                 damping=damping, learning=learning, family_catalog=state["family_catalog"],
                                 run_constraints=request.get("constraints"))
        products = {p["sku"]: p for p in context["catalog"]}
        incidents = {r["sku"]: analyze_stability(products[r["sku"]], r["proposed_price"], state["history"],
                                                 context["catalog"], policy) for r in report["recommendations"]}
        changed = False
        for sku, signal in incidents.items():
            if signal["oscillation"]:
                product = products[sku]
                maximum = min(float(product["max_change_pct"]), policy.maximum_change_pct if policy.maximum_change_pct is not None else 1.)
                step = float(product["current_price"]) * maximum * policy.damping_fraction
                bounded = (max(damping[sku][0], float(product["current_price"]) - step),
                           min(damping[sku][1], float(product["current_price"]) + step))
                changed |= tuple(damping[sku]) != bounded
                damping[sku] = bounded
        if changed:
            report = await o.run_cpu(analyze_catalog, effective, context["sales"], context["inventory"],
                                     state["competitors"], objective=request["objective"], iterations=request["iterations"],
                                     seed=request["seed"], horizon_days=request["horizon_days"],
                                     damping=damping, learning=learning, family_catalog=state["family_catalog"],
                                     run_constraints=request.get("constraints"))
        report["configuration"]["numeric_policy_version"] = policy_version
        learned = learning
        for item in report["recommendations"]:
            item["initial_stability"] = incidents.get(item["sku"], {})
            item["forecast_error_series"] = learned.get(item["sku"], {}).get("error_series", [])
        if not report["recommendations"]:
            raise AnalysisError("No scoped SKU has enough eligible data and a feasible price.", "no_eligible_skus", report["quality"])
        artifact_hash = digest(report)
        narrative = await o.llm.generate(CitedNarrative, role="analyst", query="Interpret elasticity forecast uncertainty and baseline",
                                         facts={"aggregate": report["aggregate"], "configuration": report["configuration"],
                                                "skipped": report["skipped"], "numeric_hash": artifact_hash},
                                         run_id=state["run_id"], prompt=narrative_prompt("Interpret the deterministic forecast. Preserve its uncertainty and limitations."),
                                         policy_version=str(o.governance.mode()["policy_version"]))
        return {"report": report, "numeric_hash": artifact_hash, "quantitative_narrative": narrative.model_dump()}

    async def strategy(self, state):
        self.stage(state, "strategy_reasoning")
        o, report = self.owner, state["report"]
        if digest(report) != state["numeric_hash"]:
            raise RuntimeError("Numeric artifact integrity failed")
        recommendations = report["recommendations"]
        reasons = {}
        # Small sequential batches bound context/output size and gateway pressure.
        batch_size = o.settings_provider().strategy_batch_size
        for offset in range(0, len(recommendations), batch_size):
            batch = recommendations[offset:offset + batch_size]
            facts = [{k: item[k] for k in ("sku", "current_price", "proposed_price", "delta_pct", "confidence",
                                          "confidence_factors", "optimal_price_uncertainty", "elasticity", "impact",
                                          "competitive_gap_pct", "inventory_pressure")}
                     for item in batch]
            result = await o.llm.generate(StrategyNarrative, role="strategist", query="Pricing policy strategy rationale for retail SKUs",
                                          facts={"recommendations": facts, "numeric_hash": state["numeric_hash"]},
                                          run_id=state["run_id"], prompt=strategy_prompt("Explain each supplied SKU's computed price, tradeoffs and uncertainty."),
                                          policy_version=str(o.governance.mode()["policy_version"]))
            if Counter(r.sku for r in result.recommendations) != Counter(i["sku"] for i in batch):
                raise AnalysisError("The grounded strategy omitted or duplicated a SKU.", "strategy_contract_failed")
            reasons.update({r.sku: r.model_dump() for r in result.recommendations})
        enriched = [{**item, "rationale": reasons[item["sku"]]["rationale"], "citations": reasons[item["sku"]]["citations"],
                     "numeric_hash": state["numeric_hash"], "source_as_of": state["context"]["as_of"]}
                    for item in recommendations]
        return {"report": {**report, "recommendations": enriched}}

    async def validation(self, state):
        self.stage(state, "validation_compliance")
        o = self.owner
        policy_version = state["report"]["configuration"]["numeric_policy_version"]
        require_policy(o, policy_version)
        items = await o.governance.register(state["run_id"], state["report"]["recommendations"],
                                            catalog=state["context"]["catalog"], history=state["history"], activate=False)
        narrative = await narrate_verdicts(o, state["run_id"], items, policy_version)
        report = {**state["report"], "kind": "grounded", "type": "grounded_recommendations",
                  "recommendations": items, "executable": False, "summary": state["report"]["aggregate"],
                  "data_narrative": state["data_narrative"], "quantitative_narrative": state["quantitative_narrative"],
                  "validation_narrative": narrative}
        return {"report": report, "item_ids": [i["id"] for i in items],
                "review_ids": [i["id"] for i in items if i["status"] in {"pending_review", "hold", "escalated"}],
                "validation_narrative": narrative}

    async def execution(self, state):
        self.stage(state, "execution")
        o = self.owner
        if not state.get("execution_ready"):
            items = await o.governance.activate(state["run_id"])
            return Command(update={"execution_ready": True,
                           "review_ids": [i["id"] for i in items if i["status"] in {"pending_review", "hold", "escalated"}]},
                           goto="execution")
        await o.governance.dispatch_due(state["item_ids"])
        self._execution_outcomes(state)
        for item_id in state.get("review_ids", []):
            # Stable interrupt order on replay; the resume value grants no authority.
            interrupt({"item_id": item_id, "run_id": state["run_id"], "kind": "human_decision"})
            if not o._resolved(item_id):
                raise RuntimeError("A graph resume is not a durable human decision")
            await o.governance.dispatch_due([item_id])
            self._execution_outcomes(state)
        return Command(update={"report": {**state["report"], "recommendations": o.governance.queue(run_id=state["run_id"])}},
                       goto=END)

    def _execution_outcomes(self, state):
        items = self.owner.governance.queue(run_id=state["run_id"])
        initially_clean = {i["id"] for i in state["report"]["recommendations"] if i.get("compliance", {}).get("status") == "passed"}
        if any(i["status"] in {"unknown", "execution_rejected", "stale"}
               or i["status"] == "blocked" and i["id"] in initially_clean for i in items):
            raise AnalysisError("Execution has rejected, stale or unknown outcomes. Inspect the receipts and reconcile before starting another iteration.",
                                "execution_failed")
