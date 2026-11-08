"""Numerical behavioral tests use generated observations, never estimator truth inputs."""

from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pytest

from platform_app.tools import AnalysisError, analyze_catalog, simulate_sku
from platform_app.tools.elasticity import estimate_elasticity
from platform_app.tools.monte_carlo import sample_forecasts


def fixtures(elasticity=-1.7, count=140, sku="SKU-001", size=250, current=10):
    now = datetime.now(timezone.utc)
    product = {
        "sku": sku, "name": "Test product", "category": "Beverages", "family_id": "FAM-1",
        "size": size, "currency": "USD", "cost": "5.00", "current_price": str(current),
        "map_price": "6.00", "min_price": "6.00", "max_price": "18.00",
        "max_change_pct": 0.2, "minimum_margin_pct": 0.15,
        "rounding_increment": "0.01", "price_version": 1,
    }
    rng = np.random.default_rng(71)
    sales = []
    for index in range(count):
        day = now.date() - timedelta(days=count - index)
        price = round(current * rng.uniform(0.8, 1.2), 2)
        promotion = index % 11 == 0
        seasonal = 1 + 0.12 * np.sin(index / 20)
        quantity = 45 * (price / current) ** elasticity * seasonal * (1.3 if promotion else 1)
        quantity *= np.exp(rng.normal(0, 0.025))
        sales.append({"sku": sku, "date": str(day), "price": str(price), "units": round(quantity),
                      "promotion": promotion, "seasonal_index": seasonal})
    inventory = {"sku": sku, "on_hand": 10000, "updated_at": now.isoformat()}
    competitor = {"sku": sku, "competitor": "Market", "price": str(current * 0.97), "observed_at": now.isoformat()}
    return product, sales, inventory, competitor


def test_regression_recovers_known_elasticity_without_truth_input():
    product, sales, _, _ = fixtures()
    fit = estimate_elasticity(product, sales)
    assert fit.estimate == pytest.approx(-1.7, abs=0.1)
    assert fit.lower < fit.estimate < fit.upper
    assert fit.sample_size == 140
    assert fit.r_squared > 0.95


def test_fixed_seed_and_scenario_share_identical_price_conditioned_draws():
    product, sales, inventory, competitor = fixtures()
    inputs = ([product], sales, [inventory], [competitor])
    first = analyze_catalog(*inputs, iterations=200, seed=94)
    repeated = analyze_catalog(*inputs, iterations=200, seed=94)
    assert first == repeated
    recommendation = first["recommendations"][0]
    scenario = simulate_sku(product, sales, inventory, [competitor], recommendation["proposed_price"],
                            iterations=200, seed=94)
    assert scenario["forecast"] == recommendation["forecast"]
    assert first["executable"] is False
    assert recommendation["compliance_status"] == "not_validated"
    json.dumps(first, allow_nan=False)


def test_monte_carlo_consumes_upstream_elasticity():
    from dataclasses import replace
    product, sales, inventory, competitor = fixtures()
    fitted = estimate_elasticity(product, sales)
    steep = replace(fitted, estimate=-3.2)
    mild = replace(fitted, estimate=-0.4)
    steep_draws = sample_forecasts(product, steep, inventory, [competitor], [12.0], 500, 1, 14)
    mild_draws = sample_forecasts(product, mild, inventory, [competitor], [12.0], 500, 1, 14)
    assert steep_draws["units"].mean() < mild_draws["units"].mean() * 0.7
    assert steep_draws["margin_rate"].var() > 0


def test_sparse_and_no_price_variation_are_not_confident_recommendations():
    product, sales, inventory, competitor = fixtures(count=15)
    report = analyze_catalog([product], sales, [inventory], [competitor], iterations=100)
    assert not report["recommendations"]
    assert report["skipped"][0]["status"] == "insufficient_history"
    product, sales, inventory, competitor = fixtures()
    for row in sales:
        row["price"] = "10.00"
    report = analyze_catalog([product], sales, [inventory], [competitor], iterations=100)
    assert report["skipped"][0]["confidence"] == 0


def test_quality_failure_prevents_analysis():
    product, sales, inventory, competitor = fixtures()
    product["cost"] = "NaN"
    with pytest.raises(AnalysisError) as failure:
        analyze_catalog([product], sales, [inventory], [competitor], iterations=100)
    assert failure.value.code == "quality_gate_failed"
    assert failure.value.quality["blocked"]


def test_feasible_prices_and_joint_family_ladder_are_preserved():
    first = fixtures(elasticity=-0.4)
    second = fixtures(elasticity=-3.8, sku="SKU-002", size=500, current=10.5)
    products = [first[0], second[0]]
    report = analyze_catalog(products, first[1] + second[1], [first[2], second[2]],
                             [first[3], second[3]], iterations=100)
    recommendations = report["recommendations"]
    assert len(recommendations) == 2
    assert float(recommendations[0]["proposed_price"]) <= float(recommendations[1]["proposed_price"])
    for recommendation, product in zip(recommendations, products):
        price = float(recommendation["proposed_price"])
        assert price >= float(product["map_price"])
        assert 0.8 * float(product["current_price"]) <= price <= 1.2 * float(product["current_price"])
        assert (price - float(product["cost"])) / price >= product["minimum_margin_pct"]


def test_aggregate_uses_corresponding_samples_not_summed_interval_bounds():
    first = fixtures()
    second = fixtures(sku="SKU-002", size=500, current=13)
    report = analyze_catalog([first[0], second[0]], first[1] + second[1], [first[2], second[2]],
                             [first[3], second[3]], iterations=500)
    summed_lower = sum(item["forecast"]["revenue"]["lower"] for item in report["recommendations"])
    assert report["aggregate"]["forecast"]["revenue"]["lower"] > summed_lower
    assert report["aggregate"]["forecast"]["revenue"]["mean"] == pytest.approx(
        sum(item["forecast"]["revenue"]["mean"] for item in report["recommendations"])
    )


def test_missing_competitor_data_lowers_confidence_without_invented_prices():
    product, sales, inventory, competitor = fixtures()
    known = analyze_catalog([product], sales, [inventory], [competitor], iterations=100)
    missing = analyze_catalog([product], sales, [inventory], [], iterations=100)
    assert missing["recommendations"][0]["confidence"] < known["recommendations"][0]["confidence"]
    assert missing["recommendations"][0]["competitive_gap_pct"] is None


def test_out_of_stock_is_explicit_and_monetary_precision_is_validated():
    product, sales, inventory, competitor = fixtures()
    inventory["on_hand"] = 0
    result = analyze_catalog([product], sales, [inventory], [competitor], iterations=100)
    assert not result["recommendations"]
    assert result["skipped"][0]["status"] == "no_available_inventory"
    for price in ["0.0001", "NaN", "1E308"]:
        with pytest.raises(AnalysisError) as failure:
            simulate_sku(product, sales, inventory, [competitor], price, iterations=100)
        assert failure.value.code == "invalid_candidate_price"


@pytest.mark.parametrize("alias,preset,revenues,profits", [
    ("revenue", "revenue-weighted", [100, 95], [10, 100]),
    ("margin", "margin-weighted", [10, 100], [100, 95]),
])
def test_ui_objective_aliases_preserve_weighted_tradeoffs(alias, preset, revenues, profits):
    from platform_app.tools.optimization import objective_scores
    draws = {"revenue": np.array(revenues)[:, None], "gross_profit": np.array(profits)[:, None]}
    alias_scores = objective_scores(draws, alias)
    assert np.array_equal(alias_scores, objective_scores(draws, preset))
    # A pure primary-metric objective would choose index zero; the weighted tradeoff chooses one.
    assert int(np.argmax(alias_scores)) == 1
    product, sales, inventory, competitor = fixtures()
    alias_report = analyze_catalog([product], sales, [inventory], [competitor], objective=alias, iterations=100)
    preset_report = analyze_catalog([product], sales, [inventory], [competitor], objective=preset, iterations=100)
    assert alias_report["recommendations"] == preset_report["recommendations"]
    assert alias_report["configuration"]["objective_weights"] == preset_report["configuration"]["objective_weights"]


def test_conventional_baseline_applies_and_discloses_category_discounts():
    from platform_app.tools.optimization import baseline_price
    product, sales, inventory, competitor = fixtures()
    product.update(category="Snacks", cost="10.00")
    assert baseline_price(product) == 13.78  # 10 * 1.45 * 0.95 = 13.775, rounded half-up.
    scenario = simulate_sku(product, sales, inventory, [competitor], "10.00", iterations=100)
    assert scenario["baseline"]["policy"]["discount"] == 0.05
    assert scenario["baseline"]["price"] == "13.78"
    assert scenario["configuration"]["baseline_policy"]["categories"]["Household"]["discount"] == 0.03
