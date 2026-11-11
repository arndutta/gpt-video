"""Deterministic stability signals and optimizer damping constraints."""

from datetime import datetime, timezone
from decimal import Decimal
import math
import statistics

from .models import GovernancePolicy


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _ordered(history, sku):
    return sorted((row for row in history if row.get("sku") == sku
                   and Decimal(str(row["prior_price"])) != Decimal(str(row["new_price"]))),
                  key=lambda row: (row.get("applied_at", ""), row.get("id", 0)))


def analyze_stability(product: dict, candidate: str | float, history: list[dict],
                      category_prices: list[dict] | None = None,
                      policy: GovernancePolicy | None = None,
                      error_series: list[float] | None = None, *, at: datetime | None = None) -> dict:
    policy = policy or GovernancePolicy()
    recent = _ordered(history, product["sku"])[-policy.oscillation_window:]
    current, proposed = float(product["current_price"]), float(candidate)
    deltas = [float(row["new_price"]) - float(row["prior_price"]) for row in recent]
    if proposed != current:
        deltas.append(proposed - current)
    signs = [1 if delta > 0 else -1 for delta in deltas if delta]
    reversals = sum(a != b for a, b in zip(signs, signs[1:]))
    tick = float(product["rounding_increment"])
    old_prices = [float(row["prior_price"]) for row in recent]
    returns = proposed != current and any(abs(proposed - price) < tick / 2 for price in old_prices)
    oscillation = reversals >= policy.reversals_threshold or returns
    historical = old_prices + [float(row["new_price"]) for row in recent]
    historical_z = None
    if len(historical) >= 5 and statistics.pstdev(historical) > tick:
        historical_z = abs(proposed - statistics.mean(historical)) / statistics.pstdev(historical)
    peers = [float(row["current_price"]) / max(float(row["size"]), 1)
             for row in (category_prices or []) if row["category"] == product["category"]]
    category_z = None
    if len(peers) >= 5:
        logs = [math.log(price) for price in peers if price > 0]
        if logs:
            # A 1% log-price scale floor avoids division by zero for a category
            # with identical unit prices while retaining a meaningful anomaly test.
            deviation = max(statistics.pstdev(logs), .01)
            category_z = abs(math.log(proposed / product["size"]) - statistics.mean(logs)) / deviation
    anomalous = any(z is not None and z > policy.anomaly_z_threshold
                    for z in (historical_z, category_z))
    latest = _time(recent[-1].get("applied_at")) if recent else None
    clock = at or datetime.now(timezone.utc)
    elapsed = max((clock - latest).total_seconds(), 0) if latest else None
    cooldown = (proposed != current and elapsed is not None
                and elapsed < policy.minimum_change_seconds)
    errors = [abs(float(value)) for value in (error_series or []) if math.isfinite(float(value))]
    convergence = "pending"
    if len(errors) >= 6:
        earlier, latest_error = statistics.mean(errors[-6:-3]), statistics.mean(errors[-3:])
        convergence = "widening" if latest_error > earlier * 1.1 else "narrowing" if latest_error < earlier * .9 else "stable"
    return {"oscillation": bool(oscillation), "direction_reversals": reversals,
            "recent_price_return": bool(returns), "window": policy.oscillation_window,
            "reversals_threshold": policy.reversals_threshold,
            "damping_applied": bool(oscillation), "damping_fraction": policy.damping_fraction,
            "historical_z": historical_z, "category_z": category_z,
            "anomaly_z_threshold": policy.anomaly_z_threshold, "novel_market": bool(anomalous),
            "cooldown_active": bool(cooldown), "seconds_since_change": elapsed,
            "minimum_change_seconds": policy.minimum_change_seconds,
            "convergence_status": convergence, "error_observations": len(errors),
            "signals": [name for name, flag in (("oscillation", oscillation), ("anomalous_price", anomalous),
                        ("cooldown", cooldown), ("widening_forecast_error", convergence == "widening")) if flag]}


def damping_bounds(product: dict, history: list[dict], policy: GovernancePolicy | None = None):
    """Pass these bounds into candidate construction before choosing an optimum.

    Existing oscillation is retained even when a smaller final step avoids a new
    reversal. Candidate-triggered oscillation is checked again at validation.
    """
    policy = policy or GovernancePolicy()
    signals = analyze_stability(product, product["current_price"], history, policy=policy)
    current = Decimal(str(product["current_price"]))
    maximum = min(Decimal(str(product["max_change_pct"])),
                  Decimal(str(policy.maximum_change_pct if policy.maximum_change_pct is not None else 1)))
    fraction = Decimal(str(policy.damping_fraction)) if signals["oscillation"] else Decimal(1)
    step = current * maximum * fraction
    return float(current - step), float(current + step), signals
