"""Platform-owned preview runs and append-only audit events, never live business data."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "app.db"
        data_dir.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO schema_version VALUES(1);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, stage TEXT NOT NULL,
                    created_at TEXT NOT NULL, completed_at TEXT,
                    request TEXT NOT NULL, result TEXT, error TEXT
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, run_id TEXT, detail TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
                BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
                BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END;
            """)
            interrupted = db.execute("SELECT id FROM runs WHERE status IN ('queued','running')").fetchall()
            db.execute("UPDATE runs SET status='interrupted',stage='interrupted',"
                       "error='Application stopped. Start a new preview to refresh input data.' "
                       "WHERE status IN ('queued','running')")
            for row in interrupted:
                self._audit(db, "system", "preview_interrupted", row["id"], {})
        with sqlite3.connect(data_dir / "llm_cache.db") as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS cache_metadata (version INTEGER PRIMARY KEY)")
            db.execute("INSERT OR IGNORE INTO cache_metadata VALUES(1)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _audit(db, actor: str, action: str, run_id: str | None, detail: dict):
        db.execute("INSERT INTO audit(timestamp,actor,action,run_id,detail) VALUES(?,?,?,?,?)",
                   (now(), actor, action, run_id, json.dumps(detail, allow_nan=False)))

    def audit(self, action: str, detail: dict, actor="human", run_id=None):
        with self.connection() as db:
            self._audit(db, actor, action, run_id, detail)

    def create_run(self, request: dict) -> dict:
        run_id = str(uuid4())
        with self.connection() as db:
            db.execute("INSERT INTO runs(id,status,stage,created_at,request) VALUES(?,?,?,?,?)",
                       (run_id, "queued", "queued", now(), json.dumps(request)))
            self._audit(db, "human", "preview_requested", run_id, request)
        return self.get_run(run_id)

    def update_run(self, run_id: str, status: str, stage: str, result=None, error=None):
        serialized = json.dumps(result, allow_nan=False) if result is not None else None
        finished = now() if status in {"completed", "failed", "interrupted"} else None
        with self.connection() as db:
            db.execute("UPDATE runs SET status=?,stage=?,completed_at=?,result=?,error=? WHERE id=?",
                       (status, stage, finished, serialized, error, run_id))
            self._audit(db, "system", f"preview_{status}", run_id, {"stage": stage, "error": error})

    @staticmethod
    def _decode(row, include_result=True) -> dict:
        item = dict(row)
        item["request"] = json.loads(item["request"])
        if include_result:
            item["result"] = json.loads(item["result"]) if item["result"] else None
        else:
            item.pop("result", None)
        return item

    def get_run(self, run_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            return self._decode(row) if row else None

    def list_runs(self, limit=50) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT id,status,stage,created_at,completed_at,request,error "
                              "FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [{**dict(row), "request": json.loads(row["request"])} for row in rows]

    def list_audit(self, limit=100) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [{**dict(row), "detail": json.loads(row["detail"])} for row in rows]
