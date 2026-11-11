from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from governance_helpers import recommendation
from platform_app.governance.bands import assign_band
from platform_app.governance.compliance import contains_personal_pricing, validate_price
from platform_app.governance.models import Decision, GovernancePolicy
from platform_app.governance.stability import analyze_stability, damping_bounds


@pytest.fixture
def product():
    return {"sku": "A", "name": "A", "category": "Beverages", "family_id": "F", "size": 1,
            "currency": "USD", "current_price": "10.00", "price_version": 1, "cost": "5.00",
            "map_price": "8.00", "minimum_margin_pct": .2, "max_change_pct": .2,
            "min_price": "7.00", "max_price": "15.00", "rounding_increment": "0.01"}


@pytest.mark.parametrize("field,value,price,rule", [
    ("map_price", "10.50", "10.20", "map_floor"),
    ("cost", "9.00", "10.20", "margin_floor"),
    ("max_change_pct", .01, "10.20", "max_change"),
    ("max_price", "10.10", "10.20", "category_bounds"),
    ("rounding_increment", "0.05", "10.21", "rounding_policy"),
])
def test_independent_rule_veto(product, field, value, price, rule):
    product[field] = value
    result = validate_price(product, price, [product], expected_version=1)
    assert result["status"] == "failed"
    assert not next(row for row in result["rules"] if row["rule"] == rule)["passed"]
    assert len(result["rules"]) >= 7


def test_ladder_stale_and_personal_pricing_veto(product):
    larger = {**product, "sku": "B", "size": 2, "current_price": "10.10"}
    result = validate_price(product, "10.20", [product, larger], expected_version=2,
                            request={"scope": {"customer_id": "sensitive"}})
    failed = {row["rule"] for row in result["rules"] if not row["passed"]}
    assert {"price_ladder", "source_price_version", "personal_pricing"} <= failed
    assert contains_personal_pricing([{"x": {"email": "redacted@example.org"}}])
    assert not contains_personal_pricing({"sku": "X", "category": "All"})
    assert validate_price(product, "NaN", [product])["status"] == "failed"
    assert validate_price(product, "1.001", [product])["status"] == "failed"


def test_runtime_policy_only_tightens_commerce_rules(product):
    policy = GovernancePolicy(minimum_margin_pct=.1, maximum_change_pct=.9)
    assert validate_price(product, "12.01", [product], policy=policy)["status"] == "failed"
    tighter = GovernancePolicy(minimum_margin_pct=.6, maximum_change_pct=.01)
    verdict = validate_price(product, "10.20", [product], policy=tighter)
    assert {row["rule"] for row in verdict["rules"] if not row["passed"]} >= {"margin_floor", "max_change"}


@pytest.mark.parametrize("trigger", ["compliance", "margin", "volatility", "oscillation", "novel_market"])
def test_every_escalation_trigger_independently_wins(product, trigger):
    item = recommendation(product)
    compliance, stability = {"status": "passed"}, {"oscillation": False, "novel_market": False}
    if trigger == "compliance":
        compliance["status"] = "failed"
    elif trigger == "margin":
        product["minimum_margin_pct"] = .49
    elif trigger == "volatility":
        item["forecast"]["revenue"]["variance"] = 1600
    else:
        stability[trigger] = True
    band = assign_band(item, product, compliance, stability)
    assert band["band"] == "escalate"
    assert any(not reason["passed"] for reason in band["band_reasons"][:5])


def test_auto_requires_every_condition_and_confidence_strictly_above(product):
    item = recommendation(product)
    args = (product, {"status": "passed"}, {"oscillation": False, "novel_market": False})
    assert assign_band(item, *args)["band"] == "auto_approve"
    for patch in ({"confidence": .8}, {"delta_pct": 5.01}, {"elasticity": {"sample_size": 59}}):
        changed = {**item, **patch}
        assert assign_band(changed, *args)["band"] == "review"
    assert assign_band({**item, "delta_pct": 5.0}, *args)["band"] == "auto_approve"
    # Scaling revenue to a fractional currency amount must not hide volatility.
    small = deepcopy(item)
    small["forecast"]["revenue"] = {"mean": .1, "variance": .01}
    assert assign_band(small, *args)["band"] == "escalate"


@pytest.mark.parametrize("gap,expected", [(30., "auto_approve"), (-30., "auto_approve"),
                                          (30.01, "escalate"), (-30.01, "escalate")])
def test_observed_market_gap_uses_configured_norm_with_actual_threshold_evidence(product, gap, expected):
    item = {**recommendation(product), "competitive_gap_pct": gap}
    result = assign_band(item, product, {"status": "passed"}, {"oscillation": False, "novel_market": False})
    assert result["band"] == expected
    reason = next(row for row in result["band_reasons"] if row["code"] == "novel_market")
    assert reason["actual"]["competitive_gap_pct"] == gap and reason["threshold"]["abs_market_gap_pct"] == 30.
    assert "configured" in reason["message"] and "not a measured historical distribution" in reason["message"]


def test_oscillation_damping_return_cooldown_and_convergence(product):
    at = datetime.now(timezone.utc)
    history = [{"sku": "A", "prior_price": prior, "new_price": new,
                "applied_at": (at - timedelta(seconds=10 - i)).isoformat(), "id": i}
               for i, (prior, new) in enumerate((("9.00", "10.00"), ("10.00", "9.00"), ("9.00", "10.00")))]
    policy = GovernancePolicy(minimum_change_seconds=60)
    signals = analyze_stability(product, "9.00", history, policy=policy, error_series=[1, 1, 1, 2, 2, 2], at=at)
    assert signals["oscillation"] and signals["recent_price_return"] and signals["cooldown_active"]
    assert signals["convergence_status"] == "widening"
    lower, upper, retained = damping_bounds(product, history, policy)
    assert (lower, upper) == (9.3, 10.7) and retained["oscillation"]
    assert analyze_stability(product, "10.20", [], error_series=[])["convergence_status"] == "pending"
    good = analyze_stability(product, "10.20", [], error_series=[2, 2, 2, 1, 1, 1])
    assert good["convergence_status"] == "narrowing"


def test_decision_contract_rejects_unreasoned_override_and_extra_personal_inputs():
    with pytest.raises(ValueError):
        Decision(action="override", expected_revision=1, price="10.00")
    with pytest.raises(ValueError):
        Decision(action="approve", expected_revision=True)
    with pytest.raises(ValueError):
        Decision(action="approve", expected_revision=1, customer_id="private")


def test_price_anomalies_are_independent_of_compliance(product):
    history = [{"sku": "A", "id": index, "prior_price": str(9.99 + index * .001),
                "new_price": str(10.00 + index * .001), "applied_at": f"2026-11-0{index + 1}T00:00:00+00:00"}
               for index in range(6)]
    # A wider historical range than the tick makes an identifiable distribution.
    for index, row in enumerate(history):
        row["prior_price"], row["new_price"] = str(9.9 + index * .02), str(9.92 + index * .02)
    catalog = [{**product, "sku": str(i), "current_price": str(9.9 + i * .04)} for i in range(6)]
    signals = analyze_stability(product, "11.90", history, catalog)
    assert signals["historical_z"] > 4 and signals["category_z"] > 4 and signals["novel_market"]
    assert validate_price(product, "11.90", [product])["status"] == "passed"
