"""Held-out synthetic evaluator. This module is never imported by production agents."""

import numpy as np

from platform_app.governance.models import GovernancePolicy
from platform_app.tools.optimization import feasible_prices, objective_scores, select_family_prices


def expected(product, truth, stock, price, seasonal, horizon):
    demand = truth["baseline_demand"] * seasonal * (price / float(product["current_price"])) ** (truth["elasticity"] + .06)
    units = min(stock, demand * horizon)
    return price * units, (price - float(product["cost"])) * units


def evaluator_context(report, context, truth, horizon, objective):
    """Return held-out expected-price inputs and joint optima for evaluation scripts."""
    products = {p["sku"]: p for p in context["catalog"]}
    stocks = {i["sku"]: i["on_hand"] for i in context["inventory"]}
    latest = {}
    for row in sorted(context["sales"], key=lambda row: row["date"]):
        latest[row["sku"]] = row["seasonal_index"]
    prepared = []
    for item in report["recommendations"]:
        p = products[item["sku"]]
        prices = feasible_prices(p)
        pairs = [expected(p, truth[p["sku"]], stocks[p["sku"]], price, latest[p["sku"]], horizon) for price in prices]
        draws = {"revenue": np.array([[pair[0]] for pair in pairs]),
                 "gross_profit": np.array([[pair[1]] for pair in pairs])}
        prepared.append({"product": p, "prices": prices, "scores": objective_scores(draws, objective)})
    optima = select_family_prices(prepared, context["catalog"])
    return products, stocks, latest, optima


def evaluate(report, context, truth, horizon, objective):
    products, stocks, latest, optima = evaluator_context(report, context, truth, horizon, objective)
    eligible = [i for i in report["recommendations"] if i["confidence"] > GovernancePolicy().confidence_threshold]
    errors = [abs(float(i["proposed_price"]) / optima[i["sku"]] - 1) for i in eligible]
    totals = {key: [0., 0.] for key in ("proposed", "baseline", "current")}
    for item in report["recommendations"]:
        p = products[item["sku"]]
        for key, price in (("proposed", item["proposed_price"]), ("current", item["current_price"]),
                           ("baseline", item["baseline"]["price"])):
            pair = expected(p, truth[p["sku"]], stocks[p["sku"]], float(price), latest[p["sku"]], horizon)
            totals[key] = [a + b for a, b in zip(totals[key], pair)]
    ai, baseline = report["aggregate"]["forecast"], report["aggregate"]["baseline_forecast"]
    forecast_uplift = (ai["revenue"]["mean"] / baseline["revenue"]["mean"] - 1) * 100
    forecast_profit_delta = ai["gross_profit"]["mean"] - baseline["gross_profit"]["mean"]
    forecast_margin_delta = ai["gross_profit"]["mean"] / ai["revenue"]["mean"] - baseline["gross_profit"]["mean"] / baseline["revenue"]["mean"]
    return {"sku_count": len(report["recommendations"]), "high_confidence_threshold": GovernancePolicy().confidence_threshold,
            "high_confidence_skus": len(eligible), "price_error_mean_pct": 100 * float(np.mean(errors)) if errors else None,
            "price_error_max_pct": 100 * max(errors) if errors else None,
            "within_10pct_count": sum(error <= .1 for error in errors),
            "within_10pct_share": sum(error <= .1 for error in errors) / len(errors) if errors else None,
            "forecast_revenue_uplift_vs_baseline_pct": forecast_uplift,
            "forecast_gross_profit_delta_vs_baseline": forecast_profit_delta,
            "forecast_margin_rate_delta_vs_baseline": forecast_margin_delta,
            "truth_expected_totals": {key: {"revenue": pair[0], "gross_profit": pair[1]} for key, pair in totals.items()},
            "targets": {"forecast_revenue_uplift_at_least_5pct": forecast_uplift >= 5,
                        "no_forecast_gross_profit_degradation": forecast_profit_delta >= 0,
                        "no_forecast_margin_rate_degradation": forecast_margin_delta >= 0,
                        "all_high_confidence_prices_within_10pct": bool(errors) and all(e <= .1 for e in errors)},
            "truth_method": "Held-out generator elasticity/demand; deterministic expected stock-capped demand with same +0.06 competitor follow-through and latest seasonal level. Joint family ladder, same21-point feasible candidate grid and objective. No stochastic future outcomes or causal claims."}
