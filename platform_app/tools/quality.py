"""Structured quality checks before any quantitative preview is produced."""

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import math

import numpy as np


def _finite_number(value: object, minimum: float = 0, strict: bool = False) -> bool:
    try:
        number = float(Decimal(str(value)))
        return math.isfinite(number) and (number > minimum if strict else number >= minimum)
    except (TypeError, ValueError, InvalidOperation):
        return False


def quality_report(catalog: list[dict], sales: list[dict], inventory: list[dict], competitors: list[dict]) -> dict:
    checks = []

    def record(check: str, severity: str, count: int, message: str) -> None:
        checks.append({"check": check, "severity": severity, "affected_records": int(count), "message": message})

    if not catalog:
        record("catalog_completeness", "error", 0, "No catalog products were supplied.")
    if not sales:
        record("sales_completeness", "error", 0, "No sales history was supplied.")
    sku_counts = Counter(str(item.get("sku", "")) for item in catalog)
    duplicated = sum(count - 1 for count in sku_counts.values() if count > 1)
    if duplicated:
        record("catalog_uniqueness", "error", duplicated, "Catalog SKU identifiers must be unique.")
    skus = set(sku_counts)
    malformed = 0
    for product in catalog:
        valid = bool(product.get("sku")) and bool(product.get("name"))
        valid &= all(_finite_number(product.get(key), strict=True) for key in
                     ["current_price", "min_price", "max_price", "rounding_increment"])
        valid &= all(_finite_number(product.get(key)) for key in ["cost", "map_price"])
        valid &= _finite_number(product.get("size", 1), strict=True)
        if valid:
            valid &= float(product["min_price"]) <= float(product["max_price"])
            valid &= _finite_number(product.get("max_change_pct", 0.2))
            if _finite_number(product.get("minimum_margin_pct", 0.15)):
                valid &= float(product.get("minimum_margin_pct", 0.15)) < 1
            else:
                valid = False
        malformed += not valid
    record("catalog_schema", "error" if malformed else "info", malformed,
           "Catalog prices/costs/bounds must be finite, with positive price ticks and valid margin floors.")
    inventory_by_sku = {str(item.get("sku")): item for item in inventory}
    missing_inventory = sum(sku not in inventory_by_sku for sku in skus)
    malformed_inventory = sum(not _finite_number(item.get("on_hand")) for item in inventory)
    if missing_inventory or malformed_inventory:
        record("inventory_completeness", "error", missing_inventory + malformed_inventory,
               "Every scoped SKU requires a finite non-negative inventory quantity.")
    else:
        record("inventory_completeness", "info", 0, "All scoped products have usable inventory.")
    if len(inventory_by_sku) != len(inventory):
        record("inventory_uniqueness", "error", len(inventory) - len(inventory_by_sku),
               "Inventory must contain one record per SKU.")
    today = datetime.now(timezone.utc).date()
    stale_inventory = invalid_inventory_dates = 0
    for item in inventory:
        try:
            age = (today - date.fromisoformat(str(item["updated_at"])[:10])).days
            stale_inventory += age > 30 or age < -1
        except (KeyError, TypeError, ValueError):
            invalid_inventory_dates += 1
    inventory_failures = stale_inventory + invalid_inventory_dates
    record("inventory_freshness", "error" if inventory_failures else "info", inventory_failures,
           "Inventory timestamps must be valid and no more than 30 days old.")
    invalid_sales = unknown_sku = 0
    valid_dates = []
    units = []
    observation_keys = []
    for item in sales:
        try:
            observation_date = date.fromisoformat(str(item["date"])[:10])
            valid = _finite_number(item.get("price"), strict=True) and _finite_number(item.get("units"))
            valid &= _finite_number(item.get("seasonal_index", 1), strict=True)
            if not valid:
                invalid_sales += 1
                continue
            valid_dates.append(observation_date)
            units.append(float(item["units"]))
            observation_keys.append((item.get("sku"), observation_date))
            unknown_sku += item.get("sku") not in skus
        except (KeyError, TypeError, ValueError):
            invalid_sales += 1
    record("sales_schema", "error" if invalid_sales else "info", invalid_sales,
           "Sales require ISO dates, positive finite prices/seasonality, and non-negative units.")
    if unknown_sku:
        record("referential_integrity", "error", unknown_sku, "Sales reference SKUs outside the supplied catalog scope.")
    duplicates = len(observation_keys) - len(set(observation_keys))
    if duplicates:
        record("sales_uniqueness", "error", duplicates, "Expected one aggregated sales observation per SKU and date.")
    stale = (today - max(valid_dates)).days if valid_dates else None
    if stale is not None:
        record("sales_freshness", "error" if stale > 30 or stale < -1 else "info", len(sales) if stale > 30 else 0,
               f"Latest history is {stale} days old; the demo gate permits at most 30 days.")
    if units:
        q1, q3 = np.quantile(units, [0.25, 0.75])
        outliers = sum(value > q3 + 3 * max(q3 - q1, 1) for value in units)
        record("sales_outliers", "warning" if outliers else "info", outliers,
               "Extreme volume observations are reported; controls/model diagnostics remain inspectable.")
    invalid_competitors = sum(not _finite_number(item.get("price"), strict=True) for item in competitors)
    if invalid_competitors:
        record("competitor_schema", "error", invalid_competitors, "Competitor prices must be finite and positive.")
    missing_competitors = len(skus - {item.get("sku") for item in competitors})
    if missing_competitors:
        record("competitor_completeness", "warning", missing_competitors,
               "Missing competitor observations increase uncertainty and lower confidence.")
    blocked = any(check["severity"] == "error" for check in checks)
    warnings = any(check["severity"] == "warning" for check in checks)
    return {"status": "failed" if blocked else "degraded" if warnings else "passed",
            "blocked": blocked, "checks": checks, "sku_count": len(catalog), "sales_count": len(sales)}


def competitor_freshness(competitors: list[dict]) -> float:
    if not competitors:
        return 0.0
    scores = []
    today = datetime.now(timezone.utc).date()
    for item in competitors:
        try:
            day = date.fromisoformat(str(item["observed_at"])[:10])
            days = (today - day).days
            scores.append(max(0.0, 1 - max(days, 0) / 14) if days >= -1 else 0.0)
        except (KeyError, ValueError, TypeError):
            scores.append(0.0)
    return float(np.mean(scores))
