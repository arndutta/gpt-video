"""Immutable document manifests and atomic publication of active evidence versions."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .models import COLLECTION_NAMES, DocumentConflict, EmbeddingMismatch


class Manifest:
    def __init__(self, path: Path, model_id: str, dimensions: int):
        self.path = path
        identity = json.dumps({"model_id": model_id, "dimensions": dimensions}, sort_keys=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS embedding_identity (id INTEGER PRIMARY KEY, identity TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS corpus (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO corpus VALUES (1, 0);
                CREATE TABLE IF NOT EXISTS versions (
                    collection TEXT NOT NULL, source_id TEXT NOT NULL, version TEXT NOT NULL,
                    document_key TEXT NOT NULL UNIQUE, signature TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL, ready INTEGER NOT NULL DEFAULT 0,
                    indexed_at TEXT, PRIMARY KEY(collection, source_id, version)
                );
                CREATE TABLE IF NOT EXISTS active_documents (
                    collection TEXT NOT NULL, source_id TEXT NOT NULL, version TEXT NOT NULL,
                    PRIMARY KEY(collection, source_id),
                    FOREIGN KEY(collection, source_id, version) REFERENCES versions(collection, source_id, version)
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT identity FROM embedding_identity WHERE id=1").fetchone()
            if existing and existing[0] != identity:
                raise EmbeddingMismatch("This evidence store uses a different embedding model or dimension. "
                                        "Choose a separate store path; do not mix vector spaces.")
            db.execute("INSERT OR IGNORE INTO embedding_identity VALUES (1, ?)", (identity,))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _active(db, collection: str, source_id: str) -> str | None:
        row = db.execute("SELECT version FROM active_documents WHERE collection=? AND source_id=?",
                         (collection, source_id)).fetchone()
        return row[0] if row else None

    def prepare(self, collection: str, source_id: str, version: str, document_key: str,
                signature: str, chunk_count: int) -> tuple[bool, str | None]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT signature, ready FROM versions WHERE collection=? AND source_id=? AND version=?",
                             (collection, source_id, version)).fetchone()
            if row and row["signature"] != signature:
                raise DocumentConflict("A source version is immutable. Use a new version for changed text, "
                                       "metadata, or chunking configuration.")
            if not row:
                db.execute("INSERT INTO versions(collection,source_id,version,document_key,signature,chunk_count) "
                           "VALUES(?,?,?,?,?,?)", (collection, source_id, version, document_key, signature, chunk_count))
            return bool(row and row["ready"]), self._active(db, collection, source_id)

    def publish(self, collection: str, source_id: str, version: str, expected_active: str | None) -> bool:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT ready FROM versions WHERE collection=? AND source_id=? AND version=?",
                             (collection, source_id, version)).fetchone()
            if row is None:
                raise DocumentConflict("The staged source manifest is missing; retry ingestion.")
            if row["ready"]:
                return False  # Retrying an old version must not roll a newer active version back.
            if self._active(db, collection, source_id) != expected_active:
                raise DocumentConflict("Another source version was published while indexing. Retry ingestion "
                                       "to publish against the current version.")
            timestamp = datetime.now(timezone.utc).isoformat()
            db.execute("UPDATE versions SET ready=1,indexed_at=? WHERE collection=? AND source_id=? AND version=?",
                       (timestamp, collection, source_id, version))
            db.execute("INSERT INTO active_documents VALUES(?,?,?) ON CONFLICT(collection,source_id) "
                       "DO UPDATE SET version=excluded.version", (collection, source_id, version))
            db.execute("UPDATE corpus SET revision=revision+1 WHERE id=1")
            return True

    def snapshot(self) -> tuple[int, dict[str, list[dict]]]:
        with self.connection() as db:
            db.execute("BEGIN")
            revision = db.execute("SELECT revision FROM corpus WHERE id=1").fetchone()[0]
            rows = db.execute("SELECT v.* FROM active_documents a JOIN versions v "
                              "USING(collection,source_id,version) WHERE v.ready=1 ORDER BY v.source_id").fetchall()
            groups = {name: [] for name in COLLECTION_NAMES}
            for row in rows:
                groups[row["collection"]].append(dict(row))
            return revision, groups

    def published(self, document_key: str) -> bool:
        with self.connection() as db:
            row = db.execute("SELECT ready FROM versions WHERE document_key=?", (document_key,)).fetchone()
            return bool(row and row[0])

    def revision(self) -> int:
        with self.connection() as db:
            return db.execute("SELECT revision FROM corpus WHERE id=1").fetchone()[0]

    def statistics(self) -> list[dict]:
        revision, groups = self.snapshot()
        return [{"collection": name, "document_count": len(groups[name]),
                 "chunk_count": sum(row["chunk_count"] for row in groups[name]),
                 "last_updated": max((row["indexed_at"] for row in groups[name]), default=None),
                 "corpus_version": revision} for name in COLLECTION_NAMES]
