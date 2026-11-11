"""Every deterministic veto remains absolute in each operating mode."""

from decimal import Decimal

import pytest

from commerce.storage import connect
from governance_helpers import recommendation, setup_governance
from platform_app.governance import GovernanceError


@pytest.mark.parametrize("mode", ["supervised", "assisted", "autonomous"])
@pytest.mark.parametrize("rule", ["map_floor", "margin_floor", "max_change", "category_bounds",
                                  "rounding_policy", "price_ladder", "personal_pricing"])
async def test_every_rule_vetoes_in_every_mode_and_human_override(tmp_path, mode, rule):
    service, commerce, path = setup_governance(tmp_path)
    await service.set_mode(mode, hold_seconds=0)
    products = (await commerce.all("/catalog"))["items"]
    product = products[0]
    candidate = recommendation(product)
    price = Decimal(candidate["proposed_price"])
    with connect(path) as db:
        if rule == "map_floor":
            db.execute("UPDATE products SET map_price=? WHERE sku=?", (str(price + 1), product["sku"]))
        elif rule == "margin_floor":
            cost = price * (1 - Decimal(str(product["minimum_margin_pct"]))) + Decimal("0.01")
            db.execute("UPDATE products SET cost=? WHERE sku=?", (str(cost), product["sku"]))
        elif rule == "max_change":
            db.execute("UPDATE products SET max_change_pct=.001 WHERE sku=?", (product["sku"],))
        elif rule == "category_bounds":
            db.execute("UPDATE products SET max_price=? WHERE sku=?", (product["current_price"], product["sku"]))
        elif rule == "rounding_policy":
            db.execute("UPDATE products SET rounding_increment='0.05' WHERE sku=?", (product["sku"],))
            if price % Decimal("0.05") == 0:
                candidate["proposed_price"] = str(price + Decimal("0.01"))
        elif rule == "price_ladder":
            middle = (Decimal(product["current_price"]) + price) / 2
            db.execute("UPDATE prices SET current_price=? WHERE sku=?", (f"{middle:.2f}", products[1]["sku"]))
        else:
            candidate["context"] = {"loyalty_id": "forbidden-personal-target"}
        db.commit()
    [item] = await service.register("matrix", [candidate])
    assert item["status"] == "blocked" and item["band"] == "escalate"
    assert not next(result for result in item["compliance"]["rules"] if result["rule"] == rule)["passed"]
    for action in ({"action": "approve", "reason": "Cannot waive compliance"},
                   {"action": "override", "price": product["current_price"], "reason": "Cannot waive compliance"}):
        with pytest.raises(GovernanceError):
            await service.decide(item["id"], {**action, "expected_revision": item["revision"]})
    assert not await service.dispatch_due()
    assert (await commerce.all("/price-history"))["total"] == 0
