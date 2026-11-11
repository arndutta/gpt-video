"""Observed subset comparisons never borrow forecasts from unobserved SKUs."""

from platform_app.outcomes import summarize_outcomes


def item(item_id, multiplier=1):
    return {"id": item_id, "sku": item_id, "forecast": {m: {"mean": n * multiplier} for m, n in
            (("units", 10), ("revenue", 100), ("gross_profit", 30))},
            "baseline": {"forecast": {m: {"mean": n * multiplier} for m, n in
            (("units", 12), ("revenue", 95), ("gross_profit", 25))}}}


def outcome(item_id):
    return {"item_id": item_id, "status": "observed", "result": {"units": 8, "revenue": 80, "gross_profit": 24,
            "absolute_percentage_error": .2, "interval_covered": True, "start": "2026-10-01",
            "end_exclusive": "2026-10-15", "horizon_days": 14}}


def test_observed_subset_uses_matched_forecast_and_baseline_denominator():
    result = summarize_outcomes([item("observed"), item("pending", 100)],
                                [outcome("observed"), {"item_id": "pending", "status": "pending", "result": {}}])
    assert result["observed_skus"] == result["pending_skus"] == 1
    assert result["revenue"] == 80 and result["matched_forecast"]["revenue"] == 100
    assert result["matched_baseline_forecast"]["revenue"] == 95
    assert result["revenue_error"] == result["units_error"] == result["gross_profit_error"] == .2
    assert result["interval_coverage"] == 1 and len(result["window_scope"]) == 1


def test_unmatched_or_immature_outcomes_remain_pending_not_zero():
    result = summarize_outcomes([item("pending")], [outcome("other"), {"item_id": "pending", "status": "pending", "result": {}}])
    assert result["status"] == "pending" and result["observed_skus"] == 0
    assert result["revenue"] is result["revenue_error"] is None
    assert all(v is None for v in result["matched_forecast"].values())
