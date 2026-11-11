"""Scoped historical audit chains remain reachable beyond the newest event window."""

from platform_app.dashboard import audit_items
from platform_app.storage import Store, now
from governance_helpers import setup_governance, recommendation


def newer_events(store):
    with store.connection() as db:
        db.executemany("INSERT INTO audit(timestamp,actor,action,run_id,detail) VALUES(?,?,?,?,?)",
                       [(now(), "human", "newer", "new-run", "{}") for _ in range(10005)])


def test_run_and_system_filters_precede_the_event_limit(tmp_path):
    store = Store(tmp_path)
    store.audit("old-human", {}, run_id="old-run")
    store.audit("old-system", {}, actor="system", run_id="old-run")
    newer_events(store)
    assert [i["action"] for i in audit_items(store, run_id="old-run", limit=2)] == ["old-system", "old-human"]
    assert [i["action"] for i in audit_items(store, automatic=True, limit=1)] == ["old-system"]


async def test_sku_chain_includes_human_decision_and_http_attempt_without_explicit_sku(tmp_path):
    service, commerce, _ = setup_governance(tmp_path)
    product = (await commerce.all("/catalog"))["items"][0]
    [item] = await service.register("old-run", [recommendation(product)])
    await service.decide(item["id"], {"action": "approve", "expected_revision": item["revision"]})
    await service.dispatch_due([item["id"]])
    newer_events(service.store)
    chain = audit_items(service.store, sku=item["sku"], limit=100)
    actions = {i["action"] for i in chain}
    assert {"recommendation_approve", "price_dispatch", "price_http_attempt", "price_receipt"} <= actions
    assert "newer" not in actions
