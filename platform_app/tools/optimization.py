"""Constrained candidate grids and deterministic product-family selection."""

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

import numpy as np


OBJECTIVE_WEIGHTS = {
    "revenue": (0.8, 0.2), "revenue-weighted": (0.8, 0.2),
    "margin": (0.2, 0.8), "margin-weighted": (0.2, 0.8), "balanced": (0.5, 0.5),
}
BASELINE_POLICY_VERSION = "cost-plus-category-discount-v1"
DEFAULT_BASELINE_POLICY = {"markup": 0.4, "discount": 0.0}
BASELINE_CATEGORY_POLICY = {
    "Beverages": {"markup": 0.4, "discount": 0.0},
    "Snacks": {"markup": 0.45, "discount": 0.05},
    "Household": {"markup": 0.35, "discount": 0.03},
}


def baseline_policy(product: dict | None = None) -> dict:
    common = {"version": BASELINE_POLICY_VERSION,
              "formula": "cost * (1 + markup) * (1 - discount), rounded half-up to the price tick"}
    if product is None:
        return {**common, "default": dict(DEFAULT_BASELINE_POLICY),
                "categories": {key: dict(value) for key, value in BASELINE_CATEGORY_POLICY.items()}}
    category = product.get("category", "")
    return {**common, "category": category,
            **BASELINE_CATEGORY_POLICY.get(category, DEFAULT_BASELINE_POLICY),
            "rounding_increment": product.get("rounding_increment", "0.01")}


def objective_weights(objective: str) -> dict:
    if objective not in OBJECTIVE_WEIGHTS:
        raise ValueError("objective must be balanced, revenue-weighted, or margin-weighted")
    revenue, profit = OBJECTIVE_WEIGHTS[objective]
    return {"revenue": revenue, "gross_profit": profit}


def money(value: float | Decimal) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def feasible_prices(product: dict, bounds: tuple[float, float] | None = None) -> list[float]:
    current, cost = Decimal(product["current_price"]), Decimal(product["cost"])
    change = Decimal(str(product.get("max_change_pct", 0.2)))
    margin = Decimal(str(product.get("minimum_margin_pct", 0.15)))
    tick = Decimal(str(product.get("rounding_increment", "0.01")))
    lower = max(Decimal(product["map_price"]), Decimal(product["min_price"]),
                cost / (1 - margin), current * (1 - change))
    upper = min(Decimal(product["max_price"]), current * (1 + change))
    if bounds is not None:
        lower = max(lower, Decimal(str(bounds[0])))
        upper = min(upper, Decimal(str(bounds[1])))
    if lower > upper:
        return []
    raw = np.linspace(float(lower), float(upper), 21).tolist() + [float(current)]
    prices = set()
    for value in raw:
        price = (Decimal(str(value)) / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick
        if lower <= price <= upper:
            prices.add(float(price))
    # Ensure the smallest feasible price is retained even when the grid rounds below it.
    floor_tick = (lower / tick).quantize(Decimal("1"), rounding=ROUND_CEILING) * tick
    if floor_tick <= upper:
        prices.add(float(floor_tick))
    return sorted(prices)


def baseline_price(product: dict) -> float:
    policy = baseline_policy(product)
    proposed = Decimal(product["cost"]) * (1 + Decimal(str(policy["markup"])))
    proposed *= 1 - Decimal(str(policy["discount"]))
    tick = Decimal(str(product.get("rounding_increment", "0.01")))
    return float(max(tick, (proposed / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick))


def objective_scores(draws: dict[str, np.ndarray], objective: str) -> np.ndarray:
    revenues = np.mean(draws["revenue"], axis=1)
    profits = np.mean(draws["gross_profit"], axis=1)
    weights = objective_weights(objective)
    revenue_weight, profit_weight = weights["revenue"], weights["gross_profit"]
    return revenue_weight * revenues / max(float(np.max(revenues)), 1) + profit_weight * profits / max(float(np.max(np.abs(profits))), 1)


def objective_sample_scores(draws: dict[str, np.ndarray], objective: str) -> np.ndarray:
    """Sample scores use the same fixed normalization as the expected objective."""
    weights = objective_weights(objective)
    revenue_scale = max(float(np.max(np.mean(draws["revenue"], axis=1))), 1)
    profit_scale = max(float(np.max(np.abs(np.mean(draws["gross_profit"], axis=1)))), 1)
    return (weights["revenue"] * draws["revenue"] / revenue_scale
            + weights["gross_profit"] * draws["gross_profit"] / profit_scale)


def select_family_prices(prepared: list[dict], catalog: list[dict]) -> dict[str, float]:
    """Joint monotone-price dynamic program, including unchanged/skipped siblings."""
    by_sku = {item["product"]["sku"]: item for item in prepared}
    families = {}
    for product in catalog:
        families.setdefault(product.get("family_id") or product["sku"], []).append(product)
    selected = {}
    for family in families.values():
        ordered = sorted(family, key=lambda product: (float(product.get("size", 1)), product["sku"]))
        options, scores = [], []
        for product in ordered:
            item = by_sku.get(product["sku"])
            options.append(item["prices"] if item else [float(product["current_price"])])
            scores.append(item["scores"] if item else np.array([0.0]))
        totals = [np.asarray(scores[0])]
        back_links = []
        for index in range(1, len(ordered)):
            next_totals = np.full(len(options[index]), -np.inf)
            parents = np.full(len(options[index]), -1, dtype=int)
            for candidate_index, price in enumerate(options[index]):
                eligible = [position for position, earlier_price in enumerate(options[index - 1])
                            if earlier_price <= price + 1e-9 and np.isfinite(totals[-1][position])]
                if eligible:
                    best = max(eligible, key=lambda position: (totals[-1][position], -position))
                    next_totals[candidate_index] = totals[-1][best] + scores[index][candidate_index]
                    parents[candidate_index] = best
            totals.append(next_totals)
            back_links.append(parents)
        if not np.any(np.isfinite(totals[-1])):
            continue
        choice = int(np.argmax(totals[-1]))
        for index in range(len(ordered) - 1, -1, -1):
            product = ordered[index]
            if product["sku"] in by_sku:
                selected[product["sku"]] = options[index][choice]
            if index:
                choice = int(back_links[index - 1][choice])
    return selected
