"""Runtime policy and stability bounds constrain the actual numeric candidate set."""

from copy import deepcopy
from decimal import Decimal

import pytest

from platform_app.governance import GovernancePolicy
from platform_app.governance.compliance import validate_price
from platform_app.governance.stability import damping_bounds
from platform_app.tools import analyze_catalog
from platform_app.tools.context import business_context, effective_catalog
from platform_app.tools.optimization import feasible_prices
from test_analysis import fixtures


def test_effective_policy_uses_stricter_margin_change_and_lcm_ticks_without_mutation():
    product, _, _, _ = fixtures(current=9.99)
    product["rounding_increment"] = "0.03"
    original = deepcopy(product)
    policy = GovernancePolicy(minimum_margin_pct=.5, maximum_change_pct=.03, rounding_increment="0.05")
    [effective] = effective_catalog([product], policy)
    assert product == original and effective["rounding_increment"] == "0.15"
    candidates = feasible_prices(effective)
    assert candidates
    for price in candidates:
        proposed = Decimal(str(price))
        assert proposed % Decimal("0.03") == 0 and proposed % Decimal("0.05") == 0
        assert abs(proposed / Decimal(product["current_price"]) - 1) <= Decimal("0.03")
        assert (proposed - Decimal(product["cost"])) / proposed >= Decimal("0.5")
        assert validate_price(product, str(price), [product], policy=policy)["status"] == "passed"


def test_strict_policy_and_existing_oscillation_bound_the_selected_forecast():
    product, sales, inventory, competitor = fixtures()
    policy = GovernancePolicy(maximum_change_pct=.04, damping_fraction=.35)
    [effective] = effective_catalog([product], policy)
    history = [{"id": i, "sku": product["sku"], "prior_price": prior, "new_price": new,
                "applied_at": f"2026-11-0{i + 1}T00:00:00+00:00"}
               for i, (prior, new) in enumerate((("9.90", "10.00"), ("10.00", "9.90"), ("9.90", "10.00")))]
    lower, upper, incident = damping_bounds(effective, history, policy)
    assert lower == pytest.approx(9.86) and upper == pytest.approx(10.14) and incident["oscillation"]
    report = analyze_catalog([effective], sales, [inventory], [competitor], iterations=100,
                             damping={product["sku"]: (lower, upper)}, family_catalog=[product])
    [item] = report["recommendations"]
    assert lower <= float(item["proposed_price"]) <= upper
    assert abs(item["delta_pct"]) <= 1.4 + 1e-10


def test_business_context_preserves_pending_no_demand_and_bounds_examples():
    products, sales, stocks, competitors = [], [], [], []
    for index in range(30):
        product, history, inventory, competitor = fixtures(sku=f"SKU-{index}")
        history = [{**row, "units": 0} for row in history]
        products.append(product)
        sales.extend(history)
        stocks.append(inventory)
        competitors.append(competitor)
    result = business_context({"catalog": products, "sales": sales, "inventory": stocks}, competitors)
    assert result["inventory_flags"] == {"no_observed_demand": 30}
    assert len(result["representative_skus"]) == 25 and result["representative_limit"] == 25
    assert all(row["cover_days"] is None for row in result["representative_skus"])
    assert result["median_current_market_gap_pct"] == pytest.approx(100 * (10 / 9.7 - 1))
