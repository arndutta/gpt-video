"""Commerce-owned SQLite schema and read helpers."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


SCHEMA = Path(__file__).with_name("sql").joinpath("schema.sql").read_text(encoding="utf-8")


def seed_statements() -> dict[str, str]:
    """Load named, parameterized DML statements used by the seed installer."""
    script = Path(__file__).with_name("sql").joinpath("seed.sql").read_text(encoding="utf-8")
    return {name.strip(): statement.strip() for block in script.split("-- name: ")[1:]
            for name, _, statement in [block.partition("\n")]}


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
    from commerce.market import initialize_market
    initialize_market(path.parent)


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
