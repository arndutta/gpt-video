import asyncio
import sqlite3

import pytest

from governance_helpers import recommendation, setup_governance
from platform_app.governance import Governance, GovernanceError
from platform_app.storage import Store


@pytest.mark.parametrize("mode,confidence,expected", [
    ("supervised", .95, "pending_review"), ("supervised", .7, "pending_review"),
    ("assisted", .95, "approved"), ("assisted", .7, "pending_review"),
    ("autonomous", .95, "approved"), ("autonomous", .7, "hold"),
])
async def test_mode_band_matrix_and_dispatch(tmp_path, mode, confidence, expected):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode(mode, hold_seconds=0)
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product, confidence=confidence)])
    assert item["status"] == expected
    assert item["band"] == ("auto_approve" if confidence > .8 else "review")
    results = await service.dispatch_due()
    should_push = expected == "approved" or expected == "hold"
    assert bool(results) == should_push
    assert (await commerce.all("/price-history"))["total"] == int(should_push)
    if should_push:
        pushed = service.get(item["id"])
        assert pushed["status"] == "applied" and pushed["execution"]["prior_price"] == product["current_price"]
        assert pushed["approval"]["kind"] == "automatic"
        await service.dispatch_due()
        assert (await commerce.all("/price-history"))["total"] == 1


@pytest.mark.parametrize("mode", ["supervised", "assisted", "autonomous"])
async def test_escalation_never_auto_and_requires_written_human_override(tmp_path, mode):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode(mode, hold_seconds=0)
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product, variance=1600)])
    assert item["status"] == "escalated" and item["band"] == "escalate"
    assert await service.dispatch_due() == []
    with pytest.raises(GovernanceError, match="written"):
        await service.decide(item["id"], {"action": "approve", "expected_revision": 1})
    approved = await service.decide(item["id"], {"action": "approve", "expected_revision": 1,
                                                "reason": "Reviewed the model uncertainty and available stock."})
    assert approved["approval"]["kind"] == "human"
    assert len(await service.dispatch_due()) == 1


@pytest.mark.parametrize("mode", ["supervised", "assisted", "autonomous"])
async def test_compliance_has_no_approval_or_override_escape(tmp_path, mode):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode(mode)
    product = (await commerce.all("/catalog"))["items"][0]
    bad = recommendation(product)
    bad["proposed_price"] = "0.01"
    [item] = await service.register("run", [bad])
    assert item["status"] == "blocked" and item["band"] == "escalate"
    for action in ({"action": "approve", "reason": "Force"},
                   {"action": "override", "price": product["current_price"], "reason": "Force"}):
        with pytest.raises(GovernanceError):
            await service.decide(item["id"], {**action, "expected_revision": 1})
    assert not await service.dispatch_due()
    assert (await commerce.all("/price-history"))["total"] == 0


async def test_draft_cannot_dispatch_after_failed_grounded_validation(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode("assisted")
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product)], activate=False)
    assert item["status"] == "draft" and not await service.dispatch_due()
    with pytest.raises(GovernanceError):
        await service.decide(item["id"], {"action": "approve", "expected_revision": 1})
    assert (await service.activate("run"))[0]["status"] == "approved"
    assert len(await service.dispatch_due()) == 1


async def test_kill_hold_intervention_mode_change_and_boot_fence(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode("autonomous", hold_seconds=0)
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product, confidence=.7)])
    killed = await service.kill()
    assert killed["mode"] == "supervised" and killed["canceled"] == 1
    assert service.get(item["id"])["status"] == "canceled"
    assert not await service.dispatch_due()
    await service.set_mode("autonomous", hold_seconds=0)
    assert not await service.dispatch_due()  # mode upgrade cannot revive an old intent
    [second] = await service.register("run2", [recommendation(product, confidence=.7)])
    await service.decide(second["id"], {"action": "reject", "expected_revision": 1})
    assert not await service.dispatch_due()
    [third] = await service.register("run3", [recommendation(product)])
    assert third["status"] == "approved"
    restarted = Governance(Store(tmp_path), commerce)
    assert restarted.mode()["mode"] == "supervised"
    assert restarted.get(third["id"])["status"] == "canceled"
    assert not await restarted.dispatch_due()


async def test_override_recomputes_numbers_and_preserves_original_revision(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product)])
    price = product["current_price"]
    updated = await service.decide(item["id"], {"action": "override", "expected_revision": 1,
                                              "price": price, "reason": "Retain the current price after review."})
    assert updated["revision"] == 2 and updated["proposed_price"] == price
    assert updated["numeric_hash_scope"] == "sku_revision" and updated["rationale_origin"] == "human"
    assert "Retain the current price" in updated["rationale"]
    assert updated["forecast"]["revenue"]["mean"] == 100
    assert service.history(item["id"])[0]["evidence"]["proposed_price"] == item["proposed_price"]
    with pytest.raises(GovernanceError, match="revision"):
        await service.decide(item["id"], {"action": "reject", "expected_revision": 1})
    with service.store.connection() as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE recommendations SET evidence='{}'")
    await service.dispatch_due()
    assert service.get(item["id"])["status"] == "unchanged"


async def test_bulk_only_actual_review_not_supervised_auto_queue(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    products = (await commerce.all("/catalog"))["items"]
    [auto] = await service.register("a", [recommendation(products[0])])
    assert auto["status"] == "pending_review" and auto["band"] == "auto_approve"
    with pytest.raises(GovernanceError, match="Review-band"):
        await service.bulk([auto["id"]], {auto["id"]: 1})
    # A larger clean move fails Auto delta eligibility while retaining confidence.
    [review] = await service.register("b", [recommendation(products[3], factor="1.07")])
    assert review["band"] == "review"
    approved = await service.bulk([review["id"]], {review["id"]: 1})
    assert approved[0]["status"] == "approved"
    assert auto["status"] == "pending_review"
    await service.dispatch_due()
    assert (await commerce.all("/price-history"))["total"] == 1


async def test_policy_version_cancels_pending_and_initial_oscillation_retained(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    await service.set_mode("assisted")
    product = (await commerce.all("/catalog"))["items"][0]
    candidate = recommendation(product)
    candidate["initial_stability"] = {"oscillation": True, "damping_applied": True}
    [incident] = await service.register("incident", [candidate])
    assert incident["stability"]["oscillation"] and incident["band"] == "escalate"
    [item] = await service.register("other", [recommendation(product)])
    changed = await service.update_policy({"confidence_threshold": .99})
    assert changed["version"] == 2 and service.get(item["id"])["status"] == "canceled"
    assert not await service.dispatch_due()
    assert any(event["action"] == "governance_policy_changed" for event in service.store.list_audit())
