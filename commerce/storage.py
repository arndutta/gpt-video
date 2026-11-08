"""Commerce-owned SQLite schema and read helpers."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_versions (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    family_id TEXT NOT NULL, size INTEGER NOT NULL CHECK(size > 0),
    currency TEXT NOT NULL, cost TEXT NOT NULL, map_price TEXT NOT NULL,
    min_price TEXT NOT NULL, max_price TEXT NOT NULL,
    max_change_pct REAL NOT NULL, minimum_margin_pct REAL NOT NULL,
    rounding_increment TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prices (
    sku TEXT PRIMARY KEY REFERENCES products(sku), current_price TEXT NOT NULL,
    price_version INTEGER NOT NULL CHECK(price_version > 0), updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT PRIMARY KEY REFERENCES products(sku), on_hand INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku),
    date TEXT NOT NULL, price TEXT NOT NULL, units INTEGER NOT NULL CHECK(units >= 0),
    promotion INTEGER NOT NULL, seasonal_index REAL NOT NULL,
    UNIQUE(sku, date)
);
CREATE INDEX IF NOT EXISTS sales_sku_date ON sales(sku, date);
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku),
    batch_key TEXT, prior_price TEXT NOT NULL, new_price TEXT NOT NULL,
    prior_version INTEGER NOT NULL, new_version INTEGER NOT NULL,
    actor TEXT NOT NULL, approval_kind TEXT NOT NULL, applied_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_sku ON price_history(sku, id);
CREATE TABLE IF NOT EXISTS batches (
    batch_key TEXT PRIMARY KEY, payload_digest TEXT NOT NULL,
    result_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_truth (
    sku TEXT PRIMARY KEY REFERENCES products(sku), elasticity REAL NOT NULL,
    baseline_demand REAL NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: str | Path):
    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
    finally:
        connection.close()


def initialize(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO schema_versions VALUES (?, ?)", (1, utc_now())
        )
        connection.commit()


def source_timestamp(connection: sqlite3.Connection) -> str | None:
    row = connection.execute("SELECT value FROM metadata WHERE key = 'as_of'").fetchone()
    return row[0] if row else None


def product_rows(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        "SELECT p.*, q.current_price, q.price_version FROM products p "
        "JOIN prices q USING (sku) ORDER BY p.sku"
    )]


def scope_filters(sku: str | None, category: str | None, alias: str = "p"):
    clauses, values = [], []
    if sku:
        skus = [value.strip() for value in sku.split(",") if value.strip()]
        if skus:
            clauses.append(f"{alias}.sku IN ({','.join('?' for _ in skus)})")
            values.extend(skus)
    if category:
        clauses.append(f"{alias}.category = ?")
        values.append(category)
    return clauses, values


def page(connection, select: str, source: str, clauses: list[str], values: list,
         order: str, limit: int, offset: int) -> dict:
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = connection.execute(f"SELECT COUNT(*) FROM {source}{where}", values).fetchone()[0]
    rows = connection.execute(
        f"SELECT {select} FROM {source}{where} ORDER BY {order} LIMIT ? OFFSET ?",
        [*values, limit, offset],
    ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total,
            "as_of": source_timestamp(connection)}
