"""Packaged SQLite DDL/DML shared by runtime repositories and installation."""

from contextlib import closing
from pathlib import Path
import sqlite3


SQL_DIR = Path(__file__).with_name("sql")
APP_SCHEMAS = ("app", "governance", "feedback", "grounding", "loop", "scenarios", "discovery", "usage")


def sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding="utf-8")


def initialize_platform(data_dir: Path) -> None:
    """Create every platform table without interrupting runs or changing approvals."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(data_dir / "app.db", timeout=10)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("\n".join(sql(name + "_ddl.sql") for name in APP_SCHEMAS))
        # Older app databases are upgraded by the same additive migration as runtime.
        columns = {row[1] for row in db.execute("PRAGMA table_info(llm_usage)")}
        with db:
            if "pricing_source" not in columns:
                db.execute("ALTER TABLE llm_usage ADD COLUMN pricing_source TEXT NOT NULL "
                           "DEFAULT 'legacy_configured_fallback_rates'")
            if "pricing_model" not in columns:
                db.execute("ALTER TABLE llm_usage ADD COLUMN pricing_model TEXT")
        db.executescript(sql("app_dml.sql") + sql("governance_dml.sql"))
    with closing(sqlite3.connect(data_dir / "llm_cache.db", timeout=10)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(sql("cache_ddl.sql") + sql("cache_dml.sql"))
