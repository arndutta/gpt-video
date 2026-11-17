"""Install the independent SQLite market feed and migrate legacy JSON once."""

from contextlib import closing
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3


SQL_DIR = Path(__file__).with_name("sql")
INSERT_QUOTES = (SQL_DIR / "market_seed.sql").read_text(encoding="utf-8")


def quote_values(quotes: list[dict]) -> list[tuple]:
    """Validate legacy and generated feed data before starting any replacement."""
    if not isinstance(quotes, list) or len(quotes) > 10000:
        raise ValueError("Competitor feed must contain at most 10000 quote objects")
    values = []
    for item in quotes:
        if (not isinstance(item, dict) or set(item) != {"sku", "competitor", "price", "observed_at"}
                or any(not isinstance(item[key], str) or not 1 <= len(item[key]) <= 100
                       for key in ("sku", "competitor"))
                or not isinstance(item["price"], str)
                or not re.fullmatch(r"\d{1,8}(?:\.\d{1,2})?", item["price"])
                or Decimal(item["price"]) <= 0
                or not isinstance(item["observed_at"], str) or not 10 <= len(item["observed_at"]) <= 40):
            raise ValueError("Invalid competitor quote in market data")
        date.fromisoformat(item["observed_at"][:10])
        values.append(tuple(item[key] for key in ("sku", "competitor", "price", "observed_at")))
    return values


def initialize_market(data_dir: str | Path, *, import_legacy=True) -> Path:
    """Create market.db; import legacy JSON only if no persisted quotes exist."""
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "market.db"
    legacy = directory / "competitor_feed.json"
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript((SQL_DIR / "market_schema.sql").read_text(encoding="utf-8"))
        with db:
            db.execute("BEGIN IMMEDIATE")
            migrated = db.execute("SELECT value FROM market_metadata WHERE key='legacy_competitor_import'").fetchone()
            if import_legacy and legacy.exists() and not migrated:
                if db.execute("SELECT COUNT(*) FROM competitor_quotes").fetchone()[0]:
                    state = "skipped_existing_quotes"
                else:
                    payload = json.loads(legacy.read_text(encoding="utf-8"))
                    quotes = payload.get("items") if isinstance(payload, dict) else payload
                    db.executemany(INSERT_QUOTES, quote_values(quotes))
                    state = "imported"
                db.execute("INSERT INTO market_metadata(key,value) VALUES('legacy_competitor_import',?)", (state,))
    return path


def replace_quotes(data_dir: str | Path, quotes: list[dict]) -> int:
    """Atomically replace a synthetic feed; invalid rows leave existing data intact."""
    values = quote_values(quotes)
    path = initialize_market(data_dir, import_legacy=False)
    with closing(sqlite3.connect(path, timeout=10)) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM competitor_quotes")
            db.executemany(INSERT_QUOTES, values)
    return len(values)
