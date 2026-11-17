"""Remove obsolete data sidecars only after verifying their persisted SQLite rows."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3

from commerce.market import initialize_market, quote_values


def _stored_rows(path: Path, query: str) -> list[tuple]:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
        return db.execute(query).fetchall()


def cleanup_legacy_json(data_dir: str | Path) -> list[str]:
    """Migrate/verify the two known legacy data files, then remove matching copies.

    An edited or malformed file, or data differing from SQLite, is retained. All
    comparisons finish before either file is removed. Other JSON files are untouched.
    """
    directory = Path(data_dir)
    candidates = []
    feed = directory / "competitor_feed.json"
    if feed.exists():
        initialize_market(directory)
        content = feed.read_bytes()
        payload = json.loads(content)
        quotes = payload.get("items") if isinstance(payload, dict) else payload
        expected = sorted(quote_values(quotes))
        actual = sorted(_stored_rows(directory / "market.db",
                                    "SELECT sku,competitor,price,observed_at FROM competitor_quotes"))
        if expected != actual:
            raise ValueError("Cannot remove competitor_feed.json: its data differs from market.db")
        candidates.append((feed, content))
    truth = directory / "evaluation_truth.json"
    if truth.exists():
        content = truth.read_bytes()
        payload = json.loads(content)
        actual = {sku: {"elasticity": elasticity, "baseline_demand": demand}
                  for sku, elasticity, demand in _stored_rows(
                      directory / "commerce.db", "SELECT sku,elasticity,baseline_demand FROM evaluation_truth")}
        if not isinstance(payload, dict) or payload != actual:
            raise ValueError("Cannot remove evaluation_truth.json: its data differs from commerce.db")
        candidates.append((truth, content))
    if any(path.read_bytes() != content for path, content in candidates):
        raise ValueError("Legacy data changed during verification; retry cleanup")
    for path, _content in candidates:
        path.unlink()
    return [path.name for path, _content in candidates]
