"""Pricing estimates read installed SQLite rates and preserve local changes."""

import sqlite3
from types import SimpleNamespace

import pytest

from platform_app.config import Settings
from platform_app.llm import pricing


def test_pricing_database_changes_affect_next_estimate_and_survive_reinitialization(tmp_path):
    settings = Settings(data_dir=tmp_path, pricing_model_analyst="gpt-4o-mini")
    pricing.initialize_pricing(tmp_path)
    assert len(pricing.catalog(tmp_path)["models"]) == 8
    with sqlite3.connect(tmp_path / "app.db") as db:
        db.execute("UPDATE model_pricing SET input_cost_per_token=0.000002,"
                   "output_cost_per_token=0.000003,cache_read_input_token_cost=0.000001 "
                   "WHERE model='gpt-4o-mini'")
        db.execute("DELETE FROM model_pricing WHERE model='gpt-4.1-mini'")
        db.execute("UPDATE model_pricing_provenance SET value='local-update' WHERE key='description'")
    raw = SimpleNamespace(usage_metadata={"input_token_details": {"cache_read": 200}})
    updated = pricing.estimate_cost(settings, "analyst", "alias", raw, 1000, 500)
    assert updated["cost_usd"] == pytest.approx(.0033)
    pricing.initialize_pricing(tmp_path)
    snapshot = pricing.catalog(tmp_path)
    assert snapshot["models"]["gpt-4o-mini"]["input_cost_per_token"] == .000002
    assert "gpt-4.1-mini" not in snapshot["models"]
    assert snapshot["provenance"]["description"] == "local-update"


def test_settings_select_their_own_database_and_unknown_models_use_fallback(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    pricing.initialize_pricing(first)
    pricing.initialize_pricing(second)
    with sqlite3.connect(first / "app.db") as db:
        db.execute("DELETE FROM model_pricing WHERE model='gpt-4o-mini'")
    missing = pricing.estimate_cost(Settings(data_dir=first), "analyst", "gpt-4o-mini", None, 1000, 1000)
    present = pricing.estimate_cost(Settings(data_dir=second), "analyst", "gpt-4o-mini", None, 1000, 1000)
    assert missing["pricing_source"] == "configured_fallback_rates"
    assert present["pricing_source"] == "litellm_snapshot"
    assert present["cost_usd"] == pytest.approx(.00075)


def test_seed_failure_rolls_back_schema_and_rates(tmp_path, monkeypatch):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "model_pricing_ddl.sql").write_text(
        (pricing.SQL_DIR / "model_pricing_ddl.sql").read_text())
    (sql_dir / "model_pricing_dml.sql").write_text(
        "INSERT INTO model_pricing(model,input_cost_per_token,output_cost_per_token) "
        "VALUES('partial',1,1);\nINSERT INTO missing_table VALUES(1);\n")
    monkeypatch.setattr(pricing, "SQL_DIR", sql_dir)
    directory = tmp_path / "data"
    with pytest.raises(sqlite3.OperationalError, match="missing_table"):
        pricing.initialize_pricing(directory)
    with sqlite3.connect(directory / "app.db") as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0
