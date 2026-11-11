"""A revert is a new, independently checked compensating price change."""

from copy import deepcopy
from uuid import uuid4

from platform_app.storage import now

from .bands import assign_band
from .compliance import validate_price
from .models import GovernanceError
from .repository import revision_hash
from .stability import analyze_stability


async def revert(service, item_id):
    async with service.fence:
        original = service.repo.get(item_id)
        if original is None:
            raise GovernanceError("not_found", "Recommendation does not exist.", 404)
        execution = original.get("execution") or {}
        if original["status"] != "applied" or execution.get("status") != "applied":
            raise GovernanceError("not_revertible", "Only a confirmed applied price can be reverted.")
        with service.store.connection() as db:
            children = db.execute("SELECT evidence FROM recommendations WHERE sku=?", (original["sku"],)).fetchall()
            import json
            for child in children:
                linked = json.loads(child["evidence"])
                if linked.get("reverts_item_id") == item_id:
                    return service.repo.read(db, linked["id"])
        catalog = (await service.commerce.all("/catalog"))["items"]
        history = (await service.commerce.all("/price-history"))["items"]
        product = next((row for row in catalog if row["sku"] == original["sku"]), None)
        if product is None or product["price_version"] != execution["new_version"]:
            raise GovernanceError("stale_price", "The SKU has changed since this push; refresh before planning a new price.")
        price = execution["prior_price"]
        with service.store.connection() as db:
            state, policy = service.repo.control(db)
        compliance = validate_price(product, price, catalog, expected_version=execution["new_version"], policy=policy,
                                    constraints=original.get("run_constraints"))
        if compliance["status"] != "passed":
            service.store.audit("revert_veto", {"item_id": item_id, "compliance": compliance}, run_id=original["run_id"])
            raise GovernanceError("compliance_veto", "The prior price violates a current rule and cannot be restored.")
        stability = analyze_stability(product, price, history, catalog, policy)
        if stability["cooldown_active"]:
            raise GovernanceError("cooldown", "The minimum change interval prevents this revert until it expires.")
        if service.override_forecast is None:
            raise GovernanceError("forecast_required", "Revert requires a fresh deterministic forecast.")
        try:
            numeric = await service.override_forecast(original, price, product)
        except GovernanceError:
            raise
        except Exception:
            raise GovernanceError("forecast_failed", "The fresh revert forecast failed its data or simulation gate. Refresh the run.", 422) from None
        if not isinstance(numeric, dict) or not numeric.get("forecast"):
            raise GovernanceError("forecast_required", "The revert forecast could not be recomputed.")
        item = deepcopy(original)
        allowed = {"forecast", "current_forecast", "impact", "baseline", "confidence", "confidence_factors",
                   "elasticity", "configuration", "assumptions", "cover_days", "competitive_gap_pct", "competitor_gaps",
                   "optimal_price_uncertainty"}
        item.update({key: value for key, value in numeric.items() if key in allowed})
        item["optimal_price_uncertainty"] = numeric.get("optimal_price_uncertainty")
        current = float(product["current_price"])
        item.update({"id": str(uuid4()), "revision": 1, "created_at": now(),
                     "reverts_item_id": item_id, "reverts_batch_key": execution["batch_key"],
                     "current_price": product["current_price"], "price_version": product["price_version"],
                     "proposed_price": price, "delta_absolute": f"{float(price) - current:.2f}",
                     "delta_pct": 100 * (float(price) / current - 1), "compliance": compliance,
                     "compliance_status": "passed", "stability": stability, "product_evidence": product,
                     "mode_at_decision": state["mode"], "mode_version": state["version"],
                     "policy_version": state["policy_version"], "policy_evidence": policy.model_dump(),
                     "rationale": "Human-requested compensating change restoring the prior approved price.",
                     "rationale_origin": "human", "prior_numeric_hash": original.get("numeric_hash"),
                     "numeric_hash_scope": "sku_revision"})
        item.update(assign_band(item, product, compliance, stability, policy))
        item["numeric_hash"] = revision_hash(item)
        approval = {"kind": "human", "actor": "local-operator", "reason": "Revert confirmed prior price",
                    "approved_at": now(), "mode_version": state["version"]}
        with service.store.connection() as db:
            service.repo.insert(db, item, "approved", approval)
            service.store._audit(db, "human", "revert_requested", item["run_id"],
                                {"item_id": item["id"], "reverts_item_id": item_id, "prior_batch": execution["batch_key"],
                                 "restored_price": price, "compliance": compliance})
    await service.dispatch_due([item["id"]])
    return service.repo.get(item["id"])
