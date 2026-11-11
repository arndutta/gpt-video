"""Run comparison uses only the same mature SKU windows on both sides."""


def summarize_outcomes(items, outcomes):
    by_id = {i["id"]: i for i in items}
    matched = [(o["result"], by_id[o["item_id"]]) for o in outcomes
               if o["status"] == "observed" and o["item_id"] in by_id and by_id[o["item_id"]].get("forecast")]
    metrics = ("units", "revenue", "gross_profit")
    actual = {m: sum(o[m] for o, _ in matched) if matched else None for m in metrics}
    forecast = {m: sum(i["forecast"][m]["mean"] for _, i in matched) if matched else None for m in metrics}
    baseline = {m: sum(i["baseline"]["forecast"][m]["mean"] for _, i in matched) if matched else None for m in metrics}
    errors = {m + "_error": abs(actual[m] - forecast[m]) / max(abs(forecast[m]), 1.) if matched else None for m in metrics}
    # Signed covariance is not recoverable from interval endpoints; this report
    # deliberately exposes aggregate means, not a fabricated aggregate interval.
    return {"status": "observed" if matched else "pending", **actual, **errors,
            "observed_skus": len(matched), "pending_skus": sum(o["status"] == "pending" for o in outcomes),
            "excluded_skus": sum(o["status"] == "excluded" for o in outcomes),
            "forecast_error": sum(o["absolute_percentage_error"] for o, _ in matched) / len(matched) if matched else None,
            "interval_coverage": sum(o["interval_covered"] for o, _ in matched) / len(matched) if matched else None,
            "matched_forecast": forecast, "matched_baseline_forecast": baseline,
            "denominator": "Same observed SKU revisions, each over its complete, disjoint forecast horizon",
            "window_scope": [{"item_id": i["id"], "sku": i["sku"], "start": o["start"],
                              "end_exclusive": o["end_exclusive"], "horizon_days": o["horizon_days"]} for o, i in matched],
            "comparison_status": "Observed treatment versus aligned forecast; baseline is a counterfactual forecast, not measured uplift"}
