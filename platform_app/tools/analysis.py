"""Pure numerical entry points; business data arrives through caller-owned adapters."""

from collections import defaultdict
from decimal import Decimal, InvalidOperation

import numpy as np

from .elasticity import InsufficientHistory, estimate_elasticity
from .monte_carlo import (
    configuration, forecast_summary, sample_forecasts, summarize,
    validate_simulation_parameters,
)
from .optimization import (
    baseline_policy, baseline_price, feasible_prices, money,
    objective_scores, objective_weights, select_family_prices,
)
from .quality import competitor_freshness, quality_report


class AnalysisError(ValueError):
    def __init__(self, message: str, code: str = "quality_gate_failed", quality: dict | None = None):
        super().__init__(message)
        self.code = code
        self.quality = quality


def _group(records: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for record in records:
        grouped[record.get("sku")].append(record)
    return grouped


def _check_inputs(catalog, sales, inventory, competitors, iterations, seed, horizon_days):
    try:
        validate_simulation_parameters(iterations, seed, horizon_days)
    except ValueError as error:
        raise AnalysisError(str(error), "invalid_simulation_parameters") from error
    quality = quality_report(catalog, sales, inventory, competitors)
    if quality["blocked"]:
        reasons = [check["message"] for check in quality["checks"] if check["severity"] == "error"]
        raise AnalysisError(" ".join(reasons), quality=quality)
    return quality


def _confidence(estimate, forecast: dict, competitors: list[dict], quality: dict) -> tuple[float, dict]:
    width = estimate.upper - estimate.lower
    elasticity_score = 1 / (1 + width)
    if estimate.estimate >= 0:
        elasticity_score *= 0.25
    elif estimate.upper >= 0:
        elasticity_score *= 0.5
    revenue = forecast["revenue"]
    variation = revenue["variance"] ** 0.5 / max(revenue["mean"], 1)
    components = {
        "elasticity_precision": elasticity_score,
        "sample_sufficiency": min(estimate.sample_size / 120, 1),
        "simulation_stability": 1 / (1 + variation),
        "data_quality": 0.8 if quality["status"] == "degraded" else 1.0,
        "competitor_freshness": competitor_freshness(competitors),
    }
    weights = {"elasticity_precision": 0.4, "sample_sufficiency": 0.15,
               "simulation_stability": 0.15, "data_quality": 0.15, "competitor_freshness": 0.15}
    score = sum(components[key] * weights[key] for key in components)
    return round(score, 4), {**components, "weights": weights, "calibrated": False}


def _render_preview(item: dict, price: float, quality: dict, iterations: int, seed: int, horizon_days: int):
    product, estimate = item["product"], item["estimate"]
    current = float(product["current_price"])
    baseline = baseline_price(product)
    draws = sample_forecasts(product, estimate, item["inventory"], item["competitors"],
                             [price, current, baseline], iterations, seed, horizon_days)
    forecast = forecast_summary(draws, 0, product)
    current_forecast = forecast_summary(draws, 1, product)
    baseline_forecast = forecast_summary(draws, 2, product)
    confidence, factors = _confidence(estimate, forecast, item["competitors"], quality)
    competitor_prices = [float(record["price"]) for record in item["competitors"]]
    market_price = float(np.median(competitor_prices)) if competitor_prices else None
    cover = float(item["inventory"]["on_hand"]) / max(estimate.daily_demand, 1e-9)
    impacts = {metric: summarize(values[0] - values[1]) for metric, values in draws.items()
               if metric in {"revenue", "gross_profit"}}
    impacts["revenue_uplift_pct"] = 100 * (forecast["revenue"]["mean"] / max(current_forecast["revenue"]["mean"], 1e-9) - 1)
    impacts["profit_uplift_pct"] = 100 * impacts["gross_profit"]["mean"] / max(abs(current_forecast["gross_profit"]["mean"]), 1e-9)
    report = {
        "sku": product["sku"], "name": product["name"], "category": product.get("category", ""),
        "family_id": product.get("family_id"), "currency": product.get("currency", "USD"),
        "current_price": money(current), "proposed_price": money(price),
        "delta_absolute": money(price - current), "delta_pct": 100 * (price / current - 1),
        "price_version": product.get("price_version"), "elasticity": estimate.public(),
        "forecast": forecast, "current_forecast": current_forecast, "impact": impacts,
        "confidence": confidence, "confidence_factors": factors,
        "baseline": {"price": money(baseline), "forecast": baseline_forecast,
                     "method": "cost-plus with category discounts; not an approved price",
                     "policy": baseline_policy(product)},
        "competitive_gap_pct": 100 * (price / market_price - 1) if market_price else None,
        "competitor_gaps": [{"competitor": record["competitor"], "price": record["price"],
                             "gap_pct": 100 * (price / float(record["price"]) - 1)}
                            for record in item["competitors"]],
        "cover_days": cover, "inventory_pressure": "stockout_risk" if cover < 7 else "overstock" if cover > 60 else "normal",
        "status": "preview", "compliance_status": "not_validated", "executable": False,
        "assumptions": [
            "95% predictive simulation bands; uncertainty distributions are initial demo assumptions, not calibrated guarantees.",
            "Elasticity is estimated by log-linear regression with promotion, seasonal and weekly controls.",
            "Demand is capped by on-hand inventory; no replenishment is assumed during the horizon.",
            "Cost drift has 2% lognormal uncertainty; seasonal and cost shocks are partly shared across SKUs.",
            "Competitor response has 3.5% price uncertainty (12% when absent), 0.4 demand transmission, and 0.15 price follow-through.",
            "Forecast represents a non-promoted average weekday at the latest observed seasonal level.",
            "Quantitative preview requires grounded reasoning, validation, and approval before price changes.",
        ],
        "evidence_sources": [f"commerce://catalog/{product['sku']}", f"commerce://sales/{product['sku']}",
                             f"commerce://inventory/{product['sku']}"],
    }
    # Callers aggregate corresponding draws, not interval endpoints.
    return report, {metric: values for metric, values in draws.items() if metric in {"revenue", "gross_profit", "units"}}


def analyze_catalog(
    catalog: list[dict], sales: list[dict], inventory: list[dict], competitors: list[dict],
    objective: str = "balanced", iterations: int = 1000, seed: int = 42, horizon_days: int = 14,
) -> dict:
    quality = _check_inputs(catalog, sales, inventory, competitors, iterations, seed, horizon_days)
    if objective not in {"balanced", "revenue-weighted", "margin-weighted", "revenue", "margin"}:
        raise AnalysisError("Unknown objective; choose balanced, revenue-weighted, or margin-weighted.", "invalid_objective")
    sales_by_sku, competitors_by_sku = _group(sales), _group(competitors)
    inventory_by_sku = {record["sku"]: record for record in inventory}
    prepared, skipped = [], []
    for product in sorted(catalog, key=lambda record: record["sku"]):
        sku = product["sku"]
        if float(inventory_by_sku[sku]["on_hand"]) == 0:
            skipped.append({"sku": sku, "status": "no_available_inventory", "confidence": 0,
                            "reason": "No on-hand inventory is available in the no-replenishment horizon."})
            continue
        try:
            estimate = estimate_elasticity(product, sales_by_sku[sku])
        except InsufficientHistory as error:
            skipped.append({"sku": sku, "status": "insufficient_history", "reason": str(error), "confidence": 0})
            continue
        prices = feasible_prices(product)
        if not prices:
            skipped.append({"sku": sku, "status": "no_feasible_price", "reason": "Price constraints have no feasible intersection."})
            continue
        draws = sample_forecasts(product, estimate, inventory_by_sku[sku], competitors_by_sku[sku],
                                 prices, iterations, seed, horizon_days)
        prepared.append({"product": product, "estimate": estimate, "inventory": inventory_by_sku[sku],
                         "competitors": competitors_by_sku[sku], "prices": prices,
                         "scores": objective_scores(draws, objective)})
    selected = select_family_prices(prepared, catalog)
    recommendations = []
    totals = {metric: np.zeros((3, iterations)) for metric in ["revenue", "gross_profit", "units"]}
    for item in prepared:
        sku = item["product"]["sku"]
        if sku not in selected:
            skipped.append({"sku": sku, "status": "no_feasible_family_price",
                            "reason": "No coherent monotone price ladder satisfies all family constraints."})
            continue
        report, draws = _render_preview(item, selected[sku], quality, iterations, seed, horizon_days)
        recommendations.append(report)
        for metric in totals:
            totals[metric] += draws[metric]
    aggregate = {
        "sku_count": len(recommendations), "excluded_sku_count": len(skipped),
        "scope": "Only successfully modeled SKUs; the same SKU set is used for every comparison.",
        "forecast": {metric: summarize(values[0]) for metric, values in totals.items()},
        "current_forecast": {metric: summarize(values[1]) for metric, values in totals.items()},
        "baseline_forecast": {metric: summarize(values[2]) for metric, values in totals.items()},
        "impact": {metric: summarize(values[0] - values[1]) for metric, values in totals.items()},
        "baseline_impact": {metric: summarize(values[0] - values[2]) for metric, values in totals.items()},
    }
    return {"type": "quantitative_preview", "executable": False, "quality": quality,
            "recommendations": recommendations, "skipped": skipped, "aggregate": aggregate,
            "configuration": {**configuration(iterations, seed, horizon_days), "objective": objective,
                              "objective_weights": objective_weights(objective),
                              "objective_normalization": "Per-SKU candidate maximum expected revenue and absolute expected gross profit, each floored at one.",
                              "baseline_policy": baseline_policy()}}


def simulate_sku(
    product: dict, sales: list[dict], inventory: list[dict] | dict, competitors: list[dict],
    candidate_price: float | str, iterations: int = 1000, seed: int = 42, horizon_days: int = 14,
) -> dict:
    try:
        monetary_price = Decimal(str(candidate_price))
        tick = Decimal(str(product.get("rounding_increment", "0.01")))
        if not monetary_price.is_finite() or monetary_price <= 0 or monetary_price % tick:
            raise ValueError
        price = float(candidate_price)
        if not np.isfinite(price) or price <= 0:
            raise ValueError
    except (TypeError, ValueError, InvalidOperation, ZeroDivisionError) as error:
        raise AnalysisError("Candidate price must be positive, finite, and an exact multiple of the price tick.",
                            "invalid_candidate_price") from error
    sku = product["sku"]
    sales = [record for record in sales if record.get("sku") == sku]
    competitors = [record for record in competitors if record.get("sku") == sku]
    inventories = [inventory] if isinstance(inventory, dict) else [record for record in inventory if record.get("sku") == sku]
    quality = _check_inputs([product], sales, inventories, competitors, iterations, seed, horizon_days)
    try:
        estimate = estimate_elasticity(product, sales)
    except InsufficientHistory as error:
        raise AnalysisError(str(error), "insufficient_history", quality) from error
    item = {"product": product, "estimate": estimate, "inventory": inventories[0], "competitors": competitors}
    report, _ = _render_preview(item, price, quality, iterations, seed, horizon_days)
    return {**report, "type": "quantitative_preview", "quality": quality,
            "configuration": {**configuration(iterations, seed, horizon_days),
                              "baseline_policy": baseline_policy()}}
