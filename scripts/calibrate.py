"""Evaluation-only threshold study on independent synthetic fixtures; never updates policy."""

import argparse
import asyncio
from collections import Counter
from datetime import date, datetime, timezone
from itertools import product
import json
from pathlib import Path
import tempfile
import time

import httpx

from commerce.app import create_app as create_commerce
from commerce.evaluation import read_evaluation_truth
from commerce.seed import seed_database
from platform_app.commerce_client import CommerceClient, read_competitors
from platform_app.governance.bands import assign_band
from platform_app.governance.compliance import validate_price
from platform_app.governance.models import GovernancePolicy
from platform_app.governance.stability import analyze_stability
from platform_app.tools import analyze_catalog
from scripts.benchmark import hardware
from scripts.benchmark_metrics import evaluate, evaluator_context

CONFIDENCE_GRID = (.8, .85, .9, .95)
DELTA_GRID = (3., 5., 10.)
VOLATILITY_GRID = (.2, .35, .5)


def accuracy(items, errors):
    values = [errors[item["sku"]] for item in items]
    count = len(values)
    return {"denominator": count, "within_10pct": sum(value <= .1 for value in values),
            "over_10pct": sum(value > .1 for value in values),
            "within_10pct_share": sum(value <= .1 for value in values) / count if count else None,
            "mean_error_pct": 100 * sum(values) / count if count else None,
            "max_error_pct": 100 * max(values) if count else None,
            "all_within_10pct": all(value <= .1 for value in values) if count else None}


def threshold_study(report, context, truth, horizon, objective):
    default = GovernancePolicy()
    items = report["recommendations"]
    products, _, _, optima = evaluator_context(report, context, truth, horizon, objective)
    errors = {item["sku"]: abs(float(item["proposed_price"]) / optima[item["sku"]] - 1) for item in items}
    changes = {item["sku"]: item["proposed_price"] for item in items}
    evidence = {}
    for item in items:
        current = products[item["sku"]]
        compliance = validate_price(current, item["proposed_price"], context["catalog"], changes=changes,
                                    expected_version=item["price_version"], policy=default)
        stability = analyze_stability(current, item["proposed_price"], [], context["catalog"], default)
        evidence[item["sku"]] = (compliance, stability)
    rows = []
    for confidence, delta, volatility in product(CONFIDENCE_GRID, DELTA_GRID, VOLATILITY_GRID):
        policy = default.model_copy(update={"confidence_threshold": confidence, "auto_delta_pct": delta,
                                            "volatility_limit": volatility})
        bands, selected, escalations = Counter(), [], Counter()
        for item in items:
            compliance, stability = evidence[item["sku"]]
            verdict = assign_band(item, products[item["sku"]], compliance, stability, policy)
            bands[verdict["band"]] += 1
            if verdict["band"] == "auto_approve":
                selected.append(item)
            if verdict["band"] == "escalate":
                for reason in verdict["band_reasons"][:5]:
                    if not reason["passed"]:
                        escalations[reason["code"]] += 1
        high = [item for item in items if item["confidence"] > confidence]
        count = len(items)
        rows.append({"thresholds": {"confidence": confidence, "absolute_delta_pct": delta,
                                    "revenue_coefficient_of_variation": volatility},
                     "modeled_skus": count, "high_confidence": accuracy(high, errors),
                     "high_confidence_share_of_modeled": len(high) / count if count else None,
                     "predicted_band_counts": {band: bands[band] for band in ("auto_approve", "review", "escalate")},
                     "predicted_band_shares": {band: bands[band] / count if count else None
                                               for band in ("auto_approve", "review", "escalate")},
                     "predicted_auto_accuracy": accuracy(selected, errors),
                     "compliance_violation_skus": sum(evidence[i["sku"]][0]["status"] != "passed" for i in items),
                     "predicted_auto_compliance_violations": sum(evidence[i["sku"]][0]["status"] != "passed" for i in selected),
                     "escalation_trigger_counts": dict(escalations)})
    return rows


async def study(args):
    fixtures = []
    for seed in args.seeds:
        with tempfile.TemporaryDirectory(prefix=f"pricing-calibration-{seed}-") as temp:
            directory = Path(temp)
            seed_database(directory / "commerce.db", sku_count=args.skus, days=180, seed=seed,
                          as_of=args.as_of, data_dir=directory, categories=(args.category,))
            upstream = create_commerce(directory / "commerce.db")
            commerce = CommerceClient("http://calibration-commerce", httpx.ASGITransport(app=upstream))
            async with upstream.router.lifespan_context(upstream):
                context = await commerce.context(category=args.category)
                competitors = read_competitors(directory)
                truth = read_evaluation_truth(directory / "commerce.db")
                for objective in args.objectives:
                    started = time.perf_counter()
                    report = await asyncio.to_thread(analyze_catalog, context["catalog"], context["sales"],
                                                     context["inventory"], competitors, objective=objective,
                                                     iterations=args.iterations, seed=seed, horizon_days=args.horizon)
                    analysis_seconds = time.perf_counter() - started
                    rows = threshold_study(report, context, truth, args.horizon, objective)
                    fixtures.append({"seed": seed, "objective": objective, "input_skus": len(context["catalog"]),
                                     "confidence_model_version": report["configuration"].get("confidence_model_version"),
                                     "modeled_skus": len(report["recommendations"]), "skipped_skus": len(report["skipped"]),
                                     "analysis_seconds": analysis_seconds,
                                     "effectiveness": evaluate(report, context, truth, args.horizon, objective),
                                     "thresholds": rows})
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "hardware": hardware(),
            "configuration": {"seeds": args.seeds, "sku_count_per_seed": args.skus, "category": args.category,
                              "history_days": 180, "as_of": args.as_of.isoformat(), "iterations": args.iterations,
                              "horizon_days": args.horizon, "objectives": args.objectives,
                              "confidence_grid": CONFIDENCE_GRID, "absolute_delta_pct_grid": DELTA_GRID,
                              "volatility_grid": VOLATILITY_GRID, "fixed_policy": GovernancePolicy().model_dump()},
            "fixtures": fixtures, "selected_new_defaults": None, "system_policy_updated": False,
            "scope": "Read-only evaluation against independent synthetic seeds; no LLM calls, no running app database, no approval or Commerce push.",
            "limitations": ["Seed42 is the development fixture; seed43 is an independent same-generator comparison, not a real-market holdout.",
                "Every confidence row reports its own denominator; reducing eligible coverage does not establish a successful product target.",
                "Predicted Auto shares are deterministic band eligibility on one snapshot, not actual Assisted automatic execution or human acceptance.",
                "Compliance, margin proximity, sample minimum, market-gap norm, damping and stability settings are unchanged.",
                "Empty price history cannot establish longitudinal oscillation or convergence; no realized outcome or human precision metric is observed.",
                "Thresholds are studied without changing proposed prices or policy; no new default is selected."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43])
    parser.add_argument("--skus", type=int, default=500)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--horizon", type=int, default=14)
    parser.add_argument("--category", default="Beverages")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--objectives", choices=("balanced", "revenue", "margin"), nargs="+", default=["balanced"])
    parser.add_argument("--output", type=Path, default=Path("data/calibration_result.json"))
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds) or len(set(args.objectives)) != len(args.objectives):
        parser.error("Seeds and objectives must be distinct.")
    result = asyncio.run(study(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "fixtures": [{key: fixture[key] for key in
        ("seed", "objective", "modeled_skus", "analysis_seconds", "effectiveness")} for fixture in result["fixtures"]],
        "system_policy_updated": False, "selected_new_defaults": None}, indent=2))


if __name__ == "__main__":
    main()
