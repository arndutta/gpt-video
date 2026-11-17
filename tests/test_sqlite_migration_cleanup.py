"""Legacy cleanup verifies persisted data; RAG installation preserves evidence."""

from datetime import date
import json
from pathlib import Path
import sqlite3
import struct

import pytest

from commerce.evaluation import read_evaluation_truth
from commerce.legacy import cleanup_legacy_json
from commerce.seed import seed_database
from platform_app.commerce_client import read_competitors


def legacy_copies(directory):
    seed_database(directory / "commerce.db", sku_count=3, days=2, as_of=date(2026, 11, 17))
    quotes = read_competitors(directory)
    truth = read_evaluation_truth(directory / "commerce.db")
    (directory / "competitor_feed.json").write_text(json.dumps({"items": quotes}))
    (directory / "evaluation_truth.json").write_text(json.dumps(truth))
    return quotes, truth


def test_cleanup_imports_missing_market_database_and_removes_only_verified_sidecars(tmp_path):
    quotes, _truth = legacy_copies(tmp_path)
    for path in tmp_path.glob("market.db*"):
        path.unlink()
    report = tmp_path / "benchmark_result.json"
    report.write_text('{"measurements":42}')
    model = tmp_path / "models" / "tokenizer.json"
    model.parent.mkdir()
    model.write_text('{"model":"metadata"}')
    assert cleanup_legacy_json(tmp_path) == ["competitor_feed.json", "evaluation_truth.json"]
    assert read_competitors(tmp_path) == quotes
    assert report.read_text() == '{"measurements":42}'
    assert model.read_text() == '{"model":"metadata"}'
    assert cleanup_legacy_json(tmp_path) == []


@pytest.mark.parametrize("changed", ["competitor_feed.json", "evaluation_truth.json"])
def test_cleanup_retains_both_files_when_either_differs_from_sqlite(tmp_path, changed):
    quotes, truth = legacy_copies(tmp_path)
    if changed == "competitor_feed.json":
        quotes[0]["price"] = "999.00"
        (tmp_path / changed).write_text(json.dumps(quotes))
    else:
        truth["SKU-00001"]["elasticity"] = -99
        (tmp_path / changed).write_text(json.dumps(truth))
    before = {name: (tmp_path / name).read_bytes()
              for name in ("competitor_feed.json", "evaluation_truth.json")}
    with pytest.raises(ValueError, match="differs"):
        cleanup_legacy_json(tmp_path)
    assert {name: (tmp_path / name).read_bytes() for name in before} == before


def test_cleanup_retains_files_when_legacy_content_is_malformed(tmp_path):
    legacy_copies(tmp_path)
    (tmp_path / "evaluation_truth.json").write_text("invalid JSON")
    with pytest.raises(ValueError):
        cleanup_legacy_json(tmp_path)
    assert (tmp_path / "competitor_feed.json").exists()
    assert (tmp_path / "evaluation_truth.json").read_text() == "invalid JSON"


def test_installer_does_not_claim_embedding_identity_and_exports_saved_rag_data(tmp_path):
    from scripts.database import export_sql, inspect_database, install

    directory = tmp_path / "data"
    result = install(directory, schema_only=True)
    assert result["databases"]["rag.db"]["tables"]["embedding_identity"] == 0
    assert result["databases"]["rag.db"]["tables"]["rag_chunks"] == 0
    vector = struct.pack("<dd", .25, .75)
    identity = json.dumps({"model_id": "existing-model", "dimensions": 2})
    with sqlite3.connect(directory / "rag.db") as db:
        db.execute("INSERT INTO embedding_identity VALUES(1,?)", (identity,))
        db.execute("INSERT INTO rag_collections(name,dimensions) VALUES('pricing_policy',2)")
        db.execute("INSERT INTO rag_chunks(collection,id,document_key,source_id,version,title,content_hash,"
                   "chunk_index,start_char,end_char,source_uri,document,embedding) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   ("pricing_policy", "citation-1", "key", "policy", "v1", "Title", "hash", 0, 0, 4,
                    "policy.md", "Text", vector))
    result = install(directory, schema_only=True)
    assert result["databases"]["rag.db"]["tables"]["rag_chunks"] == 1
    rag_sql = next(Path(path) for path in export_sql(directory, tmp_path / "sql") if Path(path).stem == "rag")
    restored = tmp_path / "restored.db"
    with sqlite3.connect(restored) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(rag_sql.read_text())
        assert db.execute("SELECT identity FROM embedding_identity").fetchone()[0] == identity
        assert db.execute("SELECT document,embedding FROM rag_chunks").fetchone() == ("Text", vector)
    assert inspect_database(restored)["tables"] == result["databases"]["rag.db"]["tables"]
