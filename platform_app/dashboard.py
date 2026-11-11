"""Read-only, scoped metrics with explicit observation denominators and pending states."""

from collections import Counter
import json
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from platform_app.outcomes import summarize_outcomes

router = APIRouter(prefix="/api")


def audit_items(store, *, automatic=False, run_id=None, sku=None, limit=1000):
    clauses, params = [], []
    if automatic:
        clauses.append("a.actor='system'")
    if run_id:
        clauses.append("a.run_id=?")
        params.append(run_id)
    if sku:
        clauses.append("(json_extract(a.detail,'$.sku')=? OR json_extract(a.detail,'$.item_id') IN "
                       "(SELECT id FROM recommendations WHERE sku=?) OR json_extract(a.detail,'$.batch_key') IN "
                       "(SELECT o.batch_key FROM price_outbox o,json_each(o.item_refs) j WHERE json_extract(j.value,'$.sku')=?))")
        params.extend([sku, sku, sku])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with store.connection() as db:
        rows = db.execute("SELECT a.* FROM audit a" + where + " ORDER BY a.id DESC LIMIT ?", [*params, limit]).fetchall()
    return [{**dict(r), "detail": json.loads(r["detail"])} for r in rows]


@router.get("/audit/export")
def export(request: Request, automatic: bool = False, run_id: str | None = None, sku: str | None = None):
    items = audit_items(request.app.state.store, automatic=automatic, run_id=run_id, sku=sku, limit=10000)
    return JSONResponse({"items": items, "limit": 10000, "scope": "matching append-only events"},
                        headers={"Content-Disposition": 'attachment; filename="pricing-audit.json"'})


@router.get("/dashboard")
def dashboard(request: Request, run_id: str | None = None):
    state = request.app.state
    runs = state.store.list_runs()
    selected = next((r for r in runs if (not run_id or r["id"] == run_id)
                     and r["status"] in {"completed", "awaiting_review"}), None)
    run = state.store.get_run(selected["id"]) if selected else None
    report = (run or {}).get("result") or {}
    items = state.governance.queue(run_id=run["id"]) if run else []
    bands = Counter(i["band"] for i in items)
    decisions = {"approved": 0, "rejected": 0, "overridden": 0, "automatic": 0, "total": 0}
    for i in items:
        approval = i.get("approval") or {}
        kind = approval.get("kind", approval.get("approval_kind"))
        if kind == "automatic":
            decisions["automatic"] += 1
    human = {}
    for event in audit_items(state.store, run_id=(run or {}).get("id"), limit=10000) if run else []:
        if event["actor"] != "human" or "item_id" not in event["detail"]:
            continue
        action = event["action"]
        if action in {"recommendation_approve", "recommendation_bulk_approved", "recommendation_override", "recommendation_rejected"}:
            human.setdefault(event["detail"]["item_id"], action)
    decisions["approved"] = sum(a in {"recommendation_approve", "recommendation_bulk_approved"} for a in human.values())
    decisions["overridden"] = sum(a == "recommendation_override" for a in human.values())
    decisions["rejected"] = sum(a == "recommendation_rejected" for a in human.values())
    decisions["total"] = len(human)
    aggregate = report.get("aggregate", {})
    forecast = {"revenue": aggregate.get("forecast", {}).get("revenue", {}).get("mean"),
                "gross_profit": aggregate.get("forecast", {}).get("gross_profit", {}).get("mean"),
                "baseline_revenue": aggregate.get("baseline_forecast", {}).get("revenue", {}).get("mean"),
                "baseline_gross_profit": aggregate.get("baseline_forecast", {}).get("gross_profit", {}).get("mean")}
    outcomes = [o for o in state.feedback.outcomes() if run and o["run_id"] == run["id"]]
    realized = summarize_outcomes(items, outcomes)
    learned = state.feedback.states()
    series = [value for sku, value in learned.items() if any(i["sku"] == sku for i in items)]
    causes = Counter(reason.get("code", reason.get("rule", "escalation")) for i in items if i["band"] == "escalate"
                     for reason in i.get("band_reasons", []) if reason.get("passed") is False
                     and reason.get("code") in {"compliance", "margin_proximity", "volatility", "oscillation", "novel_market"})
    return {"run_id": (run or {}).get("id"), "scope": (run or {}).get("request", {}).get("category") or "Selected run SKU scope",
            "horizon_days": (run or {}).get("request", {}).get("horizon_days"),
            "recommendations": len(items) or len(report.get("recommendations", [])), "bands": dict(bands),
            "decisions": decisions, "forecast": forecast, "realized": realized,
            "stability": {"oscillating_skus": sum(bool(i.get("stability", {}).get("oscillation")) for i in items),
                          "damped_skus": sum(bool(i.get("stability", {}).get("damping_applied")) for i in items),
                          "error_trend": "widening" if any(s.get("convergence") == "widening" for s in series) else
                                         "pending" if not series else "stable_or_insufficient", "series": series},
            "mode_history": [a for a in audit_items(state.store) if a["action"] in {"mode_changed", "kill_switch"}],
            "escalation_causes": [{"cause": cause, "count": count} for cause, count in causes.items()],
            "limitations": ["Forecasts and conventional baseline are model comparisons, not realized counterfactual uplift.",
                            "Acceptance and escalation precision require human decisions and labels.",
                            "Missing or immature outcomes remain pending; cost uses the decision-time catalog snapshot."]}


@router.get("/feedback")
def feedback(request: Request):
    return {"items": request.app.state.feedback.outcomes(), "learning": request.app.state.feedback.states()}


@router.post("/feedback/refresh")
async def refresh_feedback(request: Request):
    return await request.app.state.feedback.refresh(request.app.state.governance.queue())


@router.get("/monitor")
def monitor(request: Request):
    snapshot = request.app.state.llm.snapshot()
    return {**snapshot, "active_calls": snapshot.get("active_calls", snapshot.get("active", 0)),
            "input_tokens": snapshot.get("tokens_in", 0), "output_tokens": snapshot.get("tokens_out", 0),
            "pricing_source": snapshot.get("cost_source")}
