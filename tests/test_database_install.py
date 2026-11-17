"""Installations preserve live state; exported SQL faithfully replays saved data."""

from datetime import date
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys

from fastapi.testclient import TestClient
import httpx
import pytest

from commerce.app import create_app as create_commerce
from platform_app.app import create_app
from platform_app.config import Settings
from scripts import database
from scripts.database import DATABASES, export_sql, inspect_database, install, sql_value


def test_command_line_installs_and_reports_once_and_status_is_read_only(tmp_path):
    command = [sys.executable, "-m", "scripts.database", "--data-dir", str(tmp_path)]
    result = subprocess.run([*command, "--sku-count", "3", "--days", "1"],
                            check=True, capture_output=True, text=True)
    report = json.loads(result.stdout)
    assert report["seeded_new_catalog"]
    result = subprocess.run([*command, "status"], check=True, capture_output=True, text=True)
    status = json.loads(result.stdout)
    assert status["databases"] == report["databases"]


def test_install_seeds_complete_data_and_api_reads_committed_sql_updates(tmp_path):
    result = install(tmp_path, sku_count=3, days=30, as_of=date(2026, 11, 16))
    assert result["seeded_new_catalog"]
    databases = result["databases"]
    assert databases["commerce.db"]["tables"]["sales"] == 90
    assert databases["commerce.db"]["tables"]["evaluation_truth"] == 3
    assert databases["market.db"]["tables"]["competitor_quotes"] == 6
    assert databases["app.db"]["tables"]["model_pricing"] == 8
    assert not list(tmp_path.glob("*.json"))
    commerce = create_commerce(tmp_path / "commerce.db")
    platform = create_app(Settings(data_dir=tmp_path, commerce_url="http://commerce"),
                          commerce_transport=httpx.ASGITransport(app=commerce))
    with TestClient(commerce), TestClient(platform) as client:
        with sqlite3.connect(tmp_path / "commerce.db") as db:
            db.execute("UPDATE products SET name='Database product' WHERE sku='SKU-00001'")
            db.execute("UPDATE prices SET current_price='18.75' WHERE sku='SKU-00001'")
        response = client.get("/api/catalog", params={"sku": "SKU-00001"})
        assert response.status_code == 200
        item = next(row for row in response.json()["items"] if row["sku"] == "SKU-00001")
        assert item["name"] == "Database product" and item["current_price"] == "18.75"


def test_reinstall_preserves_existing_catalog_policy_and_in_progress_work(tmp_path):
    install(tmp_path, sku_count=3, days=2)
    with sqlite3.connect(tmp_path / "commerce.db") as db:
        db.execute("UPDATE prices SET current_price='16.25',price_version=4 WHERE sku='SKU-00001'")
    with sqlite3.connect(tmp_path / "app.db") as db:
        db.execute("INSERT INTO runs(id,status,stage,created_at,request) "
                   "VALUES('existing','running','analysis','2026-11-16T00:00:00+00:00','{}')")
        db.execute("UPDATE governance_control SET mode='assisted',generation=17")
        db.execute("UPDATE model_pricing SET input_cost_per_token=0.25 WHERE model='gpt-4o-mini'")
    result = install(tmp_path, sku_count=9, days=90, seed=999)
    assert not result["seeded_new_catalog"]
    assert result["databases"]["commerce.db"]["tables"]["sales"] == 6
    with sqlite3.connect(tmp_path / "commerce.db") as db:
        assert db.execute("SELECT current_price,price_version FROM prices WHERE sku='SKU-00001'").fetchone() == ("16.25", 4)
    with sqlite3.connect(tmp_path / "app.db") as db:
        assert db.execute("SELECT status FROM runs WHERE id='existing'").fetchone()[0] == "running"
        assert db.execute("SELECT mode,generation FROM governance_control").fetchone() == ("assisted", 17)
        assert db.execute("SELECT input_cost_per_token FROM model_pricing WHERE model='gpt-4o-mini'").fetchone()[0] == .25


def test_sql_export_replays_all_tables_rows_and_immutable_audit_rules(tmp_path):
    data_dir = tmp_path / "data"
    result = install(data_dir, sku_count=3, days=2)
    with sqlite3.connect(data_dir / "app.db") as db:
        db.execute("INSERT INTO audit(timestamp,actor,action,detail) VALUES('now','human','saved','{}')")
        db.execute('CREATE TABLE "export probe"(id INTEGER PRIMARY KEY AUTOINCREMENT,value REAL,note TEXT,payload BLOB)')
        db.execute('INSERT INTO "export probe" VALUES(1,?,?,?)', (1.2345678901234567, "A\0B's data", b"\x00\xff"))
        db.execute('INSERT INTO "export probe"(id) VALUES(50)')
        db.execute('DELETE FROM "export probe" WHERE id=50')
    exports = export_sql(data_dir, tmp_path / "sql")
    assert len(exports) == len(DATABASES)
    restored_dir = tmp_path / "restored"
    restored_dir.mkdir()
    for filename in exports:
        source = Path(filename)
        target = restored_dir / (source.stem + ".db")
        with sqlite3.connect(target) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(source.read_text())
        original = inspect_database(data_dir / target.name)
        assert inspect_database(target)["tables"] == original["tables"]
    with sqlite3.connect(restored_dir / "app.db") as db:
        assert json.loads(db.execute("SELECT detail FROM audit").fetchone()[0]) == {}
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM audit")
        assert db.execute('SELECT value,note,payload FROM "export probe"').fetchone() == (
            1.2345678901234567, "A\0B's data", b"\x00\xff")
        db.execute('INSERT INTO "export probe"(note) VALUES(\'next\')')
        assert db.execute('SELECT id FROM "export probe" WHERE note=\'next\'').fetchone()[0] == 51
    with sqlite3.connect(data_dir / "commerce.db") as original, sqlite3.connect(restored_dir / "commerce.db") as restored:
        assert original.execute("SELECT * FROM evaluation_truth ORDER BY sku").fetchall() == restored.execute(
            "SELECT * FROM evaluation_truth ORDER BY sku").fetchall()
    assert result["databases"]["app.db"]["integrity"] == "ok"


def test_schema_only_can_be_populated_later_without_replacing_reference_rates(tmp_path):
    result = install(tmp_path, schema_only=True)
    assert not result["seeded_new_catalog"]
    assert result["databases"]["commerce.db"]["tables"]["products"] == 0
    assert result["databases"]["app.db"]["tables"]["model_pricing"] == 8
    result = install(tmp_path, sku_count=3, days=1)
    assert result["seeded_new_catalog"]


def test_legacy_usage_schema_is_upgraded_without_losing_cost_history(tmp_path):
    with sqlite3.connect(tmp_path / "app.db") as db:
        db.execute("CREATE TABLE llm_usage(id INTEGER PRIMARY KEY,timestamp REAL,run_id TEXT,agent TEXT,"
                   "model TEXT,status TEXT,tokens_in INTEGER,tokens_out INTEGER,cost_usd REAL,latency_ms REAL)")
        db.execute("INSERT INTO llm_usage VALUES(1,1,'old','analyst','model','completed',10,5,.2,3)")
    install(tmp_path, schema_only=True)
    with sqlite3.connect(tmp_path / "app.db") as db:
        assert db.execute("SELECT cost_usd,pricing_source,pricing_model FROM llm_usage").fetchone() == (
            .2, "legacy_configured_fallback_rates", None)


def test_exported_float_expressions_preserve_extreme_and_adjacent_values():
    values = [0., 5e-324, 1.7976931348623157e308, -1.600934491842885, 59.017395959346956,
              math.nextafter(1., 0.), math.nextafter(1., 2.), 1e-100, -1e100]
    with sqlite3.connect(":memory:") as db:
        for value in values:
            assert db.execute("SELECT " + sql_value(value)).fetchone()[0] == value


def test_failed_export_preserves_previous_sql_file_and_removes_partial_output(tmp_path, monkeypatch):
    install(tmp_path / "data", sku_count=3, days=1)
    exports = export_sql(tmp_path / "data", tmp_path / "sql")
    original = Path(exports[0]).read_bytes()

    def interrupted(_db, stream):
        stream.write("partial output")
        raise OSError("Export storage failed")

    monkeypatch.setattr(database, "write_dump", interrupted)
    with pytest.raises(OSError, match="Export storage failed"):
        export_sql(tmp_path / "data", tmp_path / "sql")
    assert Path(exports[0]).read_bytes() == original
    assert len(list((tmp_path / "sql").iterdir())) == len(DATABASES)
