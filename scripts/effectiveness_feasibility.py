"""Evaluation-only feasibility bounds and estimator/decision sensitivity evidence."""

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import tempfile

import httpx
import numpy as np

from commerce.app import create_app
from commerce.evaluation import read_evaluation_truth
from commerce.seed import seed_database
from platform_app.commerce_client import CommerceClient, read_competitors
from platform_app.governance.compliance import validate_price
from platform_app.tools import analyze_catalog
from platform_app.tools.elasticity import estimate_elasticity
from platform_app.tools.monte_carlo import sample_forecasts
from platform_app.tools.optimization import baseline_price, feasible_prices, objective_scores, select_family_prices
from scripts.benchmark_metrics import evaluate, evaluator_context, expected


def continuous_bound(product, truth, stock, seasonal, horizon):
    """Upper bound: retain SKU rules but relax ticks, the grid and family ladders."""
    current, cost = float(product["current_price"]), float(product["cost"])
    lower = max(float(product["map_price"]), float(product["min_price"]),
                cost / (1 - product["minimum_margin_pct"]), current * (1 - product["max_change_pct"]))
    upper = min(float(product["max_price"]), current * (1 + product["max_change_pct"]))
    if lower > upper:
        raise ValueError("The fixture has no feasible price interval")
    exponent = truth["elasticity"] + .06
    demand = truth["baseline_demand"] * seasonal * horizon
    candidates = [lower, upper]
    if exponent != 0 and stock > 0 and demand > 0:
        log_crossing = math.log(current) + math.log(stock / demand) / exponent
        if math.log(lower) <= log_crossing <= math.log(upper):
            candidates.append(math.exp(log_crossing))
    price = max(candidates, key=lambda candidate: expected(product, truth, stock, candidate, seasonal, horizon)[0])
    return {"price": price, "revenue": expected(product, truth, stock, price, seasonal, horizon)[0],
            "lower": lower, "upper": upper}


def snapshot(context, competitors, truth, seed, iterations, horizon):
    report = analyze_catalog(context["catalog"], context["sales"], context["inventory"], competitors,
                             iterations=iterations, seed=seed, horizon_days=horizon)
    products, stock, seasonal, optima = evaluator_context(report, context, truth, horizon, "balanced")
    inventory = {i["sku"]: i for i in context["inventory"]}
    sales, feed = defaultdict(list), defaultdict(list)
    for row in context["sales"]:
        sales[row["sku"]].append(row)
    for row in competitors:
        feed[row["sku"]].append(row)
    fits = {sku: estimate_elasticity(p, sales[sku]) for sku, p in products.items()}
    grids = {sku: feasible_prices(p) for sku, p in products.items()}
    raw = {sku: baseline_price(p) for sku, p in products.items()}
    nearest = [{"product": p, "prices": grids[sku],
                "scores": -((np.array(grids[sku]) - raw[sku]) / max(raw[sku], 1e-9)) ** 2}
               for sku, p in products.items()]
    projected = select_family_prices(nearest, context["catalog"])
    raw_failures, projected_failures = Counter(), Counter()
    legal_grid_revenue_bound = raw_forecast = projected_forecast = projected_profit = continuous = raw_truth = 0.
    revenue_prepared, point_prepared, arrays = [], [], {}
    true_scores, family_regret, per_sku = {}, defaultdict(lambda: [0., 0.]), []
    for sku, p in products.items():
        for prices, failures in ((raw, raw_failures), (projected, projected_failures)):
            verdict = validate_price(p, str(prices[sku]), context["catalog"], changes=prices)
            for rule in verdict["rules"]:
                if not rule["passed"]:
                    failures[rule["rule"]] += 1
        prices, fit = grids[sku], fits[sku]
        draws = sample_forecasts(p, fit, inventory[sku], feed[sku], prices + [raw[sku], projected[sku]],
                                 iterations, seed, horizon)
        means = {metric: values.mean(axis=1) for metric, values in draws.items()}
        legal_grid_revenue_bound += max(means["revenue"][:-2])
        raw_forecast += means["revenue"][-2]
        projected_forecast += means["revenue"][-1]
        projected_profit += means["gross_profit"][-1]
        arrays[sku] = means
        revenue_prepared.append({"product": p, "prices": prices, "scores": means["revenue"][:-2]})
        continuous += continuous_bound(p, truth[sku], stock[sku], seasonal[sku], horizon)["revenue"]
        raw_truth += expected(p, truth[sku], stock[sku], raw[sku], seasonal[sku], horizon)[0]
        demand = np.minimum(fit.daily_demand * horizon * (np.array(prices) / float(p["current_price"])) ** (fit.estimate + .06), stock[sku])
        point_draws = {"revenue": np.array(prices)[:, None] * demand[:, None],
                       "gross_profit": (np.array(prices) - float(p["cost"]))[:, None] * demand[:, None]}
        point_prepared.append({"product": p, "prices": prices, "scores": objective_scores(point_draws, "balanced")})
        pairs = [expected(p, truth[sku], stock[sku], price, seasonal[sku], horizon) for price in prices]
        scores = objective_scores({"revenue": np.array([[a] for a, _ in pairs]),
                                   "gross_profit": np.array([[b] for _, b in pairs])}, "balanced")
        true_scores[sku] = dict(zip(prices, scores))
    point_prices = select_family_prices(point_prepared, context["catalog"])
    maximum_prices = select_family_prices(revenue_prepared, context["catalog"])
    maximum_revenue = maximum_profit = 0.
    for sku, price in maximum_prices.items():
        index = grids[sku].index(price)
        maximum_revenue += arrays[sku]["revenue"][index]
        maximum_profit += arrays[sku]["gross_profit"][index]
    for item in report["recommendations"]:
        sku, price = item["sku"], float(item["proposed_price"])
        fit, p = fits[sku], products[sku]
        true_daily = truth[sku]["baseline_demand"] * seasonal[sku]
        error = abs(price / optima[sku] - 1)
        point_error = abs(point_prices[sku] / optima[sku] - 1)
        family = p.get("family_id") or sku
        family_regret[family][0] += true_scores[sku][optima[sku]]
        family_regret[family][1] += true_scores[sku][price]
        per_sku.append({"sku": sku, "family": family, "relative_price_error": error,
                        "price": price, "theoretical_price": optima[sku], "point_price": point_prices[sku],
                        "point_relative_error": point_error, "confidence": item["confidence"],
                        "elasticity_error": fit.estimate - truth[sku]["elasticity"],
                        "elasticity_ci_covers_truth": fit.lower <= truth[sku]["elasticity"] <= fit.upper,
                        "relative_demand_error": fit.daily_demand / true_daily - 1,
                        "optimal_price_uncertainty": item.get("optimal_price_uncertainty")})
    errors = [item for item in per_sku if item["relative_price_error"] > .1]
    regrets = {family: max((best - actual) / max(abs(best), 1e-9), 0)
               for family, (best, actual) in family_regret.items()}
    error_families = {item["family"] for item in errors}
    return {"seed": seed, "modeled_skus": len(per_sku),
            "confidence_model_version": report["configuration"].get("confidence_model_version"),
            "effectiveness": evaluate(report, context, truth, horizon, "balanced"),
            "all_sku_accuracy": {"within_10pct": len(per_sku) - len(errors), "denominator": len(per_sku),
                                 "max_error_pct": 100 * max(i["relative_price_error"] for i in per_sku)},
            "diagnosis": {"point_optimizer_errors_over_10pct": sum(i["point_relative_error"] > .1 for i in per_sku),
                          "monte_carlo_vs_point_price_diff_over_10pct": sum(abs(i["price"] / i["point_price"] - 1) > .1 for i in per_sku),
                          "elasticity_rmse": float(np.sqrt(np.mean([i["elasticity_error"] ** 2 for i in per_sku]))),
                          "elasticity_95pct_ci_coverage": np.mean([i["elasticity_ci_covers_truth"] for i in per_sku]).item(),
                          "demand_mape": np.mean([abs(i["relative_demand_error"]) for i in per_sku]).item(),
                          "price_error_families": len(error_families),
                          "error_family_objective_regret_median_pct": 100 * float(np.median([regrets[f] for f in error_families])) if error_families else None,
                          "error_family_objective_regret_max_pct": 100 * max(regrets[f] for f in error_families) if error_families else None},
            "original_baseline_constraint_failure_counts": dict(raw_failures),
            "upper_bounds": {"forecast_grid_relaxed_family_uplift_pct": 100 * (legal_grid_revenue_bound / raw_forecast - 1),
                             "truth_continuous_relaxed_family_uplift_pct": 100 * (continuous / raw_truth - 1),
                             "target_5pct_feasible_under_forecast_grid_upper_bound": bool(legal_grid_revenue_bound >= raw_forecast * 1.05)},
            "analytical_counterfactual_only": {
                "description": "Nearest original cost-plus price on existing feasible grids with joint ladder, minimizing summed squared relative displacement. Not a replacement baseline or policy update.",
                "projected_baseline_rule_failures": dict(projected_failures),
                "projected_baseline_forecast_revenue": projected_forecast,
                "projected_baseline_forecast_gross_profit": projected_profit,
                "legal_grid_revenue_maximum_with_family": maximum_revenue,
                "legal_grid_revenue_maximum_gross_profit": maximum_profit,
                "maximum_revenue_uplift_vs_projected_pct": 100 * (maximum_revenue / projected_forecast - 1),
                "maximum_revenue_margin_rate_delta_vs_projected": maximum_profit / maximum_revenue - projected_profit / projected_forecast},
            "per_sku": per_sku}


async def study(args):
    results = []
    for seed in args.seeds:
        with tempfile.TemporaryDirectory(prefix="pricing-feasibility-") as temp:
            directory = Path(temp)
            seed_database(directory / "commerce.db", sku_count=args.skus, days=180, seed=seed,
                          as_of=args.as_of, data_dir=directory, categories=("Beverages",))
            upstream = create_app(directory / "commerce.db")
            commerce = CommerceClient("http://feasibility-commerce", httpx.ASGITransport(app=upstream))
            async with upstream.router.lifespan_context(upstream):
                context = await commerce.context()
            truth = read_evaluation_truth(directory / "commerce.db")
            results.append(await asyncio.to_thread(snapshot, context, read_competitors(directory), truth,
                                                    seed, args.iterations, args.horizon))
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "seeds": args.seeds, "sku_count_per_seed": args.skus,
            "as_of": args.as_of.isoformat(), "iterations": args.iterations, "horizon_days": args.horizon,
            "freshness_clock": "Actual UTC evaluation date; source fixture date is not used to bypass freshness decay.",
            "evaluation_only": True, "production_policy_or_baseline_changed": False, "fixtures": results,
            "bound_derivation": "r(p)=p*min(q*(p/current)^(elasticity+0.06),stock). On each side of the stock crossing it is a power or linear function, hence maxima over a legal continuous interval occur at an endpoint or crossing. Summing independent SKU maxima relaxes family/tick constraints and bounds any joint legal policy. The forecast-grid bound independently maximizes each existing MC candidate, relaxing family and profit constraints."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43])
    parser.add_argument("--skus", type=int, default=500)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--horizon", type=int, default=14)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--output", type=Path, default=Path("data/effectiveness_feasibility.json"))
    args = parser.parse_args()
    result = asyncio.run(study(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "fixtures": [{key: fixture[key] for key in
        ("seed", "all_sku_accuracy", "diagnosis", "upper_bounds", "original_baseline_constraint_failure_counts", "analytical_counterfactual_only")}
        for fixture in result["fixtures"]]}, indent=2))


if __name__ == "__main__":
    main()
