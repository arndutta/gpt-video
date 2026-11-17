"""One/many-SKU what-if requests, shared-engine distributions and saved evidence."""

from platform_app.database import sql

import asyncio
import json
from typing import Literal
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from platform_app.commerce_client import read_competitors
from platform_app.feeds import optional_quotes
from platform_app.storage import now
from platform_app.tools import AnalysisError, simulate_sku
from platform_app.tools import analyze_catalog
from platform_app.governance import GovernancePolicy
from platform_app.governance.stability import damping_bounds
from platform_app.tools.elasticity import estimate_elasticity
from platform_app.tools.monte_carlo import sample_forecasts, summarize, configuration
from platform_app.tools.optimization import baseline_price
from platform_app.tools.refinement import refine_estimate
from platform_app.tools.context import effective_catalog
from platform_app.workflow.schemas import CitedNarrative

router = APIRouter(prefix="/api/scenarios")


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=100)
    candidate_price: str = Field(pattern=r"^\d{1,8}(?:\.\d{1,2})?$")


class BatchScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Candidate] = Field(min_length=1, max_length=500)
    iterations: int = Field(default=1000, ge=100, le=5000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    horizon_days: int = Field(default=14, ge=1, le=90)
    stress: Literal["none", "demand_collapse", "competitor_undercut", "cost_spike"] = "none"
    narrate: bool = False

    @model_validator(mode="after")
    def unique(self):
        if len({i.sku for i in self.items}) != len(self.items):
            raise ValueError("Supply each SKU once")
        return self


class SaveScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    request: BatchScenario


def simulate_many(context, competitors, payload, learning):
    products = {p["sku"]: p for p in context["catalog"]}
    inventory = {i["sku"]: i for i in context["inventory"]}
    reports = []
    optimized = analyze_catalog([{**p, "_stress": payload.stress} for p in context["catalog"]], context["sales"],
                                context["inventory"], competitors, iterations=payload.iterations, seed=payload.seed,
                                horizon_days=payload.horizon_days, damping=context.get("damping"), learning=learning,
                                family_catalog=context.get("family_catalog"))
    optimized = {i["sku"]: i for i in optimized["recommendations"]}
    totals = {m: np.zeros((3, payload.iterations)) for m in ("revenue", "gross_profit", "units")}
    for candidate in payload.items:
        if candidate.sku not in products:
            raise AnalysisError("A scenario SKU is missing from Commerce.", "sku_not_found")
        product = products[candidate.sku]
        state = learning.get(candidate.sku)
        report = simulate_sku(product, context["sales"], context["inventory"], competitors,
                              candidate.candidate_price, payload.iterations, payload.seed, payload.horizon_days,
                              learning=state, stress=payload.stress)
        comparison = optimized.get(candidate.sku)
        report.update(ai_price=comparison["proposed_price"] if comparison else None,
                      ai_forecast=comparison["forecast"] if comparison else None,
                      comparison_scope="Same inputs, stock cap, horizon, seed, uncertainty and stress; optimized balanced candidate")
        reports.append(report)
        sales = [s for s in context["sales"] if s["sku"] == candidate.sku]
        feed = [c for c in competitors if c.get("sku") == candidate.sku]
        estimate = refine_estimate(estimate_elasticity(product, sales), state)
        draws = sample_forecasts({**product, "_stress": payload.stress}, estimate, inventory[candidate.sku], feed,
                                 [float(candidate.candidate_price), float(product["current_price"]), baseline_price(product)],
                                 payload.iterations, payload.seed, payload.horizon_days)
        for metric in totals:
            totals[metric] += draws[metric]
    aggregate = {"sku_count": len(reports), "scope": "Matched scenario SKU set and shared sample shocks",
                 "forecast": {m: summarize(v[0]) for m, v in totals.items()},
                 "current_forecast": {m: summarize(v[1]) for m, v in totals.items()},
                 "baseline_forecast": {m: summarize(v[2]) for m, v in totals.items()},
                 "impact": {m: summarize(v[0] - v[1]) for m, v in totals.items()}}
    return {"items": reports, "aggregate": aggregate, "executable": False,
            "configuration": {**configuration(payload.iterations, payload.seed, payload.horizon_days),
                              "stress": payload.stress, "stress_assumptions": {
                                  "none": "No additional stress", "demand_collapse": "Demand multiplied by 0.5",
                                  "competitor_undercut": "Competitor price down 20%, demand transmission 0.4",
                                  "cost_spike": "Cost multiplied by 1.2"}[payload.stress]}}


async def evaluate(payload, state):
    manager = state.runs
    if manager.busy or manager.stopping:
        raise HTTPException(409, "Another analysis is running. Wait for it to finish.")
    manager.busy = True
    try:
        context, competitors, history, full_catalog = await asyncio.gather(
            state.commerce.context(sku_ids=[i.sku for i in payload.items]),
            optional_quotes(state.settings), state.commerce.all("/price-history"), state.commerce.all("/catalog"))
        policy = GovernancePolicy(**state.governance.policy()["thresholds"])
        context["catalog"] = effective_catalog(context["catalog"], policy)
        context["damping"] = {p["sku"]: damping_bounds(p, history["items"], policy)[:2] for p in context["catalog"]}
        context["family_catalog"] = full_catalog["items"]
        result = await manager.run_cpu(simulate_many, context, competitors, payload, state.feedback.states())
        if payload.narrate:
            try:
                narrative = await state.llm.generate(CitedNarrative, role="narrator", query="Interpret scenario uncertainty and margin risk",
                                                      facts=result, prompt="Explain this what-if forecast without granting approval.",
                                                      policy_version=str(state.governance.mode()["policy_version"]))
                result["narrative"] = narrative.model_dump()
            except Exception as error:
                result["narrative_status"] = getattr(error, "code", "unavailable")
        return result
    except AnalysisError as error:
        raise HTTPException(422, {"code": error.code, "message": str(error), "quality": error.quality}) from None
    finally:
        manager.busy = False


def init_scenarios(store):
    with store.connection() as db:
        db.executescript(sql("scenarios_ddl.sql"))


@router.post("/batch")
async def batch(payload: BatchScenario, request: Request):
    return await evaluate(payload, request.app.state)


@router.post("/saved", status_code=201)
async def save(payload: SaveScenario, request: Request):
    state = request.app.state
    result = await evaluate(payload.request, state)
    item = {"id": str(uuid4()), "name": payload.name, "created_at": now(),
            "request": payload.request.model_dump(), "result": result}
    with state.store.connection() as db:
        db.execute("INSERT INTO saved_scenarios VALUES(?,?,?,?,?)", (item["id"], item["name"], item["created_at"],
                                                                  json.dumps(item["request"]), json.dumps(result)))
        state.store._audit(db, "human", "scenario_saved", None, {"scenario_id": item["id"], "name": item["name"]})
    return item


@router.get("/saved")
def saved(request: Request):
    with request.app.state.store.connection() as db:
        return {"items": [{**dict(r), "request": json.loads(r["request"]), "result": json.loads(r["result"])}
                          for r in db.execute("SELECT * FROM saved_scenarios ORDER BY created_at DESC LIMIT 100")]}
