"""Bounded business signals for cited context, and effective numerical constraints."""

from collections import defaultdict, Counter
from datetime import date, timedelta
from decimal import Decimal
import math
import statistics

from .quality import competitor_freshness


def effective_catalog(catalog, policy):
    result = []
    for product in catalog:
        p = dict(product)
        p["minimum_margin_pct"] = max(float(p["minimum_margin_pct"]), policy.minimum_margin_pct or 0)
        p["max_change_pct"] = min(float(p["max_change_pct"]), policy.maximum_change_pct if policy.maximum_change_pct is not None else 1.)
        if policy.rounding_increment:
            original = int(Decimal(p["rounding_increment"]) * 100)
            configured = int(Decimal(policy.rounding_increment) * 100)
            p["rounding_increment"] = f"{Decimal(math.lcm(original, configured)) / 100:.2f}"
        result.append(p)
    return result


def business_context(context, competitors):
    sales, feed = defaultdict(list), defaultdict(list)
    for row in context["sales"]:
        sales[row["sku"]].append(row)
    for row in competitors:
        feed[row["sku"]].append(row)
    stock = {i["sku"]: i["on_hand"] for i in context["inventory"]}
    rows = []
    for product in context["catalog"]:
        sku = product["sku"]
        history = sorted(sales[sku], key=lambda s: s["date"])[-30:]
        velocity = statistics.mean(i["units"] for i in history) if history else 0.
        cover = stock[sku] / velocity if velocity > 0 else None
        flag = "out_of_stock" if stock[sku] == 0 else "no_observed_demand" if cover is None else "stockout_risk" if cover < 7 else "overstock" if cover > 60 else "normal"
        quotes = feed[sku]
        median = statistics.median(float(i["price"]) for i in quotes) if quotes else None
        freshness = competitor_freshness(quotes)
        rows.append({"sku": sku, "category": product["category"], "inventory_flag": flag, "cover_days": cover,
                     "observed_daily_units": velocity, "competitor_median": median,
                     "current_market_gap_pct": 100 * (float(product["current_price"]) / median - 1) if median else None,
                     "competitor_status": "missing" if not quotes else "stale" if freshness == 0 else "available",
                     "competitor_freshness": freshness})
    gaps = [r["current_market_gap_pct"] for r in rows if r["current_market_gap_pct"] is not None]
    examples = sorted(rows, key=lambda r: (r["inventory_flag"] == "normal", -abs(r["current_market_gap_pct"] or 0), r["sku"]))[:25]
    return {"inventory_flags": dict(Counter(r["inventory_flag"] for r in rows)),
            "competitor_status": dict(Counter(r["competitor_status"] for r in rows)),
            "median_current_market_gap_pct": statistics.median(gaps) if gaps else None,
            "representative_skus": examples, "representative_limit": 25,
            "velocity_basis": "Mean of at most 30 most recent aggregated daily observations per SKU"}
