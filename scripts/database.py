"""Install or inspect local SQLite data without replacing an existing catalog."""

import argparse
from contextlib import closing
from datetime import date
import json
import math
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile

from commerce.legacy import cleanup_legacy_json
from commerce.market import initialize_market
from commerce.seed import seed_database
from commerce.storage import connect, initialize
from platform_app.database import initialize_platform, sql
from platform_app.llm.pricing import initialize_pricing
from platform_app.rag.migration import migrate_chroma
from platform_app.rag.models import RagError


DATABASES = ("commerce.db", "market.db", "app.db", "llm_cache.db", "rag.db")


def initialize_rag(data_dir: Path) -> dict:
    """Migrate legacy evidence, then create empty schemas without claiming a model."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    migration = migrate_chroma(data_dir)
    with closing(sqlite3.connect(data_dir / "rag.db", timeout=10)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(sql("manifest_ddl.sql") + sql("manifest_dml.sql") + sql("rag_ddl.sql"))
    return migration


def inspect_database(path: Path) -> dict:
    """Read persisted counts and verify SQLite and relational integrity."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
        db.execute("BEGIN")
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != ["ok"] or foreign_keys:
            raise ValueError(f"Integrity check failed for {path.name}")
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {"path": str(path), "integrity": "ok", "tables": {
            name: db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
            for name in tables}}


def install(data_dir: Path, *, schema_only=False, sku_count=500, days=180, seed=42,
            as_of: date | None = None) -> dict:
    """Run additive DDL, one-time imports and DML; seed only an empty Commerce DB."""
    data_dir = Path(data_dir)
    initialize(data_dir / "commerce.db")
    initialize_market(data_dir)
    initialize_platform(data_dir)
    initialize_pricing(data_dir)
    rag_migration = initialize_rag(data_dir)
    seeded = False
    with connect(data_dir / "commerce.db") as db:
        populated = db.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0
    if not populated and not schema_only:
        seed_database(data_dir / "commerce.db", data_dir=data_dir, sku_count=sku_count,
                      days=days, seed=seed, as_of=as_of or date.today())
        seeded = True
    return {"status": "ok", "seeded_new_catalog": seeded, "rag_migration": rag_migration,
            "databases": {name: inspect_database(data_dir / name) for name in DATABASES}}


def sql_value(value) -> str:
    """Preserve binary float precision and embedded NULs, unlike SQLite quote()."""
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, str):
        if "\0" in value:
            return "CAST(X'" + value.encode("utf-8").hex() + "' AS TEXT)"
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-9e999" if value < 0 else "9e999"
        # SQLite's decimal parser can differ from Python by one ULP, even with
        # 17+ digits. An exact integer significand scaled by powers of two avoids it.
        fraction, exponent = math.frexp(value)
        significand = int(math.ldexp(fraction, 53))
        exponent -= 53
        expression = f"CAST({significand} AS REAL)"
        while exponent:
            step = min(abs(exponent), 52)
            expression += ("*" if exponent > 0 else "/") + str(1 << step)
            exponent += -step if exponent > 0 else step
        return "(" + expression + ")"
    return repr(value)


def write_dump(db, stream) -> None:
    """Write schemas before data and immutable triggers after data for fresh restores."""
    tables = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    stream.write("BEGIN TRANSACTION;\nPRAGMA defer_foreign_keys=ON;\n")
    for _name, ddl in tables:
        stream.write(ddl + ";\n")
    # AUTOINCREMENT sequences can exceed the greatest remaining row ID.
    if (db.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone()
            and db.execute("SELECT 1 FROM sqlite_sequence LIMIT 1").fetchone()):
        tables.append(("sqlite_sequence", None))
    for name, _ddl in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        if name == "sqlite_sequence":
            stream.write("DELETE FROM sqlite_sequence;\n")
        for row in db.execute("SELECT * FROM " + quoted):
            stream.write("INSERT INTO " + quoted + " VALUES(" + ",".join(map(sql_value, row)) + ");\n")
    for (ddl,) in db.execute("SELECT sql FROM sqlite_master WHERE type IN ('index','trigger','view') "
                             "AND sql IS NOT NULL ORDER BY type,name"):
        stream.write(ddl + ";\n")
    stream.write("COMMIT;\n")


def export_sql(data_dir: Path, output_dir: Path) -> list[str]:
    """Export consistent, replayable DDL and exact INSERT DML from each database."""
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for name in DATABASES:
        path = data_dir / name
        output = output_dir / (Path(name).stem + ".sql")
        temporary = None
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
                db.execute("BEGIN")
                with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_dir, delete=False) as stream:
                    temporary = Path(stream.name)
                    write_dump(db, stream)
            temporary.replace(output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        files.append(str(output))
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "status", "cleanup-legacy"), nargs="?", default="install")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", "data")))
    parser.add_argument("--schema-only", action="store_true", help="Create schemas/reference rates without demo products.")
    parser.add_argument("--sku-count", type=int, default=500)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--export-dir", type=Path, help="Write full SQL dumps with DDL and saved row INSERT statements.")
    args = parser.parse_args(argv)
    if not 1 <= args.sku_count <= 5000 or not 1 <= args.days <= 3650:
        parser.error("Use 1–5000 SKUs and 1–3650 history days.")
    try:
        if args.command == "install":
            result = install(args.data_dir, schema_only=args.schema_only, sku_count=args.sku_count,
                             days=args.days, seed=args.seed, as_of=args.as_of)
        elif args.command == "cleanup-legacy":
            result = {"status": "ok", "removed_legacy_files": cleanup_legacy_json(args.data_dir)}
        else:
            result = {"status": "ok", "databases": {
                name: inspect_database(args.data_dir / name) for name in DATABASES}}
        if args.export_dir:
            result["sql_exports"] = export_sql(args.data_dir, args.export_dir)
    except (OSError, ValueError, sqlite3.Error, RagError) as error:
        parser.exit(1, f"Database operation failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
