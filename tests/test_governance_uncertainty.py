"""Human candidates cannot inherit a prior optimizer's price-argmax interval."""

from copy import deepcopy

import pytest

from governance_helpers import setup_governance
from platform_app.commerce_client import read_competitors
from platform_app.governance.compliance import validate_price
from platform_app.tools import analyze_catalog, simulate_sku


async def numerical_governance(directory, omit_uncertainty):
    service, commerce, _ = setup_governance(directory)
    context = await commerce.context()
    competitors = read_competitors(directory)
    report = analyze_catalog(context["catalog"], context["sales"], context["inventory"], competitors,
                             iterations=100, seed=42)
    products = {product["sku"]: product for product in context["catalog"]}
    # An increase is also revertible under the original symmetric Commerce cap.
    original = next(item for item in report["recommendations"]
                    if float(item["proposed_price"]) > float(item["current_price"])
                    and validate_price(products[item["sku"]], item["proposed_price"], context["catalog"])["status"] == "passed")
    assert original["optimal_price_uncertainty"]

    async def fresh_candidate(item, price, product):
        fresh = await commerce.context(sku_ids=[item["sku"]])
        numeric = simulate_sku(product, fresh["sales"], fresh["inventory"], competitors, price,
                               iterations=100, seed=42)
        assert numeric["optimal_price_uncertainty"] is None
        assert numeric["confidence_factors"]["selection_status"] == "not_evaluated_for_arbitrary_candidate"
        if omit_uncertainty:
            numeric.pop("optimal_price_uncertainty")
        return numeric

    service.override_forecast = fresh_candidate
    [item] = await service.register("numeric-run", [original])
    return service, item


@pytest.mark.parametrize("omit_uncertainty", [False, True])
async def test_override_clears_old_argmax_interval_and_preserves_original_evidence(tmp_path, omit_uncertainty):
    service, original = await numerical_governance(tmp_path, omit_uncertainty)
    old_interval = deepcopy(original["optimal_price_uncertainty"])
    changed = await service.decide(original["id"], {"action": "override", "expected_revision": original["revision"],
        "price": original["current_price"], "reason": "Retain the source price after reviewing its fresh forecast."})
    assert changed["optimal_price_uncertainty"] is None
    assert changed["confidence_factors"]["selection_status"] == "not_evaluated_for_arbitrary_candidate"
    assert changed["proposed_price"] == original["current_price"]
    assert service.history(original["id"])[0]["evidence"]["optimal_price_uncertainty"] == old_interval


@pytest.mark.parametrize("omit_uncertainty", [False, True])
async def test_revert_uses_fresh_candidate_uncertainty_without_editing_original_optimizer_record(tmp_path, omit_uncertainty):
    service, original = await numerical_governance(tmp_path, omit_uncertainty)
    old_interval = deepcopy(original["optimal_price_uncertainty"])
    await service.decide(original["id"], {"action": "approve", "expected_revision": original["revision"],
                                         "reason": "Reviewed the synthetic numeric proposal."})
    await service.dispatch_due([original["id"]])
    assert service.get(original["id"])["status"] == "applied"
    reverted = await service.revert(original["id"])
    assert reverted["status"] == "applied" and reverted["optimal_price_uncertainty"] is None
    assert reverted["confidence_factors"]["selection_status"] == "not_evaluated_for_arbitrary_candidate"
    assert reverted["proposed_price"] == original["current_price"]
    assert service.get(original["id"])["optimal_price_uncertainty"] == old_interval
    assert service.history(original["id"])[0]["evidence"]["optimal_price_uncertainty"] == old_interval
