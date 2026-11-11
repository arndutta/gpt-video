"""Many-SKU sample aggregation, no-write semantics, stress and learned version parity."""

from copy import deepcopy

import numpy as np
import pytest
from pydantic import ValidationError

from platform_app.scenarios import BatchScenario, simulate_many
from platform_app.tools import AnalysisError, analyze_catalog, simulate_sku
from platform_app.tools.elasticity import estimate_elasticity
from platform_app.tools.monte_carlo import sample_forecasts, summarize
from test_analysis import fixtures


def scenario_fixture():
    first = fixtures(sku="SKU-1", current=10)
    second = fixtures(sku="SKU-2", size=500, current=16)
    context = {"catalog": [first[0], second[0]], "sales": first[1] + second[1],
               "inventory": [first[2], second[2]]}
    return context, [first[3], second[3]]


def request(**changes):
    return BatchScenario(**{"items": [{"sku": "SKU-1", "candidate_price": "11.00"},
                                      {"sku": "SKU-2", "candidate_price": "17.00"}],
                            "iterations": 200, "seed": 42, "horizon_days": 14, **changes})


def test_many_sku_scenario_aggregates_corresponding_samples_without_mutation():
    context, competitors = scenario_fixture()
    original = deepcopy(context)
    result = simulate_many(context, competitors, request(), {})
    assert context == original and result["executable"] is False
    assert result["aggregate"]["sku_count"] == 2
    samples = []
    for product, price in zip(context["catalog"], [11., 17.]):
        rows = [s for s in context["sales"] if s["sku"] == product["sku"]]
        inventory = next(i for i in context["inventory"] if i["sku"] == product["sku"])
        feed = [c for c in competitors if c["sku"] == product["sku"]]
        samples.append(sample_forecasts(product, estimate_elasticity(product, rows), inventory,
                                        feed, [price], 200, 42, 14)["revenue"][0])
    assert result["aggregate"]["forecast"]["revenue"] == summarize(np.sum(samples, axis=0))
    assert result == simulate_many(context, competitors, request(), {})


@pytest.mark.parametrize("stress", ["demand_collapse", "competitor_undercut", "cost_spike"])
def test_stress_matches_single_engine_and_exposes_assumptions(stress):
    context, competitors = scenario_fixture()
    payload = request(stress=stress)
    result = simulate_many(context, competitors, payload, {})
    reference = simulate_sku(context["catalog"][0], context["sales"], context["inventory"],
                             competitors, "11.00", 200, 42, 14, stress=stress)
    assert result["items"][0]["forecast"] == reference["forecast"]
    normal = simulate_many(context, competitors, request(), {})
    metric = "gross_profit" if stress == "cost_spike" else "revenue"
    assert result["aggregate"]["forecast"][metric]["mean"] < normal["aggregate"]["forecast"][metric]["mean"]
    assert result["configuration"]["stress"] == stress and result["configuration"]["stress_assumptions"]


def test_learned_state_is_used_identically_by_scenario_and_recommendation():
    context, competitors = scenario_fixture()
    state = {"observations": 4, "observed_days": 40, "elasticity_offset": -.2, "uncertainty_multiplier": 1.3,
             "mean_absolute_error": .4, "version": "learned-4"}
    learning = {"SKU-1": state}
    report = analyze_catalog(**context, competitors=competitors, iterations=200, learning=learning)
    first = next(i for i in report["recommendations"] if i["sku"] == "SKU-1")
    payload = request(items=[{"sku": "SKU-1", "candidate_price": first["proposed_price"]}])
    scenario = simulate_many(context, competitors, payload, learning)["items"][0]
    assert scenario["forecast"] == first["forecast"]
    assert scenario["elasticity"] == first["elasticity"]
    assert scenario["confidence_factors"]["model_version"] == "learned-4"


def test_invalid_scope_and_duplicate_candidates_are_typed_failures():
    context, competitors = scenario_fixture()
    with pytest.raises(AnalysisError) as missing:
        simulate_many(context, competitors, request(items=[{"sku": "missing", "candidate_price": "1.00"}]), {})
    assert missing.value.code == "sku_not_found"
    with pytest.raises(ValidationError):
        request(items=[{"sku": "SKU-1", "candidate_price": "1.00"}] * 2)
    with pytest.raises(AnalysisError) as bad_price:
        simulate_many(context, competitors, request(items=[{"sku": "SKU-1", "candidate_price": "0.00"}]), {})
    assert bad_price.value.code == "invalid_candidate_price"
