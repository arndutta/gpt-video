"""Run-specific bounds remain absolute through human edits and automatic execution."""

from copy import deepcopy
from decimal import Decimal

import pytest

from governance_helpers import recommendation, setup_governance
from platform_app.config import RunRequest
from platform_app.constraints import RunConstraints, apply_run_constraints
from platform_app.governance import GovernanceError
from platform_app.governance.compliance import validate_price
from platform_app.tools.optimization import feasible_prices
from test_analysis import fixtures


@pytest.mark.parametrize("payload", [
    {"max_change_pct": True}, {"max_change_pct": "0.1"}, {"max_change_pct": -0.1},
    {"max_change_pct": 1.1}, {"max_change_pct": float("nan")}, {"unknown": 1},
    {"category_floors": {"Beverages": 10.0}}, {"category_floors": {"Beverages": "0.00"}},
    {"category_ceilings": {"Beverages": "10.001"}}, {"category_ceilings": {"Beverages": "NaN"}},
    {"category_floors": {"": "10.00"}}, {"category_floors": {str(i): "1.00" for i in range(51)}},
    {"category_floors": {"Beverages": "10.00"}, "category_ceilings": {"Beverages": "9.99"}},
])
def test_run_constraints_reject_invalid_or_unbounded_inputs(payload):
    with pytest.raises(ValueError):
        RunRequest(constraints=payload)


def test_empty_explicit_sku_scope_cannot_expand_to_the_entire_catalog():
    with pytest.raises(ValueError):
        RunRequest(sku_ids=[])


def test_candidate_grid_uses_run_constraints_without_weakening_commerce_or_mutation():
    product, _, _, _ = fixtures()
    original = deepcopy(product)
    constraints = RunConstraints(max_change_pct=.04, category_floors={"Beverages": "9.90"},
                                 category_ceilings={"Beverages": "10.20"})
    [effective] = apply_run_constraints([product], constraints)
    candidates = feasible_prices(effective)
    assert product == original and candidates
    assert all(9.90 <= price <= 10.20 for price in candidates)
    assert all(abs(price / 10 - 1) <= .04 for price in candidates)
    assert all(validate_price(product, str(price), [product], constraints=constraints)["status"] == "passed"
               for price in candidates)
    [looser] = apply_run_constraints([product], {"max_change_pct": .8,
        "category_floors": {"Beverages": "1.00"}, "category_ceilings": {"Beverages": "99.00"}})
    assert looser["max_change_pct"] == product["max_change_pct"]
    assert looser["min_price"] == "6.00" and looser["max_price"] == "18.00"


@pytest.mark.parametrize("mode", ["supervised", "assisted", "autonomous"])
async def test_run_cap_is_bound_to_request_and_cannot_be_deleted_by_recommendation_or_override(tmp_path, mode):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode(mode, hold_seconds=3600)
    await service.update_policy({"confidence_threshold": 1.})
    request = RunRequest(kind="grounded", constraints={"max_change_pct": .03})
    run = service.store.create_run(request.model_dump())
    service.store.update_run(run["id"], "running", "execution")
    product = (await commerce.all("/catalog"))["items"][0]
    proposed = recommendation(product)
    proposed["run_constraints"] = {"max_change_pct": 1.}  # Untrusted model metadata has no authority.
    [item] = await service.register(run["id"], [proposed])
    assert item["run_constraints"]["max_change_pct"] == .03 and item["compliance_status"] == "passed"
    bad_price = f"{Decimal(product['current_price']) * Decimal('1.05'):.2f}"
    with pytest.raises(GovernanceError, match="current price or rules"):
        await service.decide(item["id"], {"action": "override", "expected_revision": 1,
            "price": bad_price, "reason": "A human cannot waive a run constraint."})
    assert service.get(item["id"])["revision"] == 1
    assert (await commerce.all("/price-history"))["total"] == 0


async def test_automatic_registration_cannot_push_a_candidate_outside_run_bounds(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode("assisted")
    run = service.store.create_run(RunRequest(kind="grounded", constraints={"max_change_pct": .01}).model_dump())
    service.store.update_run(run["id"], "running", "execution")
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register(run["id"], [recommendation(product, factor="1.02")])
    assert item["status"] == "blocked" and item["band"] == "escalate"
    assert not next(rule for rule in item["compliance"]["rules"] if rule["rule"] == "run_max_change")["passed"]
    assert not await service.dispatch_due()
    assert (await commerce.all("/price-history"))["total"] == 0


async def test_revert_cannot_restore_price_below_original_run_floor(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    product = (await commerce.all("/catalog"))["items"][0]
    floor = f"{Decimal(product['current_price']) + Decimal('0.01'):.2f}"
    run = service.store.create_run(RunRequest(kind="grounded", constraints={
        "category_floors": {product["category"]: floor}}).model_dump())
    service.store.update_run(run["id"], "running", "execution")
    [item] = await service.register(run["id"], [recommendation(product)])
    await service.decide(item["id"], {"action": "approve", "expected_revision": item["revision"]})
    await service.dispatch_due()
    assert service.get(item["id"])["status"] == "applied"
    with pytest.raises(GovernanceError, match="current rule"):
        await service.revert(item["id"])
    assert (await commerce.all("/price-history"))["total"] == 1
