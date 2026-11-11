"""Escalate-first risk bands with inspectable values and trial thresholds."""

import math

from .models import GovernancePolicy


def assign_band(item: dict, product: dict, compliance: dict, stability: dict,
                policy: GovernancePolicy | None = None) -> dict:
    policy = policy or GovernancePolicy()
    forecast = item.get("forecast") or {}
    revenue = forecast.get("revenue", {})
    mean, variance = revenue.get("mean"), revenue.get("variance")
    volatility = (math.sqrt(float(variance)) / max(abs(float(mean)), 1e-9)
                  if mean is not None and variance is not None
                  and math.isfinite(float(mean)) and math.isfinite(float(variance))
                  and float(mean) > 0 and float(variance) >= 0 else None)
    price, cost = float(item["proposed_price"]), float(product["cost"])
    margin = (price - cost) / price
    floor = max(float(product["minimum_margin_pct"]), policy.minimum_margin_pct or 0)
    proximity = margin - floor
    gap = item.get("competitive_gap_pct")
    gap = float(gap) if gap is not None and math.isfinite(float(gap)) else None
    gap_outside_norm = gap is not None and abs(gap) > policy.market_gap_limit_pct
    novelty = bool(stability.get("novel_market") or item.get("novel_market") or gap_outside_norm)
    reasons = []

    def check(code, passed, actual, threshold, message):
        reasons.append({"code": code, "passed": bool(passed), "actual": actual,
                        "threshold": threshold, "message": message})

    check("compliance", compliance["status"] == "passed", compliance["status"], "passed", "Every rule must pass.")
    check("margin_proximity", proximity > policy.margin_proximity_buffer, proximity,
          policy.margin_proximity_buffer, "Margin headroom must exceed the proximity buffer.")
    check("volatility", volatility is not None and volatility <= policy.volatility_limit, volatility,
          policy.volatility_limit, "Normalized forecast volatility must stay within its limit.")
    check("oscillation", not stability.get("oscillation"), stability.get("oscillation", False), False,
          "An oscillation incident requires human intervention, even after damping.")
    check("novel_market", not novelty,
          {"price_anomaly": bool(stability.get("novel_market") or item.get("novel_market")),
           "competitive_gap_pct": gap, "outside_configured_gap_norm": gap_outside_norm},
          {"price_anomaly": False, "abs_market_gap_pct": policy.market_gap_limit_pct},
          "A price anomaly or market gap beyond the configured norm requires human intervention; the gap norm is an initial calibration, not a measured historical distribution.")
    escalated = any(not row["passed"] for row in reasons)
    confidence = float(item.get("confidence", 0))
    samples = int(item.get("elasticity", {}).get("sample_size", 0))
    delta = abs(float(item.get("delta_pct", 100 * (price / float(product["current_price"]) - 1))))
    check("confidence", confidence > policy.confidence_threshold, confidence, policy.confidence_threshold,
          "Automatic approval requires confidence above the threshold.")
    check("delta", delta <= policy.auto_delta_pct, delta, policy.auto_delta_pct,
          "Automatic approval requires a small price change.")
    check("sample_size", samples >= policy.minimum_sample, samples, policy.minimum_sample,
          "Automatic approval requires sufficient eligible sales history.")
    check("cooldown", not stability.get("cooldown_active"), stability.get("seconds_since_change"),
          policy.minimum_change_seconds, "A price change must respect its minimum interval.")
    band = "escalate" if escalated else "auto_approve" if all(row["passed"] for row in reasons) else "review"
    return {"band": band, "band_reasons": reasons, "volatility": volatility,
            "market_novelty": {"flagged": novelty, "competitive_gap_pct": gap,
                               "gap_limit_pct": policy.market_gap_limit_pct,
                               "basis": "configured absolute market-gap norm and historical price anomaly signals"},
            "margin_headroom": proximity}
