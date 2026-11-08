"""Independent, deterministic Commerce validation. No model or platform imports."""

from decimal import Decimal

from commerce.models import PriceItem


def validate_item(item: PriceItem, product: dict | None) -> tuple[str, str] | None:
    if product is None:
        return "unknown_sku", "SKU does not exist in Commerce."
    price, current = item.price, Decimal(product["current_price"])
    if item.expected_version != product["price_version"]:
        return "stale_price", "Current price version changed; fetch and revalidate."
    if price < Decimal(product["map_price"]):
        return "map_floor", "Proposed price is below the minimum advertised price."
    margin = (price - Decimal(product["cost"])) / price
    if margin < Decimal(str(product["minimum_margin_pct"])):
        return "margin_floor", "Proposed price is below the required gross margin."
    if abs(price - current) / current > Decimal(str(product["max_change_pct"])):
        return "max_change", "Proposed price exceeds the maximum permitted change."
    if not Decimal(product["min_price"]) <= price <= Decimal(product["max_price"]):
        return "category_bounds", "Proposed price is outside category price bounds."
    if price % Decimal(product["rounding_increment"]):
        return "rounding_policy", "Proposed price does not match the configured price increment."
    return None


def invalid_ladder_families(products: list[dict], changes: dict[str, Decimal]) -> set[str]:
    families: dict[str, list[dict]] = {}
    for product in products:
        families.setdefault(product["family_id"], []).append(product)
    invalid = set()
    for family_id, members in families.items():
        ordered = sorted(members, key=lambda row: (row["size"], row["sku"]))
        for smaller, larger in zip(ordered, ordered[1:]):
            small_price = changes.get(smaller["sku"], Decimal(smaller["current_price"]))
            large_price = changes.get(larger["sku"], Decimal(larger["current_price"]))
            if smaller["size"] < larger["size"] and small_price > large_price:
                invalid.add(family_id)
    return invalid
