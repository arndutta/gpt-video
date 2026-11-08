"""Browser-facing foundation APIs. All price-changing capabilities remain unavailable."""

import asyncio
from collections import Counter
import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from platform_app.commerce_client import CommerceUnavailable, read_competitors
from platform_app.config import RunRequest, ScenarioRequest, Settings, SettingsUpdate, tls_context
from platform_app.tools import AnalysisError, simulate_sku

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(request: Request):
    state = request.app.state
    try:
        result = await state.commerce.get("/health")
        ready = result.get("status") == "ok" and result.get("seeded", False)
        commerce = {"status": "ok" if ready else "unavailable",
                    "detail": "Ready" if ready else "Seed the Commerce demo data first."}
    except CommerceUnavailable as error:
        ready, commerce = False, {"status": "unavailable", "detail": str(error)}
    return {"status": "ok" if ready else "degraded", "service": "pricing-platform",
            "commerce": commerce, "mode": "supervised", "loop": {"running": False},
            "tls_verification_disabled": not state.settings.verify_tls,
            "gateway": {"configured": bool(state.settings.gateway_url),
                        "status": "configured" if state.settings.gateway_url else "unconfigured",
                        "verified": False},
            "capabilities": {"quantitative_preview": ready, "grounded_recommendations": False,
                             "price_execution": False, "continuous_loop": False}}


@router.get("/catalog")
async def catalog(request: Request, category: str | None = None, q: str | None = None,
                  limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    if q:
        result = await request.app.state.commerce.all("/catalog", category=category)
        needle = q.casefold()
        items = [item for item in result["items"] if needle in item["name"].casefold()
                 or needle in item["sku"].casefold()]
        return {"items": items[offset:offset + limit], "total": len(items), "as_of": result["as_of"]}
    return await request.app.state.commerce.get("/catalog", category=category, limit=limit, offset=offset)


@router.get("/catalog/summary")
async def summary(request: Request):
    catalog, inventory = await asyncio.gather(request.app.state.commerce.all("/catalog"),
                                             request.app.state.commerce.all("/inventory"))
    counts = Counter(item["category"] for item in catalog["items"])
    return {"sku_count": catalog["total"], "categories": [
        {"name": name, "sku_count": count} for name, count in sorted(counts.items())],
        "inventory_units": sum(item["on_hand"] for item in inventory["items"])}


@router.get("/settings")
def settings(request: Request):
    return request.app.state.settings.public()


@router.patch("/settings")
async def update_settings(update: SettingsUpdate, request: Request):
    current = request.app.state.settings
    fields = update.model_dump(exclude_unset=True)
    if fields.get("gateway_url") == "":
        fields["gateway_url"] = None
    # A cleared form field preserves the in-memory key; no response ever reads it back.
    if not fields.get("api_key") or not fields["api_key"].get_secret_value():
        fields.pop("api_key", None)
    values = {name: getattr(current, name) for name in Settings.model_fields}
    values.update(fields)
    try:
        candidate = Settings(**values)
        tls_context(candidate)
    except (ValidationError, ValueError, OSError):
        raise HTTPException(422, "Invalid settings. Check the URL, port, corporate CA, and TLS permission.") from None
    request.app.state.store.audit("settings_changed", {"fields": sorted(fields)})
    # No await between validation and publication: readers get one complete snapshot.
    request.app.state.settings = candidate
    request.app.state.runs.settings = candidate
    return candidate.public()


@router.get("/runs")
def list_runs(request: Request):
    return {"items": request.app.state.store.list_runs()}


@router.post("/runs", status_code=202)
async def create_run(payload: RunRequest, request: Request):
    status = await request.app.state.commerce.get("/health")
    if status.get("status") != "ok" or not status.get("seeded"):
        raise HTTPException(503, "Commerce has no data. Run the demo data generator first.")
    try:
        result = request.app.state.runs.start(payload)
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from None
    return {"id": result["id"], "status": result["status"]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request):
    result = request.app.state.store.get_run(run_id)
    if not result:
        raise HTTPException(404, "Preview run not found")
    return result


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    get_run(run_id, request)

    async def events():
        previous = None
        while not await request.is_disconnected():
            run = request.app.state.store.get_run(run_id)
            event = {key: run[key] for key in ["id", "status", "stage", "completed_at", "error"]}
            encoded = json.dumps(event)
            if encoded != previous:
                yield f"event: progress\ndata: {encoded}\n\n"
                previous = encoded
            if run["status"] in {"completed", "failed", "interrupted"}:
                return
            await asyncio.sleep(.25)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/scenarios/simulate")
async def scenario(payload: ScenarioRequest, request: Request):
    manager = request.app.state.runs
    if manager.busy or manager.stopping:
        raise HTTPException(409, "Another preview is running. Wait for it to finish.")
    manager.busy = True
    try:
        context, competitors = await asyncio.gather(
            request.app.state.commerce.context(sku_ids=[payload.sku]),
            asyncio.to_thread(read_competitors, request.app.state.settings.data_dir))
        if not context["catalog"]:
            raise HTTPException(404, "SKU not found")
        report = await manager.run_cpu(simulate_sku, context["catalog"][0], context["sales"],
                                       context["inventory"], competitors, payload.candidate_price,
                                       iterations=payload.iterations, seed=payload.seed,
                                       horizon_days=payload.horizon_days)
        return {**report, "kind": "quantitative_preview"}
    except AnalysisError as error:
        raise HTTPException(422, {"code": error.code, "message": str(error), "quality": error.quality}) from None
    except (ValueError, OSError):
        raise HTTPException(422, "The competitor feed is invalid. Regenerate demo data.") from None
    finally:
        manager.busy = False


@router.get("/audit")
def audit(request: Request, limit: int = Query(100, ge=1, le=1000)):
    return {"items": request.app.state.store.list_audit(limit)}
