"""Durable ingestion metadata. Uploaded text and gateway credentials are never stored here."""

import json
from uuid import uuid4

from platform_app.rag.models import Document
from platform_app.storage import Store, now


class UploadJobs:
    def __init__(self, store: Store):
        self.store = store
        with store.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS grounding_uploads (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL,
                    source_id TEXT NOT NULL, title TEXT NOT NULL, collection TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    completed_at TEXT, error_code TEXT, error TEXT, result TEXT
                );
                CREATE INDEX IF NOT EXISTS grounding_uploads_created
                    ON grounding_uploads(created_at DESC);
            """)
            pending = db.execute("SELECT * FROM grounding_uploads WHERE status IN ('queued','indexing')").fetchall()
            for row in pending:
                self._update(db, dict(row), "interrupted", error_code="upload_interrupted",
                             error="Application stopped before ingestion completed. Upload the file again to retry.")

    @staticmethod
    def _decode(row) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        item["result"] = json.loads(item["result"]) if item["result"] else None
        return item

    def create(self, document: Document, filename: str) -> dict:
        timestamp = now()
        item = {"id": str(uuid4()), "filename": filename, "source_id": document.source_id,
                "title": document.title, "collection": document.collection, "status": "queued",
                "created_at": timestamp, "updated_at": timestamp, "completed_at": None,
                "error_code": None, "error": None, "result": None}
        with self.store.connection() as db:
            db.execute("INSERT INTO grounding_uploads VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", tuple(item.values()))
            self._audit(db, item, "human")
        return item

    def _audit(self, db, item: dict, actor="system"):
        detail = {key: item[key] for key in ("id", "filename", "source_id", "collection", "status")}
        if item.get("error_code"):
            detail["error_code"] = item["error_code"]
        if item.get("result"):
            result = item["result"]
            if isinstance(result, str):
                result = json.loads(result)
            detail.update({key: result[key] for key in ("version", "chunk_count", "corpus_version", "changed")})
        self.store._audit(db, actor, f"grounding_upload_{item['status']}", None, detail)

    def _update(self, db, item: dict, status: str, *, result=None, error_code=None, error=None):
        item.update(status=status, updated_at=now(),
                    completed_at=now() if status in {"ready", "failed", "interrupted"} else None,
                    result=json.dumps(result, allow_nan=False) if result is not None else None,
                    error_code=error_code, error=error)
        db.execute("UPDATE grounding_uploads SET status=?,updated_at=?,completed_at=?,result=?,"
                   "error_code=?,error=? WHERE id=?", tuple(item[key] for key in (
                       "status", "updated_at", "completed_at", "result", "error_code", "error", "id")))
        self._audit(db, item)

    def update(self, job_id: str, status: str, *, result=None, error_code=None, error=None):
        with self.store.connection() as db:
            item = db.execute("SELECT * FROM grounding_uploads WHERE id=?", (job_id,)).fetchone()
            if item is None:
                raise RuntimeError("Ingestion job metadata is missing")
            self._update(db, dict(item), status, result=result, error_code=error_code, error=error)

    def get(self, job_id: str) -> dict | None:
        with self.store.connection() as db:
            return self._decode(db.execute("SELECT * FROM grounding_uploads WHERE id=?", (job_id,)).fetchone())

    def list(self, limit=25) -> list[dict]:
        with self.store.connection() as db:
            rows = db.execute("SELECT * FROM grounding_uploads ORDER BY created_at DESC LIMIT ?",
                              (max(1, min(limit, 100)),)).fetchall()
            return [self._decode(row) for row in rows]
