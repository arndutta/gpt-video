"""Publish fully evaluated, immutable recommendations before approval."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from platform_app.storage import now
from platform_app.constraints import constraints_model

from .bands import assign_band
from .compliance import validate_price
from .stability import analyze_stability


def disposition(item, state, policy):
    if item["compliance"]["status"] != "passed":
        return "blocked", None, None
    if item.get("forecast") is None:
        return "blocked", None, None
    if item["band"] == "escalate":
        return "escalated", None, None
    if state["mode"] == "supervised" or state["mode"] == "assisted" and item["band"] == "review":
        return "pending_review", None, None
    if state["mode"] == "autonomous" and item["band"] == "review":
        until = datetime.now(timezone.utc) + timedelta(seconds=policy.hold_seconds)
        return "hold", None, until.isoformat()
    approval = {"kind": "automatic", "actor": "system", "reason": "Eligible Auto-approve band",
                "approved_at": now(), "mode_version": state["version"]}
    return "approved", approval, None


async def register(service, run_id, recommendations, catalog=None, history=None, activate=True):
    # An unscoped read is deliberate: a scoped run must include unselected family
    # siblings in ladder validation. These snapshots are evidence, not a catalog mirror.
    full_catalog = (await service.commerce.all("/catalog"))["items"]
    history = history if history is not None else (await service.commerce.all("/price-history"))["items"]
    products = {product["sku"]: product for product in full_catalog}
    run = service.store.get_run(run_id)
    requested = (run or {}).get("request", {}).get("constraints")
    run_constraints = constraints_model(requested).model_dump() if requested is not None else None
    changes = {item["sku"]: item["proposed_price"] for item in recommendations}
    async with service.fence:
        with service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            state, policy = service.repo.control(db)
            ids = []
            for recommendation in recommendations:
                item_id = str(uuid5(NAMESPACE_URL, f"pricing:{run_id}:{recommendation['sku']}"))
                if service.repo.read(db, item_id):
                    ids.append(item_id)
                    continue
                item = deepcopy(recommendation)
                # The run request is the authority; a model-produced item cannot
                # delete or replace user-specified deterministic limits.
                item["run_constraints"] = run_constraints
                product = products.get(item["sku"])
                compliance = validate_price(product, item["proposed_price"], full_catalog, changes=changes,
                                            expected_version=item["price_version"], policy=policy, request=item,
                                            constraints=run_constraints)
                stability = analyze_stability(product, item["proposed_price"], history, full_catalog, policy,
                                              item.get("forecast_error_series", [])) if product else {
                    "oscillation": False, "novel_market": True, "cooldown_active": False,
                    "damping_applied": False, "convergence_status": "pending", "signals": ["unknown_sku"]}
                # The optimizer retains the original incident before damping; a
                # smaller selected move must not clear that incident at banding.
                prior = {**item.get("stability", {}), **item.get("initial_stability", {})}
                for key in ("oscillation", "damping_applied", "novel_market"):
                    stability[key] = bool(stability.get(key) or prior.get(key))
                band = assign_band(item, product, compliance, stability, policy) if product else {
                    "band": "escalate", "band_reasons": [{"code": "unknown_sku", "passed": False,
                    "actual": None, "threshold": "known SKU", "message": "SKU is absent from Commerce."}]}
                item.update({"id": item_id, "revision": 1, "run_id": run_id, "created_at": now(),
                             "compliance": compliance, "compliance_status": compliance["status"],
                             "stability": stability, **band, "mode_at_decision": state["mode"],
                             "mode_version": state["version"], "policy_version": state["policy_version"],
                             "executable": False, "product_evidence": product,
                             "history_evidence": [row for row in history if row.get("sku") == item["sku"]],
                             "policy_evidence": policy.model_dump()})
                status, approval, hold = disposition(item, state, policy) if activate else ("draft", None, None)
                ids.append(service.repo.insert(db, item, status, approval, hold))
                service.store._audit(db, "system", "recommendation_validated", run_id,
                                    {"item_id": item_id, "revision": 1, "sku": item["sku"],
                                     "compliance": compliance, "stability": stability, **band,
                                     "mode": state["mode"], "mode_version": state["version"],
                                     "policy_version": state["policy_version"], "disposition": status})
    return [service.repo.get(item_id) for item_id in ids]


async def activate(service, run_id):
    async with service.fence:
        with service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            state, policy = service.repo.control(db)
            rows = service.repo.queue(run_id=run_id, status="draft")
            for item in rows:
                if item["policy_version"] != state["policy_version"]:
                    service.repo.state(db, item["id"], "stale")
                    continue
                status, approval, hold = disposition(item, state, policy)
                if item["mode_version"] != state["version"]:
                    item = {**item, "revision": item["revision"] + 1,
                            "mode_at_decision": state["mode"], "mode_version": state["version"],
                            "policy_evidence": policy.model_dump()}
                    service.repo.insert(db, item, status, approval, hold)
                else:
                    service.repo.state(db, item["id"], status, approval, hold)
                service.store._audit(db, "system", "recommendation_activated", run_id,
                                    {"item_id": item["id"], "revision": item["revision"], "status": status})
    return service.repo.queue(run_id=run_id)
