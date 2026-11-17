from datetime import date
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from commerce.app import create_app
from commerce.seed import generate, money, seed_database
from commerce.storage import connect
from commerce.market import initialize_market, replace_quotes
from platform_app.commerce_client import read_competitors


@pytest.fixture
def commerce(tmp_path):
    path = tmp_path / "commerce.db"
    seed_database(path, sku_count=9, days=30, data_dir=tmp_path)
    with TestClient(create_app(path)) as client:
        yield client, path


def push(client, key, items):
    return client.post("/prices/batches", json={
        "batch_key": key, "actor": "local-operator", "approval_kind": "human", "items": items,
    })


def change(product, multiplier="1.05"):
    return {"sku": product["sku"], "price": money(Decimal(product["current_price"]) * Decimal(multiplier)),
            "expected_version": product["price_version"]}


def test_reads_are_filtered_paginated_and_do_not_expose_truth(commerce):
    client, _ = commerce
    health = client.get("/health").json()
    assert health["seeded"] and health["catalog_count"] == 9
    first = client.get("/catalog", params={"limit": 2}).json()
    assert first["total"] == 9 and len(first["items"]) == 2
    assert client.get("/catalog", params={"offset": 2, "limit": 2}).json()["items"] != first["items"]
    sku = first["items"][0]["sku"]
    for endpoint in ("catalog", "sales", "inventory", "prices", "price-history"):
        response = client.get(f"/{endpoint}", params={"sku": sku, "limit": 100000 if endpoint == "sales" else 5000})
        assert response.status_code == 200
        assert "elasticity" not in response.text and "baseline_demand" not in response.text
        assert all(item["sku"] == sku for item in response.json()["items"])
    assert client.get("/sales", params={"sku": sku, "days": 7}).json()["total"] == 7
    assert client.get("/sales", params={"sku": sku, "since": "2026-11-07"}).json()["total"] == 2
    assert client.get("/catalog", params={"category": "Beverages"}).json()["total"] == 3
    assert client.get("/catalog", params={"limit": 0}).status_code == 422


def test_batch_replay_is_noop_and_conflicting_payload_is_rejected(commerce):
    client, _ = commerce
    product = client.get("/catalog").json()["items"][0]
    item = change(product)
    first = push(client, "batch-replay", [item])
    assert first.status_code == 200 and first.json()["status"] == "applied"
    result = first.json()["items"][0]
    assert result["new_version"] == 2
    replay = push(client, "batch-replay", [item])
    assert replay.json() == first.json()
    assert client.get("/prices/batches/batch-replay").json() == first.json()
    assert client.get("/price-history").json()["total"] == 1
    assert push(client, "batch-replay", [change(product, "1.06")]).status_code == 409
    assert client.get("/prices/batches/unknown").status_code == 404


def test_partial_success_stale_version_and_no_change(commerce):
    client, _ = commerce
    products = client.get("/catalog").json()["items"]
    valid, invalid = change(products[0]), change(products[3])
    invalid["expected_version"] = 10
    response = push(client, "batch-partial", [valid, invalid]).json()
    assert response["status"] == "partial"
    assert [row["status"] for row in response["items"]] == ["applied", "rejected"]
    assert response["items"][1]["rejection_code"] == "stale_price"
    unchanged = change(products[3], "1")
    assert push(client, "batch-unchanged", [unchanged]).json()["items"][0]["new_version"] == 1
    assert client.get("/price-history").json()["total"] == 1
    bad = {"sku": "does-not-exist", "price": "12.00", "expected_version": 1}
    assert push(client, "batch-missing", [bad]).json()["items"][0]["rejection_code"] == "unknown_sku"


def test_concurrent_replays_apply_once_and_receipt_survives_restart(commerce):
    client, path = commerce
    product = client.get("/catalog").json()["items"][0]
    item = change(product)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: push(client, "batch-race", [item]).json(), range(2)))
    assert results[0] == results[1]
    assert client.get("/price-history").json()["total"] == 1
    with TestClient(create_app(path)) as restarted:
        assert restarted.get("/prices/batches/batch-race").json() == results[0]
        actual = restarted.get("/prices", params={"sku": product["sku"]}).json()["items"][0]
        assert actual["price_version"] == 2


@pytest.mark.parametrize("rule", ["map_floor", "margin_floor", "max_change", "category_bounds", "rounding_policy"])
def test_each_independent_compliance_rule_vetoes(commerce, rule):
    client, path = commerce
    product = client.get("/catalog").json()["items"][0]
    item = change(product)
    current = Decimal(product["current_price"])
    with connect(path) as connection:
        if rule == "map_floor":
            item["price"] = money(current * Decimal("0.5"))
        elif rule == "margin_floor":
            connection.execute("UPDATE products SET cost = ? WHERE sku = ?", (money(current), product["sku"]))
        elif rule == "max_change":
            item["price"] = money(current * Decimal("1.3"))
        elif rule == "category_bounds":
            connection.execute("UPDATE products SET max_price = ? WHERE sku = ?", (money(current), product["sku"]))
        else:
            connection.execute("UPDATE products SET rounding_increment = '0.05' WHERE sku = ?", (product["sku"],))
            cents = (current * 100).to_integral_value() + 1
            while cents % 5 == 0:
                cents += 1
            item["price"] = money(cents / 100)
        connection.commit()
    response = push(client, f"batch-{rule}", [item]).json()
    assert response["status"] == "rejected"
    assert response["items"][0]["rejection_code"] == rule
    assert client.get("/price-history").json()["total"] == 0


def test_coupled_family_rejection_preserves_valid_partial_result(commerce):
    client, path = commerce
    products = client.get("/catalog").json()["items"]
    small, medium, other = products[0], products[1], products[3]
    with connect(path) as connection:
        connection.execute("UPDATE products SET max_change_pct = 0.9, max_price = '999.00' WHERE family_id = ?",
                           (small["family_id"],))
        connection.commit()
    invalid = change(small)
    invalid["price"] = money(Decimal(medium["current_price"]) + Decimal("0.01"))
    medium_change = change(medium, "1")
    response = push(client, "batch-family", [invalid, medium_change, change(other)]).json()
    assert response["status"] == "partial"
    assert [row["rejection_code"] for row in response["items"][:2]] == ["price_ladder", "price_ladder"]
    assert response["items"][2]["status"] == "applied"
    actual = client.get("/prices", params={"sku": small["sku"]}).json()["items"][0]
    assert actual["current_price"] == small["current_price"] and actual["price_version"] == 1


def test_invalid_write_contracts_do_not_mutate(commerce):
    client, _ = commerce
    product = client.get("/catalog").json()["items"][0]
    item = change(product)
    assert push(client, "batch-duplicates", [item, item]).status_code == 422
    for bad in ("NaN", "Infinity", "-1.00", "0.00", "1.001", 12.50):
        assert push(client, "batch-invalid", [{**item, "price": bad}]).status_code == 422
    assert client.get("/price-history").json()["total"] == 0


def test_seed_reproducibility_ground_truth_and_explicit_reset(tmp_path):
    one = generate(6, 30, 42, date(2026, 11, 8))
    assert one == generate(6, 30, 42, date(2026, 11, 8))
    assert one != generate(6, 30, 43, date(2026, 11, 8))
    path = tmp_path / "commerce.db"
    seed_database(path, sku_count=6, days=30, data_dir=tmp_path)
    feed = read_competitors(tmp_path)
    assert len(feed) == 12 and set(feed[0]) == {"sku", "competitor", "price", "observed_at"}
    with connect(path) as connection:
        truth = connection.execute("SELECT elasticity FROM evaluation_truth").fetchall()
    assert len(truth) == 6 and all(row["elasticity"] < 0 for row in truth)
    assert not (tmp_path / "competitor_feed.json").exists()
    assert not (tmp_path / "evaluation_truth.json").exists()
    with pytest.raises(ValueError, match="already contains"):
        seed_database(path, sku_count=6, days=30, data_dir=tmp_path)
    seed_database(path, sku_count=6, days=30, data_dir=tmp_path, reset=True)
    with connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 180
    assert read_competitors(tmp_path) == feed


def test_empty_database_is_initialized_without_silent_seeding(tmp_path):
    with TestClient(create_app(tmp_path / "empty.db")) as client:
        assert client.get("/health").json()["seeded"] is False
        assert client.get("/catalog").json()["items"] == []


@pytest.mark.parametrize("envelope", [False, True])
def test_legacy_market_migration_is_once_only_and_preserves_database_edits(tmp_path, envelope):
    quote = {"sku": "SKU-1", "competitor": "Market", "price": "10.00", "observed_at": "2026-11-08"}
    legacy = tmp_path / "competitor_feed.json"
    legacy.write_text(json.dumps({"items": [quote]} if envelope else [quote]))
    path = initialize_market(tmp_path)
    assert read_competitors(tmp_path) == [quote]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE competitor_quotes SET price='11.00'")
    legacy.write_text("this obsolete input must not be read again")
    initialize_market(tmp_path)
    assert read_competitors(tmp_path) == [{**quote, "price": "11.00"}]
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM competitor_quotes")
    initialize_market(tmp_path)
    assert read_competitors(tmp_path) == []


def test_market_replacement_rolls_back_and_reader_never_uses_static_json(tmp_path):
    assert read_competitors(tmp_path) == []
    quote = {"sku": "SKU-1", "competitor": "Market", "price": "10.00", "observed_at": "2026-11-08"}
    replace_quotes(tmp_path, [quote])
    (tmp_path / "competitor_feed.json").write_text(json.dumps([{**quote, "price": "99.00"}]))
    assert read_competitors(tmp_path) == [quote]
    initialize_market(tmp_path)
    assert read_competitors(tmp_path) == [quote]
    with pytest.raises(sqlite3.IntegrityError):
        replace_quotes(tmp_path, [{**quote, "price": "12.00"}, quote])
    assert read_competitors(tmp_path) == [quote]
