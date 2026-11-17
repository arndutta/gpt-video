"""SQLite-backed attributed text-token rates with explicit unknown-model fallback."""

from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def initialize_pricing(data_dir: Path) -> None:
    """Install the DDL and initial rates once; preserve subsequent SQL edits/deletions."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(data_dir / "app.db", timeout=10)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        # executescript commits its own transaction, so include transaction control
        # in the scripts rather than splitting the bootstrap across two commits.
        ddl = (SQL_DIR / "model_pricing_ddl.sql").read_text(encoding="utf-8")
        dml = (SQL_DIR / "model_pricing_dml.sql").read_text(encoding="utf-8")
        try:
            db.executescript("BEGIN IMMEDIATE;\n" + ddl)
            if not db.execute("SELECT 1 FROM model_pricing_schema WHERE version=1").fetchone():
                # execute complete statements without executescript's implicit commit.
                statement = ""
                for line in dml.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        db.execute(statement)
                        statement = ""
                db.execute("INSERT INTO model_pricing_schema(version,applied_at) VALUES(1,?)",
                           (datetime.now(timezone.utc).isoformat(),))
            db.commit()
        except BaseException:
            db.rollback()
            raise


def catalog(data_dir: Path | None = None):
    """Read fresh rates so a committed database change affects the next estimate."""
    directory = Path(data_dir) if data_dir is not None else Path(os.environ.get("DATA_DIR", "data"))
    path = directory / "app.db"
    if not path.exists():
        initialize_pricing(directory)
    with closing(sqlite3.connect(path, timeout=.2)) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='model_pricing'").fetchone():
            initialize_pricing(directory)
        rows = db.execute("SELECT * FROM model_pricing ORDER BY model").fetchall()
        return {"provenance": dict(db.execute("SELECT key,value FROM model_pricing_provenance")),
                "models": {row["model"]: {key: value for key, value in dict(row).items()
                                           if key != "model" and value is not None} for row in rows}}


def estimate_cost(settings, role, alias, raw, tokens_in, tokens_out, *, data_dir=None):
    try:
        snapshot = catalog(data_dir if data_dir is not None else settings.data_dir)
    except (OSError, ValueError, sqlite3.Error):
        snapshot = {"models": {}}
    configured = getattr(settings, "pricing_model_" + role, None)
    metadata = getattr(raw, "response_metadata", None) or {}
    candidates = [configured] if configured else [metadata.get("model_name"), metadata.get("model"), alias]
    name = next((name for name in candidates if isinstance(name, str) and name in snapshot["models"]), None)
    if name is None:
        return {"cost_usd": (tokens_in * settings.llm_input_cost_per_million
                             + tokens_out * settings.llm_output_cost_per_million) / 1_000_000,
                "pricing_source": "configured_fallback_rates", "pricing_model": None}
    rates = snapshot["models"][name]
    suffix = "_above_200k_tokens" if tokens_in > 200_000 else ""
    input_rate = rates.get("input_cost_per_token" + suffix, rates["input_cost_per_token"])
    output_rate = rates.get("output_cost_per_token" + suffix, rates["output_cost_per_token"])
    details = (getattr(raw, "usage_metadata", None) or {}).get("input_token_details", {})
    details = details if isinstance(details, dict) else {}
    cached = details.get("cache_read", 0)
    cached = min(cached, tokens_in) if isinstance(cached, int) and not isinstance(cached, bool) and cached >= 0 else 0
    cache_rate = rates.get("cache_read_input_token_cost" + suffix,
                           rates.get("cache_read_input_token_cost", input_rate))
    cost = (tokens_in - cached) * input_rate + cached * cache_rate + tokens_out * output_rate
    return {"cost_usd": cost, "pricing_source": "litellm_snapshot", "pricing_model": name}
