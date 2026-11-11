import asyncio
from decimal import Decimal

import httpx
import pytest

from commerce.storage import connect
from governance_helpers import recommendation, setup_governance
from platform_app.governance import GovernanceError


class Intercept(httpx.AsyncBaseTransport):
    def __init__(self, wrapped, *, lose_once=False, fail=False, slow=False):
        self.wrapped, self.lose_once, self.fail, self.slow = wrapped, lose_once, fail, slow
        self.posts, self.keys, self.bodies = 0, [], []
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def handle_async_request(self, request):
        if request.method == "POST":
            self.posts += 1
            self.bodies.append(await request.aread())
            self.entered.set()
            if self.slow:
                await self.release.wait()
            if self.fail:
                raise httpx.ReadTimeout("Uncertain connection", request=request)
            result = await self.wrapped.handle_async_request(request)
            if self.lose_once:
                self.lose_once = False
                raise httpx.ReadTimeout("Reply lost after Commerce committed", request=request)
            return result
        if self.fail and request.url.path.startswith("/prices/batches/"):
            raise httpx.ConnectError("Receipt lookup unavailable", request=request)
        return await self.wrapped.handle_async_request(request)


async def approve(service, item):
    return await service.decide(item["id"], {"action": "approve", "expected_revision": item["revision"]})


async def test_ambiguous_commit_reads_original_receipt_and_applies_once(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    intercept = Intercept(commerce.transport, lose_once=True)
    commerce.transport = intercept
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product)])
    await approve(service, item)
    receipts = await service.dispatch_due()
    assert receipts[0]["status"] == "applied" and intercept.posts == 1
    assert service.get(item["id"])["status"] == "applied"
    assert (await commerce.all("/price-history"))["total"] == 1
    await service.dispatch_due()
    assert intercept.posts == 1


async def test_unknown_result_bounded_identical_replay_and_kill_no_resend(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    intercept = Intercept(commerce.transport, fail=True)
    commerce.transport = intercept
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product)])
    await approve(service, item)
    assert not await service.dispatch_due()
    assert intercept.posts == 3 and len(set(intercept.bodies)) == 1
    assert service.get(item["id"])["status"] == "unknown"
    killed = await service.kill()
    assert killed["reconciliation"] and killed["mode"] == "supervised"
    intercept.fail = False
    await service.dispatch_due()
    assert intercept.posts == 3
    assert (await commerce.all("/price-history"))["total"] == 0


async def test_kill_ack_fences_unsent_and_preserves_inflight_receipt(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    intercept = Intercept(commerce.transport, slow=True)
    commerce.transport = intercept
    await service.set_mode("assisted")
    products = (await commerce.all("/catalog"))["items"]
    items = await service.register("run", [recommendation(products[0]), recommendation(products[3])])
    dispatch = asyncio.create_task(service.dispatch_due([items[0]["id"]]))
    await intercept.entered.wait()
    kill = asyncio.create_task(service.kill())
    await asyncio.sleep(.02)
    assert not kill.done()  # acknowledgement waits for the admitted HTTP handoff
    intercept.release.set()
    await dispatch
    killed = await kill
    assert killed["mode"] == "supervised" and killed["canceled"] == 1
    assert service.get(items[0]["id"])["status"] == "applied"
    assert service.get(items[1]["id"])["status"] == "canceled"
    assert intercept.posts == 1
    await service.dispatch_due()
    assert intercept.posts == 1


async def test_cancel_during_dispatch_marks_unknown_and_reconciles_later(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    intercept = Intercept(commerce.transport, slow=True)
    commerce.transport = intercept
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product)])
    await approve(service, item)
    dispatch = asyncio.create_task(service.dispatch_due())
    await intercept.entered.wait()
    dispatch.cancel()
    with pytest.raises(asyncio.CancelledError):
        await dispatch
    assert service.get(item["id"])["status"] == "unknown"
    await service.kill()
    intercept.slow = False
    await service.dispatch_due()
    assert intercept.posts == 1 and (await commerce.all("/price-history"))["total"] == 0


async def test_stale_source_or_new_rules_block_dispatch_even_after_approval(tmp_path):
    service, commerce, path = setup_governance(tmp_path)
    products = (await commerce.all("/catalog"))["items"]
    [stale] = await service.register("stale", [recommendation(products[0])])
    [bad] = await service.register("bad", [recommendation(products[3])])
    await approve(service, stale)
    await approve(service, bad)
    with connect(path) as db:
        db.execute("UPDATE prices SET price_version=price_version+1 WHERE sku=?", (products[0]["sku"],))
        db.execute("UPDATE products SET map_price=? WHERE sku=?", ("999.00", products[3]["sku"]))
        db.commit()
    assert not await service.dispatch_due()
    assert service.get(stale["id"])["status"] == "stale"
    assert service.get(bad["id"])["status"] == "blocked"
    assert (await commerce.all("/price-history"))["total"] == 0


async def test_automatic_dispatch_rebands_new_margin_proximity(tmp_path):
    service, commerce, path = setup_governance(tmp_path)
    await service.set_mode("assisted")
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product)])
    assert item["status"] == "approved"
    # Still compliant, but now close enough to the floor to require Escalate.
    cost = Decimal(item["proposed_price"]) * (1 - Decimal(str(product["minimum_margin_pct"])) - Decimal("0.01"))
    with connect(path) as db:
        db.execute("UPDATE products SET cost=? WHERE sku=?", (str(cost), product["sku"]))
        db.commit()
    assert not await service.dispatch_due()
    assert service.get(item["id"])["status"] == "stale"
    assert (await commerce.all("/price-history"))["total"] == 0


async def test_partial_commerce_outcome_is_persisted_per_item(tmp_path):
    service, commerce, path = setup_governance(tmp_path)
    products = (await commerce.all("/catalog"))["items"]
    items = await service.register("run", [recommendation(products[0]), recommendation(products[3])])
    for item in items:
        await approve(service, item)
    inner = commerce.transport

    class ConcurrentChange(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if request.method == "POST":
                with connect(path) as db:
                    db.execute("UPDATE prices SET price_version=price_version+1 WHERE sku=?", (products[3]["sku"],))
                    db.commit()
            return await inner.handle_async_request(request)

    commerce.transport = ConcurrentChange()
    [receipt] = await service.dispatch_due()
    assert receipt["status"] == "partial"
    assert service.get(items[0]["id"])["status"] == "applied"
    assert service.get(items[1]["id"])["status"] == "execution_rejected"
    assert service.get(items[1]["id"])["execution"]["rejection_code"] == "stale_price"
    assert (await commerce.all("/price-history"))["total"] == 1
    await service.dispatch_due()
    assert (await commerce.all("/price-history"))["total"] == 1


async def test_cooldown_blocks_review_override_and_revert(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    product = (await commerce.all("/catalog"))["items"][0]
    [first] = await service.register("first", [recommendation(product)])
    await approve(service, first)
    await service.dispatch_due()
    await service.update_policy({"minimum_change_seconds": 3600})
    current = (await commerce.all("/catalog"))["items"][0]
    [second] = await service.register("second", [recommendation(current)])
    assert second["stability"]["cooldown_active"]
    with pytest.raises(GovernanceError, match="minimum interval"):
        await approve(service, second)
    with pytest.raises(GovernanceError, match="minimum"):
        await service.revert(first["id"])
    assert (await commerce.all("/price-history"))["total"] == 1


async def test_compensating_revert_is_idempotent_and_current_rules_veto(tmp_path):
    service, commerce, path = setup_governance(tmp_path)
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("run", [recommendation(product)])
    await approve(service, item)
    await service.dispatch_due()
    reverted = await service.revert(item["id"])
    assert reverted["status"] == "applied" and reverted["reverts_item_id"] == item["id"]
    assert reverted["execution"]["new_price"] == product["current_price"]
    assert reverted["execution"]["batch_key"] != service.get(item["id"])["execution"]["batch_key"]
    assert (await service.revert(item["id"]))["id"] == reverted["id"]
    assert (await commerce.all("/price-history"))["total"] == 2
    fresh = (await commerce.all("/catalog"))["items"][3]
    [next_item] = await service.register("next", [recommendation(fresh)])
    await approve(service, next_item)
    await service.dispatch_due()
    with connect(path) as db:
        db.execute("UPDATE products SET map_price=? WHERE sku=?", (next_item["proposed_price"], fresh["sku"]))
        db.commit()
    with pytest.raises(GovernanceError, match="current rule"):
        await service.revert(next_item["id"])
    assert (await commerce.all("/price-history"))["total"] == 3
