"""Aligned outcome readback, duplicate exclusion, and bounded inspectable learning."""

from datetime import date, timedelta
from uuid import uuid4

import pytest

from platform_app.feedback import Feedback
from platform_app.storage import Store
from platform_app.tools.elasticity import estimate_elasticity
from platform_app.tools.refinement import refine_estimate
from test_analysis import fixtures


class SalesFixture:
    def __init__(self):
        self.rows, self.calls = [], []

    async def all(self, path, **query):
        self.calls.append((path, query))
        return {"items": [r for r in self.rows if r["sku"] == query["sku"]]}


def applied(store, *, start=date(2026, 1, 1), horizon=10, sku="SKU-1", expected=100):
    run = store.create_run({"kind": "grounded", "horizon_days": horizon})
    return {"id": str(uuid4()), "run_id": run["id"], "sku": sku, "status": "applied",
            "current_price": "9.00", "proposed_price": "10.00", "product_evidence": {"cost": "3.00"},
            "forecast": {"units": {"mean": expected, "lower": expected * .8, "upper": expected * 1.2}},
            "execution": {"status": "applied", "applied_at": start.isoformat() + "T12:00:00+00:00"}}


def observations(item, *, horizon=10, units=10):
    start = date.fromisoformat(item["execution"]["applied_at"][:10]) + timedelta(days=1)
    return [{"sku": item["sku"], "date": (start + timedelta(days=i)).isoformat(),
             "price": item["proposed_price"], "units": units} for i in range(horizon)]


@pytest.fixture
def feedback(tmp_path):
    store, sales = Store(tmp_path), SalesFixture()
    return Feedback(store, sales), store, sales


async def test_immature_outcomes_are_pending_without_fabricated_zero(feedback):
    service, store, sales = feedback
    item = applied(store)
    result = await service.refresh([item], today=date(2026, 1, 3))
    assert result["items"][0]["status"] == "pending" and not sales.calls
    assert "units" not in result["items"][0]["result"] and result["learning"] == {}


async def test_missing_day_is_pending_but_explicit_zero_sales_are_observed(feedback):
    service, store, sales = feedback
    item = applied(store)
    sales.rows = observations(item)[:-1]
    result = await service.refresh([item], today=date(2026, 2, 1))
    assert result["items"][0]["status"] == "pending"
    sales.rows = observations(item, units=0)
    result = await service.refresh([item], today=date(2026, 2, 1))
    assert result["items"][0]["status"] == "observed"
    assert result["items"][0]["result"]["units"] == 0
    assert result["items"][0]["result"]["absolute_percentage_error"] == 1


async def test_mature_window_is_provenanced_and_never_counted_twice(feedback):
    service, store, sales = feedback
    item = applied(store)
    sales.rows = observations(item)
    first = await service.refresh([item], today=date(2026, 2, 1))
    outcome = first["items"][0]["result"]
    assert outcome["start"] == "2026-01-02" and outcome["end_exclusive"] == "2026-01-12"
    assert outcome["units"] == 100 and outcome["revenue"] == 1000 and outcome["gross_profit"] == 700
    assert outcome["interval_covered"] is True and len(outcome["provenance_hash"]) == 64
    assert first["items"][0]["run_id"] == item["run_id"]
    assert await service.refresh([item], today=date(2026, 2, 1)) == first
    assert len(sales.calls) == 1 and first["learning"]["SKU-1"]["observations"] == 1
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM learning_versions").fetchone()[0] == 1


async def test_overlapping_new_decision_is_excluded_from_learning(feedback):
    service, store, sales = feedback
    first, second = applied(store), applied(store)
    sales.rows = observations(first)
    result = await service.refresh([first, second], today=date(2026, 2, 1))
    assert {r["status"] for r in result["items"]} == {"observed", "excluded"}
    assert result["learning"]["SKU-1"]["observations"] == 1


async def test_intervening_price_or_missing_forecast_excludes_outcome(feedback):
    service, store, sales = feedback
    item = applied(store)
    sales.rows = observations(item)
    sales.rows[0]["price"] = "10.20"
    result = await service.refresh([item], today=date(2026, 2, 1))
    assert result["items"][0]["status"] == "excluded" and result["learning"] == {}
    second = applied(store, sku="SKU-2")
    second.pop("forecast")
    sales.rows.extend(observations(second))
    result = await service.refresh([second], today=date(2026, 2, 1))
    assert next(r for r in result["items"] if r["item_id"] == second["id"])["status"] == "excluded"


async def test_bounded_learning_requires_disjoint_evidence_and_can_widen(feedback):
    service, store, sales = feedback
    for index in range(9):
        item = applied(store, start=date(2026, 1, 1) + timedelta(days=12 * index))
        sales.rows.extend(observations(item, units=20 + index))
        await service.refresh([item], today=date(2027, 1, 1))
    state = service.states()["SKU-1"]
    assert state["observations"] == 9 and state["observed_days"] == 90
    assert abs(state["elasticity_offset"]) <= .5 and abs(state["last_adjustment"]) <= .1
    assert 1 < state["uncertainty_multiplier"] <= 2 and state["convergence"] == "widening"
    product, rows, *_ = fixtures()
    fitted = estimate_elasticity(product, rows)
    refined = refine_estimate(fitted, state)
    assert refined.upper - refined.lower >= fitted.upper - fitted.lower
    with store.connection() as db:
        with pytest.raises(Exception, match="immutable"):
            db.execute("DELETE FROM learning_versions")


async def test_good_evidence_tightens_only_with_minimum_observations(feedback):
    service, store, sales = feedback
    for index in range(3):
        item = applied(store, start=date(2026, 1, 1) + timedelta(days=12 * index))
        sales.rows.extend(observations(item))
        await service.refresh([item], today=date(2027, 1, 1))
        state = service.states()["SKU-1"]
        assert state["uncertainty_multiplier"] == 1 if index < 2 else .75 <= state["uncertainty_multiplier"] < 1
    assert state["elasticity_offset"] == 0 and state["mean_absolute_error"] == 0


async def test_short_windows_cannot_refine_or_claim_calibrated_confidence(feedback):
    from platform_app.tools import analyze_catalog
    service, store, sales = feedback
    for index in range(3):
        item = applied(store, start=date(2026, 1, 1) + timedelta(days=2 * index), horizon=1, expected=10)
        sales.rows.extend(observations(item, horizon=1))
        await service.refresh([item], today=date(2027, 1, 1))
    state = service.states()["SKU-1"]
    assert state["observations"] == state["observed_days"] == 3
    assert state["uncertainty_multiplier"] == 1 and state["calibration_ready"] is False
    product, rows, inventory, competitor = fixtures(sku="SKU-1")
    fitted = estimate_elasticity(product, rows)
    assert refine_estimate(fitted, state) == fitted
    report = analyze_catalog([product], rows, [inventory], [competitor], iterations=100,
                             learning={"SKU-1": state})
    factors = report["recommendations"][0]["confidence_factors"]
    assert factors["calibrated"] is False and "realized_accuracy" not in factors


async def test_missing_cost_evidence_is_excluded_instead_of_assuming_zero(feedback):
    service, store, sales = feedback
    item = applied(store)
    item["product_evidence"] = {}
    sales.rows = observations(item)
    result = await service.refresh([item], today=date(2026, 2, 1))
    assert result["items"][0]["status"] == "excluded"
    assert "cost evidence" in result["items"][0]["result"]["reason"]
    assert result["learning"] == {}
