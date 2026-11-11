"""Workflow filters are applied before pagination, including old authorized work."""

from governance_helpers import recommendation, setup_governance


async def test_run_filter_and_status_filter_find_old_items_before_applying_limit(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    products = (await commerce.all("/catalog"))["items"]
    [old] = await service.register("old-run", [recommendation(products[0])])
    await service.decide(old["id"], {"action": "approve", "expected_revision": old["revision"]})
    newer = await service.register("new-run", [recommendation(products[3]), recommendation(products[6])], activate=False)
    assert service.queue(limit=1)[0]["id"] == newer[-1]["id"]
    assert service.queue(run_id="old-run", limit=1)[0]["id"] == old["id"]
    assert service.queue(status="approved", limit=1)[0]["id"] == old["id"]
    assert len(service.queue(run_id="new-run", status="draft", limit=2)) == 2
    assert service.queue(run_id="old-run", status="draft", limit=1) == []


async def test_band_and_automatic_filters_include_old_records_and_null_approval(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    products = (await commerce.all("/catalog"))["items"]
    await service.set_mode("assisted")
    [automatic] = await service.register("auto-run", [recommendation(products[0])])
    [review] = await service.register("review-run", [recommendation(products[3], confidence=.7)])
    await service.register("draft-run", [recommendation(products[6])], activate=False)
    assert service.queue(automatic=True, limit=1)[0]["id"] == automatic["id"]
    assert service.queue(band="review", automatic=False, limit=1)[0]["id"] == review["id"]
    assert len(service.queue(automatic=False, limit=2)) == 2
    assert service.queue(band="review", automatic=True, limit=1) == []


async def test_dispatch_selects_old_hold_and_approved_work_despite_small_queue_page(tmp_path, monkeypatch):
    service, commerce, _ = setup_governance(tmp_path)
    products = (await commerce.all("/catalog"))["items"]
    await service.set_mode("autonomous", hold_seconds=0)
    [held] = await service.register("hold-run", [recommendation(products[0], confidence=.7)])
    [approved] = await service.register("auto-run", [recommendation(products[3])])
    await service.register("draft-run", [recommendation(products[6])], activate=False)
    original = service.repo.queue

    def one_row(*args, **kwargs):
        return original(*args, **{**kwargs, "limit": 1})

    monkeypatch.setattr(service.repo, "queue", one_row)
    # The hold scan must use its own predicate; a new draft is never a reason to
    # hide an expired hold. One approved page is processed per invocation.
    await service.dispatch_due()
    await service.dispatch_due()
    assert service.get(held["id"])["status"] == "applied"
    assert service.get(approved["id"])["status"] == "applied"
    assert (await commerce.all("/price-history"))["total"] == 2
