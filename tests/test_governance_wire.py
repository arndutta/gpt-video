from copy import deepcopy
from decimal import Decimal

import httpx
import pytest

from governance_helpers import recommendation, setup_governance
from commerce.storage import connect
from platform_app.commerce_client import CommerceClient, CommerceUnavailable
from platform_app.governance.transport import validate_receipt


HEALTH = {"service": "commerce", "status": "ok", "seeded": True, "catalog_count": 1,
          "as_of": "2026-11-09T00:00:00+00:00"}
HISTORY = {"id": 1, "sku": "A", "batch_key": "one", "prior_price": "10.00", "new_price": "10.50",
           "prior_version": 1, "new_version": 2, "actor": "system", "approval_kind": "automatic",
           "applied_at": "2026-11-09T00:00:00+00:00"}


@pytest.mark.parametrize("patch", [
    {"catalog_count": True}, {"catalog_count": "1"}, {"seeded": "true"},
    {"seeded": False}, {"as_of": None}, {"as_of": "2026-11-09"},
    {"service": "unexpected"}, {"status": "ready"},
])
async def test_health_contract_fails_closed(patch):
    client = CommerceClient("http://commerce", httpx.MockTransport(
        lambda request: httpx.Response(200, json={**HEALTH, **patch})))
    with pytest.raises(CommerceUnavailable):
        await client.get("/health")


@pytest.mark.parametrize("patch", [
    {"id": True}, {"new_price": "NaN"}, {"prior_price": 10.0}, {"new_version": 1},
    {"new_version": True}, {"new_price": "10.00"}, {"applied_at": "2026-11-09T00:00:00"},
    {"approval_kind": "override"}, {"sku": ""},
])
async def test_history_contract_fails_closed(patch):
    client = CommerceClient("http://commerce", httpx.MockTransport(lambda request: httpx.Response(
        200, json={"items": [{**HISTORY, **patch}], "total": 1, "as_of": HEALTH["as_of"]})))
    with pytest.raises(CommerceUnavailable):
        await client.all("/price-history")


@pytest.mark.parametrize("patch", [
    {"new_version": 1}, {"new_version": True}, {"prior_version": 2}, {"prior_price": "NaN"},
    {"prior_price": "-1"}, {"applied_at": None}, {"applied_at": "unparseable"},
    {"applied_at": "2026-11-09T00:00:00"}, {"new_price": "11.00"},
    {"rejection_code": "error"},
])
def test_receipts_are_strict_and_bound_to_original_payload(patch):
    payload = {"batch_key": "one", "items": [{"sku": "A", "price": "10.50", "expected_version": 1}]}
    receipt = {"batch_key": "one", "status": "applied", "items": [{
        "sku": "A", "status": "applied", "prior_price": "10.00", "new_price": "10.50",
        "prior_version": 1, "new_version": 2, "applied_at": HEALTH["as_of"],
        "rejection_code": None, "rejection_reason": None, **patch}]}
    with pytest.raises((ValueError, ArithmeticError, TypeError)):
        validate_receipt(receipt, payload)


async def test_human_reason_redaction_and_review_conflict(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product, variance=1600)])
    approved = await service.decide(item["id"], {"action": "approve", "expected_revision": 1,
        "reason": "Reviewed by user@example.org; api_key=not-for-storage and phone +1 555 123 4567."})
    assert "user@example.org" not in approved["approval"]["reason"]
    assert "not-for-storage" not in str(service.store.list_audit())
    assert "555 123 4567" not in str(service.store.list_audit())


async def test_fresh_policy_requires_new_escalation_reason_and_revision(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product)])
    await service.update_policy({"volatility_limit": .01})
    from platform_app.governance import GovernanceError
    with pytest.raises(GovernanceError, match="written"):
        await service.decide(item["id"], {"action": "approve", "expected_revision": 1})
    approved = await service.decide(item["id"], {"action": "approve", "expected_revision": 1,
        "reason": "Reviewed the current low volatility limit."})
    assert approved["band"] == "escalate" and approved["revision"] == 2
    assert service.history(item["id"])[0]["evidence"]["band"] == "auto_approve"


async def test_bulk_rejects_new_margin_proximity_before_recording_approval(tmp_path):
    from platform_app.governance import GovernanceError
    service, commerce, path = setup_governance(tmp_path)
    product = (await commerce.all("/catalog"))["items"][3]
    [item] = await service.register("run", [recommendation(product, factor="1.07")])
    assert item["band"] == "review"
    cost = Decimal(item["proposed_price"]) * (1 - Decimal(str(product["minimum_margin_pct"])) - Decimal("0.01"))
    with connect(path) as db:
        db.execute("UPDATE products SET cost=? WHERE sku=?", (str(cost), product["sku"]))
        db.commit()
    with pytest.raises(GovernanceError, match="Current risk"):
        await service.bulk([item["id"]], {item["id"]: item["revision"]})
    assert service.get(item["id"])["approval"] is None
    assert not any(event["action"] == "recommendation_bulk_approved" for event in service.store.list_audit())
