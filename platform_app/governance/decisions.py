"""Human review, immutable override revisions, and strict bulk eligibility."""

from copy import deepcopy

from platform_app.storage import now

from .bands import assign_band
from .compliance import validate_price
from .models import Decision, GovernanceError
from .repository import revision_hash
from .stability import analyze_stability


REVIEWABLE = {"pending_review", "escalated", "hold", "approved", "canceled"}


def _check_run(service, item, action):
    run = service.store.get_run(item["run_id"])
    if action != "reject" and run and run["status"] in {"failed", "interrupted"}:
        raise GovernanceError("run_requires_resume", "Explicitly resume the failed or interrupted run before recording a fresh approval.")


def _check(item, decision):
    if item is None:
        raise GovernanceError("not_found", "Recommendation does not exist.", 404)
    if item["revision"] != decision.expected_revision:
        raise GovernanceError("stale_revision", "Recommendation revision changed. Refresh before deciding.")
    if item["status"] not in REVIEWABLE:
        raise GovernanceError("decision_conflict", "Recommendation is not awaiting a human decision.")
    if item["status"] == "approved" and decision.action == "approve":
        raise GovernanceError("decision_conflict", "Recommendation has already been approved.")
    if item["compliance"]["status"] != "passed" and decision.action != "reject":
        raise GovernanceError("compliance_veto", "Compliance violations cannot be approved or overridden.")
    if decision.action != "reject" and item["band"] == "escalate" and not decision.reason:
        raise GovernanceError("escalation_reason_required", "Escalation requires a written human override reason.", 422)


async def decide(service, item_id, decision):
    decision = Decision.model_validate(decision)
    if decision.reason:
        decision = decision.model_copy(update={"reason": service.redact(decision.reason)})
    async with service.fence:
        item = service.repo.get(item_id)
        _check(item, decision)
        _check_run(service, item, decision.action)
        if decision.action == "reject":
            with service.store.connection() as db:
                service.repo.state(db, item_id, "rejected")
                service.store._audit(db, "human", "recommendation_rejected", item["run_id"],
                                    {"item_id": item_id, "revision": item["revision"], "reason": decision.reason})
            return service.repo.get(item_id)
        catalog = (await service.commerce.all("/catalog"))["items"]
        history = (await service.commerce.all("/price-history"))["items"]
        product = next((row for row in catalog if row["sku"] == item["sku"]), None)
        with service.store.connection() as db:
            state, policy = service.repo.control(db)
        price = decision.price if decision.action == "override" else item["proposed_price"]
        compliance = validate_price(product, price, catalog, expected_version=item["price_version"], policy=policy,
                                    constraints=item.get("run_constraints"))
        if compliance["status"] != "passed":
            service.store.audit("human_decision_veto", {"item_id": item_id, "compliance": compliance},
                                run_id=item["run_id"])
            code = "stale_price" if any(row["rule"] == "source_price_version" and not row["passed"]
                                       for row in compliance["rules"]) else "compliance_veto"
            raise GovernanceError(code, "The current price or rules no longer permit this decision.")
        stability = analyze_stability(product, price, history, catalog, policy, item.get("forecast_error_series", []))
        for key in ("oscillation", "damping_applied", "novel_market"):
            stability[key] = bool(stability.get(key) or item.get("stability", {}).get(key))
        if stability["cooldown_active"]:
            raise GovernanceError("cooldown", "The minimum interval between price changes has not elapsed.")
        if decision.action == "override":
            if service.override_forecast is None:
                raise GovernanceError("forecast_required", "A price override requires a fresh deterministic forecast.")
            try:
                numeric = await service.override_forecast(item, price, product)
            except GovernanceError:
                raise
            except Exception:
                raise GovernanceError("forecast_failed", "The fresh forecast failed its data or simulation gate. Refresh the run before overriding.", 422) from None
            if not isinstance(numeric, dict) or not numeric.get("forecast"):
                raise GovernanceError("forecast_required", "The override forecast could not be recomputed.")
            # Only explicitly numerical fields can be replaced by the calculator.
            allowed = {"forecast", "current_forecast", "impact", "baseline", "confidence", "confidence_factors",
                       "elasticity", "configuration", "assumptions", "cover_days", "competitive_gap_pct", "competitor_gaps",
                       "optimal_price_uncertainty"}
            revised = deepcopy(item)
            revised.update({key: value for key, value in numeric.items() if key in allowed})
            revised["optimal_price_uncertainty"] = numeric.get("optimal_price_uncertainty")
            current = float(product["current_price"])
            revised.update({"revision": item["revision"] + 1, "proposed_price": price,
                            "delta_absolute": f"{float(price) - current:.2f}",
                            "delta_pct": 100 * (float(price) / current - 1), "compliance": compliance,
                            "compliance_status": "passed", "stability": stability,
                            "override_reason": decision.reason, "prior_revision": item["revision"],
                            "rationale": "Human price override: " + decision.reason, "rationale_origin": "human",
                            "prior_numeric_hash": item.get("numeric_hash"), "numeric_hash_scope": "sku_revision",
                            "product_evidence": product, "policy_evidence": policy.model_dump(),
                            "mode_at_decision": state["mode"], "mode_version": state["version"],
                            "policy_version": state["policy_version"], "created_at": now()})
            revised.update(assign_band(revised, product, compliance, stability, policy))
            revised["numeric_hash"] = revision_hash(revised)
            item = revised
        else:
            current_band = assign_band(item, product, compliance, stability, policy)
            if current_band["band"] == "escalate" and not decision.reason:
                raise GovernanceError("escalation_reason_required", "Current risk conditions require a written human override reason.", 422)
            if (item["policy_version"] != state["policy_version"] or current_band["band"] != item["band"]
                    or compliance != item["compliance"]):
                item = {**item, "revision": item["revision"] + 1, **current_band,
                        "compliance": compliance, "compliance_status": "passed", "stability": stability,
                        "product_evidence": product, "policy_evidence": policy.model_dump(),
                        "mode_at_decision": state["mode"], "mode_version": state["version"],
                        "policy_version": state["policy_version"], "created_at": now()}
        approval = {"kind": "human", "actor": "local-operator", "reason": decision.reason,
                    "approved_at": now(), "mode_version": state["version"]}
        with service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = service.repo.read(db, item_id)
            if current["revision"] != decision.expected_revision or current["status"] not in REVIEWABLE:
                raise GovernanceError("stale_revision", "Recommendation changed during validation.")
            if item["revision"] != decision.expected_revision:
                service.repo.insert(db, item, "approved", approval)
            else:
                service.repo.state(db, item_id, "approved", approval)
            service.store._audit(db, "human", "recommendation_" + decision.action, item["run_id"],
                                {"item_id": item_id, "revision": item["revision"], "price": price,
                                 "reason": decision.reason, "compliance": compliance,
                                 "mode": state["mode"], "mode_version": state["version"]})
    return service.repo.get(item_id)


async def bulk(service, ids, expected_revisions):
    if not ids or len(ids) > 500 or len(set(ids)) != len(ids):
        raise GovernanceError("invalid_bulk", "Supply 1–500 distinct recommendation IDs.", 422)
    # Validate the entire set before performing any decision. Hold the same fence
    # throughout to prevent an automatic timer changing one item halfway through.
    async with service.fence:
        catalog = (await service.commerce.all("/catalog"))["items"]
        history = (await service.commerce.all("/price-history"))["items"]
        products = {item["sku"]: item for item in catalog}
        with service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            state, policy = service.repo.control(db)
            items = [service.repo.read(db, item_id) for item_id in ids]
            changes = {item["sku"]: item["proposed_price"] for item in items if item}
            if len(changes) != len(items):
                raise GovernanceError("invalid_bulk", "Bulk items must have distinct existing SKUs.")
            for item in items:
                revision = expected_revisions.get(item["id"])
                if type(revision) is not int or revision < 1:
                    raise GovernanceError("stale_revision", "Supply the current revision for every bulk item.", 422)
                decision = Decision(action="approve", expected_revision=revision)
                _check(item, decision)
                _check_run(service, item, "approve")
                if item["band"] != "review" or item["confidence"] <= policy.bulk_confidence_threshold:
                    raise GovernanceError("bulk_ineligible", "Bulk approval requires actual Review-band items above the confidence threshold.")
                result = validate_price(products.get(item["sku"]), item["proposed_price"], catalog,
                                        changes=changes, expected_version=item["price_version"], policy=policy,
                                        constraints=item.get("run_constraints"))
                if result["status"] != "passed":
                    raise GovernanceError("compliance_veto", "A bulk candidate is stale or violates a current rule.")
                stability = analyze_stability(products[item["sku"]], item["proposed_price"], history, catalog, policy)
                for signal in ("oscillation", "damping_applied", "novel_market"):
                    stability[signal] = bool(stability.get(signal) or item.get("stability", {}).get(signal))
                if stability["cooldown_active"]:
                    raise GovernanceError("cooldown", "A bulk candidate is inside its minimum change interval.")
                current_band = assign_band(item, products[item["sku"]], result, stability, policy)
                if current_band["band"] != "review":
                    raise GovernanceError("bulk_ineligible", "Current risk conditions no longer classify a bulk candidate in the Review band.")
                if (item["policy_version"] != state["policy_version"] or result != item["compliance"]
                        or current_band["band_reasons"] != item["band_reasons"]):
                    item.update(revision=item["revision"] + 1, **current_band, compliance=result,
                                compliance_status="passed", stability=stability,
                                product_evidence=products[item["sku"]], policy_evidence=policy.model_dump(),
                                mode_at_decision=state["mode"], mode_version=state["version"],
                                policy_version=state["policy_version"], created_at=now())
            for item in items:
                approval = {"kind": "human", "actor": "local-operator", "reason": "Review-band bulk approval",
                            "approved_at": now(), "mode_version": state["version"]}
                if item["revision"] != expected_revisions[item["id"]]:
                    service.repo.insert(db, item, "approved", approval)
                else:
                    service.repo.state(db, item["id"], "approved", approval)
                service.store._audit(db, "human", "recommendation_bulk_approved", item["run_id"],
                                    {"item_id": item["id"], "revision": item["revision"], "mode_version": state["version"],
                                     "policy_version": state["policy_version"], "compliance": item["compliance"],
                                     "band_reasons": item["band_reasons"]})
    return [service.repo.get(item_id) for item_id in ids]
