"""Isolated W4/W6 demonstrations with explicit model and observation-clock fixtures."""

from datetime import datetime, timedelta, timezone

from commerce.storage import connect
from governance_helpers import recommendation, setup_governance
from platform_app.config import RunRequest
from platform_app.feedback import Feedback
from test_grounding_api import complete, upload
from test_workflow_integration import settled, workbench


def test_runtime_upload_version_is_consumed_by_subsequent_grounded_graph_without_restart(tmp_path):
    with workbench(tmp_path) as (client, _, provider):
        first_upload = complete(client, upload(client))
        assert first_upload["status"] == "ready"
        request = {"kind": "grounded", "iterations": 100, "sku_ids": ["SKU-00001"]}
        first = client.post("/api/runs", json=request)
        assert first.status_code == 202, first.text
        first_run = settled(client, first.json()["id"])
        assert first_run["status"] == "awaiting_review"
        [old_item] = first_run["result"]["recommendations"]
        old_citations = old_item["citations"]
        before = len(provider.calls)
        changed = complete(client, upload(client, text="Updated margin policy requires explicit review of uncertainty and every price change.",
                                          version="v2"))
        assert changed["status"] == "ready" and changed["result"]["corpus_version"] > first_upload["result"]["corpus_version"]
        second = client.post("/api/runs", json=request)
        assert second.status_code == 202, second.text
        second_run = settled(client, second.json()["id"])
        assert second_run["status"] == "awaiting_review"
        [new_item] = second_run["result"]["recommendations"]
        assert new_item["citations"] != old_citations and len(provider.calls) > before
        assert all(chunk["citation_id"] not in old_citations for _, payload in provider.calls[before:]
                   for chunk in payload["evidence"])
        for citation in new_item["citations"]:
            assert client.get(f"/api/grounding/citations/{citation}").json()["version"] == "v2"
        for citation in old_citations:
            assert client.get(f"/api/grounding/citations/{citation}").json()["version"] == "v1"


async def test_real_commerce_http_aggregate_readback_updates_three_disjoint_learning_versions(tmp_path, monkeypatch):
    service, commerce, path = setup_governance(tmp_path)
    feedback = Feedback(service.store, commerce)
    today = datetime.now(timezone.utc).date()
    anchor = today - timedelta(days=200)
    source_ids = []
    for index in range(3):
        applied_day = anchor + timedelta(days=12 * index)
        timestamp = applied_day.isoformat() + "T12:00:00+00:00"
        # Only the isolated Commerce fixture clock is advanced; live data is untouched.
        monkeypatch.setattr("commerce.batches.utc_now", lambda value=timestamp: value)
        product = (await commerce.all("/catalog"))["items"][0]
        run = service.store.create_run(RunRequest(kind="grounded", horizon_days=10).model_dump())
        service.store.update_run(run["id"], "running", "execution")
        candidate = recommendation(product, factor="1.03")
        candidate["forecast"]["units"] = {"mean": 100., "lower": 80., "upper": 120.}
        [item] = await service.register(run["id"], [candidate])
        await service.decide(item["id"], {"action": "approve", "expected_revision": item["revision"]})
        await service.dispatch_due([item["id"]])
        assert service.get(item["id"])["status"] == "applied"
        source_ids.append(item["id"])
        # Arrange aggregated observations inside Commerce-owned fixture storage.
        # Feedback must obtain them through the real HTTP adapter and wire contract.
        with connect(path) as db:
            db.executemany("INSERT INTO sales(sku,date,price,units,promotion,seasonal_index) VALUES(?,?,?,?,?,?)",
                           [(item["sku"], (applied_day + timedelta(days=day)).isoformat(),
                             item["proposed_price"], 11, 0, 1.) for day in range(1, 11)])
            db.commit()
        result = await feedback.refresh(service.queue(), today=today)
        assert len([row for row in result["items"] if row["status"] == "observed"]) == index + 1
    state = result["learning"][product["sku"]]
    assert state["observations"] == 3 and state["observed_days"] == 30 and state["calibration_ready"]
    assert state["last_adjustment"] == .1 and state["elasticity_offset"] == .1
    assert state["uncertainty_multiplier"] < 1 and state["version"] == "learned-3"
    assert await feedback.refresh(service.queue(), today=today) == result
    assert {row["item_id"] for row in result["items"]} == set(source_ids)
    assert all(row["result"]["source"] == "Commerce /sales over HTTP" for row in result["items"])
    with service.store.connection() as db:
        assert db.execute("SELECT count(*) FROM learning_versions").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM observed_days").fetchone()[0] == 30
