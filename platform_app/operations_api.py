"""Shared human/automatic control APIs; durable governance owns write authorization."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from platform_app.governance import Decision, GovernancePolicy, ModeUpdate
from platform_app.loop import LoopRequest

router = APIRouter(prefix="/api")


class BulkDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=500)
    expected_revisions: dict[str, int]


class Revert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, strict=True)


@router.get("/control")
def control(request: Request):
    return {**request.app.state.governance.mode(), "loop": request.app.state.loop.state()}


@router.patch("/control/mode")
async def mode(payload: ModeUpdate, request: Request):
    result = await request.app.state.governance.set_mode(payload.mode, payload.hold_seconds)
    return {**result, "loop": request.app.state.loop.state()}


@router.post("/control/kill")
async def kill(request: Request):
    state = request.app.state
    # Set the dispatch fence before acknowledging scheduling/analysis cancellation.
    result = await state.governance.kill()
    await state.loop.stop("kill_switch")
    await state.workflow.cancel_active()
    return {**result, "loop": state.loop.state(), "receipts": await state.governance.reconcile()}


@router.get("/policy")
def policy(request: Request):
    return request.app.state.governance.policy()


@router.patch("/policy")
async def update_policy(payload: GovernancePolicy, request: Request):
    return await request.app.state.governance.update_policy(payload.model_dump(exclude_unset=True))


@router.get("/recommendations")
def recommendations(request: Request, run_id: str | None = None, status: str | None = None,
                    band: str | None = None, automatic: bool | None = None):
    return {"items": request.app.state.governance.queue(run_id=run_id, status=status, band=band, automatic=automatic)}


@router.post("/recommendations/bulk")
async def bulk(payload: BulkDecision, request: Request):
    state = request.app.state
    items = await state.governance.bulk(payload.ids, payload.expected_revisions)
    await state.governance.dispatch_due(payload.ids)
    for run_id in {i["run_id"] for i in items}:
        await state.workflow.decision_recorded(run_id)
    return {"items": [state.governance.get(i) for i in payload.ids]}


@router.get("/recommendations/{item_id}")
def recommendation(item_id: str, request: Request):
    item = request.app.state.governance.get(item_id)
    if not item:
        raise HTTPException(404, "Recommendation not found")
    return {**item, "revisions": request.app.state.governance.history(item_id)}


@router.post("/recommendations/{item_id}/decision")
async def decision(item_id: str, payload: Decision, request: Request):
    state = request.app.state
    item = await state.governance.decide(item_id, payload)
    await state.governance.dispatch_due([item_id])
    await state.workflow.decision_recorded(item["run_id"])
    return state.governance.get(item_id)


@router.post("/recommendations/{item_id}/revert")
async def revert(item_id: str, payload: Revert, request: Request):
    item = recommendation(item_id, request)
    if item["revision"] != payload.expected_revision:
        raise HTTPException(409, "The recommendation changed. Refresh before reverting.")
    return await request.app.state.governance.revert(item_id)


@router.post("/runs/{run_id}/resume", status_code=202)
async def resume(run_id: str, request: Request):
    try:
        return await request.app.state.workflow.resume(run_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from None


@router.get("/loop")
def loop(request: Request):
    return request.app.state.loop.state()


@router.get("/loop/history")
def loop_history(request: Request):
    return {"items": request.app.state.loop.history()}


@router.post("/loop", status_code=202)
async def start_loop(payload: LoopRequest, request: Request):
    health = await request.app.state.commerce.get("/health")
    if health.get("status") != "ok" or not health.get("seeded"):
        raise HTTPException(503, "Commerce must be healthy and seeded before starting a loop.")
    try:
        return request.app.state.loop.start(payload)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(409, str(error)) from None


@router.post("/loop/stop")
async def stop_loop(request: Request):
    return await request.app.state.loop.stop()
