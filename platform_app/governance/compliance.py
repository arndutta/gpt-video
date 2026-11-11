"""Independent platform rule evaluation. Commerce repeats its own veto."""

from decimal import Decimal, InvalidOperation
import re

from platform_app.constraints import constraint_rules
from .models import GovernancePolicy


PERSONAL_KEYS = {"customer_id", "consumer_id", "email", "phone", "ip_address",
                 "postcode", "zip_code", "birth_date", "personal_attributes",
                 "customer_segment", "individual_price"}
PERSONAL_KEY = re.compile(r"(?:^|_)(?:customer|consumer|loyalty|personal|person|email|phone|address|postcode|zipcode)(?:_|$)", re.I)


def contains_personal_pricing(value) -> bool:
    if isinstance(value, dict):
        return any(str(key).lower() in PERSONAL_KEYS or PERSONAL_KEY.search(str(key)) or contains_personal_pricing(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(contains_personal_pricing(item) for item in value)
    return False


def validate_price(product: dict | None, price: str, catalog: list[dict], *,
                   changes: dict[str, str] | None = None, expected_version: int | None = None,
                   policy: GovernancePolicy | None = None, request: dict | None = None,
                   constraints=None) -> dict:
    policy = policy or GovernancePolicy()
    rules = []

    def add(rule, passed, actual, threshold, message):
        rules.append({"rule": rule, "passed": bool(passed), "actual": actual,
                      "threshold": threshold, "message": message})

    add("personal_pricing", not contains_personal_pricing(request or {}),
        "personalized" if contains_personal_pricing(request or {}) else "SKU aggregate", "SKU aggregate only",
        "Consumer-specific pricing is prohibited.")
    if product is None:
        add("known_sku", False, None, "existing Commerce SKU", "SKU is absent from Commerce.")
        return {"status": "failed", "rules": rules}
    try:
        proposed = Decimal(str(price))
        if not proposed.is_finite() or proposed <= 0 or proposed.as_tuple().exponent < -2:
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        add("valid_price", False, None, "positive finite decimal with at most two decimals", "Invalid price.")
        return {"status": "failed", "rules": rules}
    current, cost = Decimal(str(product["current_price"])), Decimal(str(product["cost"]))
    margin = (proposed - cost) / proposed
    floor = max(Decimal(str(product["minimum_margin_pct"])),
                Decimal(str(policy.minimum_margin_pct or 0)))
    max_change = min(Decimal(str(product["max_change_pct"])),
                     Decimal(str(policy.maximum_change_pct if policy.maximum_change_pct is not None else 1)))
    add("source_price_version", expected_version is None or expected_version == product["price_version"],
        product["price_version"], expected_version, "The source price version must remain current.")
    add("map_floor", proposed >= Decimal(str(product["map_price"])), str(proposed), product["map_price"],
        "Price must meet the minimum advertised price.")
    add("margin_floor", margin >= floor, float(margin), float(floor), "Gross margin must meet the floor.")
    delta = abs(proposed - current) / current
    add("max_change", delta <= max_change, float(delta), float(max_change), "Price change must stay within its limit.")
    add("category_bounds", Decimal(str(product["min_price"])) <= proposed <= Decimal(str(product["max_price"])),
        str(proposed), {"minimum": product["min_price"], "maximum": product["max_price"]},
        "Price must stay inside category bounds.")
    tick = Decimal(str(product["rounding_increment"]))
    policy_tick = Decimal(policy.rounding_increment) if policy.rounding_increment else tick
    add("rounding_policy", proposed % tick == 0 and proposed % policy_tick == 0,
        str(proposed), {"commerce": str(tick), "platform": str(policy_tick)}, "Price must match both price increments.")
    updates = dict(changes or {})
    updates[product["sku"]] = str(proposed)
    family = sorted((item for item in catalog if item["family_id"] == product["family_id"]),
                    key=lambda item: (item["size"], item["sku"]))
    ladder = [{"sku": item["sku"], "size": item["size"],
               "price": str(updates.get(item["sku"], item["current_price"]))} for item in family]
    valid = all(a["size"] == b["size"] or Decimal(a["price"]) <= Decimal(b["price"])
                for a, b in zip(ladder, ladder[1:]))
    add("price_ladder", valid, ladder, "nondecreasing total price with size", "Family prices must preserve the size ladder.")
    rules.extend(constraint_rules(product, proposed, constraints))
    return {"status": "passed" if all(row["passed"] for row in rules) else "failed", "rules": rules}
