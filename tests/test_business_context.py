"""Aggregate business context preserves missingness and uses actual bounded signals."""

from copy import deepcopy
from datetime import datetime, timezone

from platform_app.governance import GovernancePolicy
from platform_app.tools.context import business_context, effective_catalog
from test_analysis import fixtures


def test_business_signals_distinguish_zero_stock_missing_demand_and_stale_feed():
    first, second, third = (fixtures(sku=f"SKU-{i}") for i in range(1, 4))
    first[2]["on_hand"], second[2]["on_hand"], third[2]["on_hand"] = 0, 100_000, 10
    second[3]["observed_at"] = "2020-01-01T00:00:00+00:00"
    context = {"catalog": [first[0], second[0], third[0]], "sales": first[1] + second[1],
               "inventory": [first[2], second[2], third[2]]}
    original = deepcopy(context)
    result = business_context(context, [first[3], second[3]])
    assert result["inventory_flags"] == {"out_of_stock": 1, "overstock": 1, "no_observed_demand": 1}
    assert result["competitor_status"] == {"available": 1, "stale": 1, "missing": 1}
    missing = next(i for i in result["representative_skus"] if i["sku"] == "SKU-3")
    assert missing["cover_days"] is None and missing["competitor_median"] is None
    assert missing["observed_daily_units"] == 0 and missing["current_market_gap_pct"] is None
    assert context == original


def test_effective_constraints_only_tighten_and_tick_intersection_is_exact():
    product = fixtures()[0]
    product["rounding_increment"] = "0.02"
    original = deepcopy(product)
    result = effective_catalog([product], GovernancePolicy(maximum_change_pct=.04, minimum_margin_pct=.4,
                                                          rounding_increment="0.03"))[0]
    assert result["max_change_pct"] == .04 and result["minimum_margin_pct"] == .4
    assert result["rounding_increment"] == "0.06" and product == original
    weaker = effective_catalog([product], GovernancePolicy(maximum_change_pct=.9, minimum_margin_pct=.01))[0]
    assert weaker["max_change_pct"] == original["max_change_pct"]
    assert weaker["minimum_margin_pct"] == original["minimum_margin_pct"]
