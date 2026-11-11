"""Price-conditioned simulation shared by catalog analysis and what-if previews."""

import hashlib
import numpy as np

from .elasticity import ElasticityEstimate

ENGINE_VERSION = "quantitative-preview-v1"


def summarize(draws: np.ndarray) -> dict:
    lower, median, upper = np.quantile(draws, [0.025, 0.5, 0.975])
    return {
        "mean": float(np.mean(draws)), "median": float(median),
        "lower": float(lower), "upper": float(upper),
        "variance": float(np.var(draws)), "confidence_level": 0.95,
    }


def stable_seed(seed: int, sku: str) -> int:
    value = f"{ENGINE_VERSION}:{seed}:{sku}".encode()
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")


def sample_forecasts(
    product: dict, estimate: ElasticityEstimate, inventory: dict,
    competitors: list[dict], prices: list[float], iterations: int,
    seed: int, horizon_days: int,
) -> dict[str, np.ndarray]:
    """Rows are candidate prices; columns share the same uncertainty realization.

    Catalog aggregation preserves column alignment. Seasonal/cost shared shocks are
    generated from a run seed, while SKU-specific uncertainty has independent streams.
    The four uncertainty factors are initial inspectable demo assumptions, not learned
    distributions or evidence of a calibrated forecast.
    """
    rng = np.random.default_rng(stable_seed(seed, product["sku"]))
    shared = np.random.default_rng(stable_seed(seed, "__shared_shocks__"))
    seasonal_common, cost_common = shared.normal(size=(2, iterations))
    elasticity = estimate.estimate + estimate.standard_error * rng.standard_t(
        estimate.degrees_of_freedom, iterations,
    )
    seasonal_sigma = max(0.04, min(estimate.residual_sigma, 0.35))
    seasonal_z = 0.6 * seasonal_common + 0.8 * rng.normal(size=iterations)
    seasonal = np.exp(seasonal_sigma * seasonal_z - seasonal_sigma ** 2 / 2)
    cost_z = 0.6 * cost_common + 0.8 * rng.normal(size=iterations)
    costs = float(product["cost"]) * np.exp(0.02 * cost_z - 0.02 ** 2 / 2)
    competitor_sigma = 0.035 if competitors else 0.12
    competitor_response = np.exp(
        0.4 * competitor_sigma * rng.normal(size=iterations)
        - (0.4 * competitor_sigma) ** 2 / 2,
    )
    candidates = np.asarray(prices, dtype=float)[:, None]
    ratios = candidates / float(product["current_price"])
    # The response draws directly consume the fitted elasticity and its uncertainty.
    log_price_effect = np.clip(np.log(ratios) * elasticity[None, :], -30, 25)
    demand = estimate.daily_demand * np.exp(log_price_effect) * seasonal * competitor_response
    # A small uncertain competitor follow-through is explicit, rather than an LLM claim.
    demand *= ratios ** 0.06
    stress = product.get("_stress", "none")
    if stress == "demand_collapse":
        demand *= .5
    elif stress == "competitor_undercut":
        demand *= .8 ** .4
    elif stress == "cost_spike":
        costs *= 1.2
    elif stress != "none":
        raise ValueError("Unknown stress preset")
    units = np.minimum(demand * horizon_days, float(inventory["on_hand"]))
    revenue = candidates * units
    gross_profit = (candidates - costs[None, :]) * units
    margin_rate = (candidates - costs[None, :]) / candidates
    stock_cover = np.maximum(float(inventory["on_hand"]) - units, 0) / np.maximum(demand, 1e-9)
    return {
        "revenue": revenue, "gross_profit": gross_profit,
        "margin_rate": margin_rate, "units": units, "cover_days": stock_cover,
    }


def forecast_summary(draws: dict[str, np.ndarray], index: int, product: dict) -> dict:
    result = {metric: summarize(values[index]) for metric, values in draws.items()}
    floor = float(product.get("minimum_margin_pct", 0.15))
    result["below_margin_floor_probability"] = float(np.mean(draws["margin_rate"][index] < floor))
    return result


def configuration(iterations: int, seed: int, horizon_days: int) -> dict:
    return {
        "engine_version": ENGINE_VERSION, "iterations": iterations, "seed": seed,
        "horizon_days": horizon_days, "interval_level": 0.95,
        "stock_policy": "fixed on-hand inventory; no replenishment",
        "cost_drift_sigma": 0.02, "competitor_sigma_present": 0.035,
        "competitor_sigma_missing": 0.12, "shared_shock_correlation": 0.36,
        "forecast_calibrated": False,
    }


def validate_simulation_parameters(iterations: int, seed: int, horizon_days: int) -> None:
    if not isinstance(iterations, int) or not 100 <= iterations <= 20_000:
        raise ValueError("iterations must be an integer between 100 and 20000")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if not isinstance(horizon_days, int) or not 1 <= horizon_days <= 365:
        raise ValueError("horizon_days must be an integer between 1 and 365")
