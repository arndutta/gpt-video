"""Explicit offline migration of legacy Chroma evidence into the SQLite RAG store."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import tempfile

from platform_app.database import sql
from .embedding_common import validate_vectors
from .models import COLLECTION_NAMES, EvidenceChunk, RagError


MIGRATION = "legacy_chroma_v1"
MANIFEST_TABLES = ("embedding_identity", "corpus", "versions", "active_documents")
CHUNK_COLUMNS = ("collection", "id", "document_key", "source_id", "version", "title",
                 "content_hash", "chunk_index", "start_char", "end_char", "source_uri",
                 "document", "embedding")


def _readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def _snapshot(source, target):
    # The legacy client may migrate or checkpoint its files when opened. Only a
    # disposable copy is given to it; source databases are backed up read-only.
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("*.sqlite3", "*.sqlite3-wal", "*.sqlite3-shm"))
    for name in ("manifest.sqlite3", "chroma.sqlite3"):
        with closing(_readonly(source / name)) as original:
            with closing(sqlite3.connect(target / name)) as snapshot:
                original.backup(snapshot)


def _manifest(path):
    with closing(_readonly(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RagError("The legacy manifest failed SQLite integrity checks.")
        rows = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table}")]
                for table in MANIFEST_TABLES}
        if len(rows["embedding_identity"]) != 1 or rows["embedding_identity"][0]["id"] != 1:
            raise RagError("The legacy manifest has no unique embedding identity.")
        identity = json.loads(rows["embedding_identity"][0]["identity"])
        dimensions = identity.get("dimensions")
        if (type(dimensions) is not int or dimensions < 1 or not isinstance(identity.get("model_id"), str)
                or not identity["model_id"].strip()):
            raise RagError("The legacy embedding identity is invalid.")
        corpus = rows["corpus"]
        if (len(corpus) != 1 or corpus[0]["id"] != 1 or type(corpus[0]["revision"]) is not int
                or corpus[0]["revision"] < 0):
            raise RagError("The legacy corpus revision is invalid.")
        versions = {(row["collection"], row["source_id"], row["version"]): row for row in rows["versions"]}
        for row in rows["versions"]:
            if (row["collection"] not in COLLECTION_NAMES or type(row["chunk_count"]) is not int
                    or row["chunk_count"] < 1 or row["ready"] not in (0, 1)):
                raise RagError("The legacy document manifest is invalid.")
        for active in rows["active_documents"]:
            version = versions.get((active["collection"], active["source_id"], active["version"]))
            if not version or not version["ready"]:
                raise RagError("The legacy active document has no published version.")
        return rows, dimensions


def _chunks(path, manifest, dimensions):
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
    except ImportError:
        raise RagError("Legacy migration requires the optional Chroma reader. Install "
                       "'retail-pricing-workbench[legacy-rag]' and retry the migrate command.") from None
    client = chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))
    rows, indices = [], {}
    versions = {row["document_key"]: row for row in manifest["versions"]}
    try:
        collections = client.list_collections()
        for item in collections:
            name = item if isinstance(item, str) else item.name
            if name not in COLLECTION_NAMES:
                raise RagError("The legacy index has an unknown collection; migration will not discard it.")
            collection = client.get_collection(name, embedding_function=None)
            count = collection.count()
            result = collection.get(include=["documents", "metadatas", "embeddings"])
            for identifier, document, metadata, vector in zip(
                    result["ids"], result["documents"], result["metadatas"], result["embeddings"], strict=True):
                if not isinstance(metadata, dict) or metadata.get("document_key") not in versions:
                    raise RagError("Legacy chunk metadata has no document manifest.")
                version = versions[metadata["document_key"]]
                if (metadata.get("collection") != name or version["collection"] != name
                        or metadata.get("source_id") != version["source_id"]
                        or metadata.get("version") != version["version"]):
                    raise RagError("Legacy chunk metadata does not match its document manifest.")
                EvidenceChunk(citation_id=identifier, text=document, **{key: metadata[key] for key in (
                    "source_id", "title", "collection", "version", "chunk_index", "start_char", "end_char")},
                    source_uri=metadata.get("source_uri"))
                key, index = metadata["document_key"], metadata["chunk_index"]
                if identifier != f"rag:{name}:{key}:{index}" or not isinstance(metadata.get("content_hash"), str):
                    raise RagError("The legacy index has an invalid citation identifier or content hash.")
                indices.setdefault(key, []).append(index)
                validated = validate_vectors([vector], 1, dimensions)[0]
                values = {**metadata, "collection": name, "id": identifier, "document": document,
                          "embedding": struct.pack("<" + "d" * dimensions, *validated)}
                rows.append(tuple(values.get(column) for column in CHUNK_COLUMNS))
            if len([row for row in rows if row[0] == name]) != count:
                raise RagError("The legacy index changed while reading; stop the app and retry migration.")
        for key, version in versions.items():
            actual = indices.get(key, [])
            if version["ready"] and sorted(actual) != list(range(version["chunk_count"])):
                raise RagError("Published legacy evidence has missing or duplicate chunks; repair before migration.")
    finally:
        close = getattr(client, "close", None)
        if close:
            close()
    return rows


def _completed(db):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rag_migrations'").fetchone()
    return db.execute("SELECT chunks FROM rag_migrations WHERE name=?", (MIGRATION,)).fetchone() if exists else None


def requires_migration(data_dir: str | Path) -> bool:
    """An unfinished import must not let retrieval silently open an empty store."""
    directory = Path(data_dir)
    if not any((directory / "chroma" / name).exists() for name in ("manifest.sqlite3", "chroma.sqlite3")):
        return False
    target = directory / "rag.db"
    if not target.exists():
        return True
    with closing(_readonly(target)) as db:
        return _completed(db) is None


def _empty_target(db, identity):
    for table in ("versions", "active_documents", "rag_chunks"):
        if db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise RagError("SQLite evidence already exists. Migration will not overwrite it; use a separate data directory.")
    if db.execute("SELECT 1 FROM corpus WHERE revision<>0").fetchone():
        raise RagError("The SQLite corpus is not empty; migration will not overwrite it.")
    existing = db.execute("SELECT identity FROM embedding_identity WHERE id=1").fetchone()
    if existing and existing[0] != identity:
        raise RagError("The SQLite embedding identity differs from legacy evidence; use a separate data directory.")


def migrate_chroma(data_dir: str | Path) -> dict:
    """Copy all legacy evidence without embedding calls; stop app processes first.

    A committed marker makes retries harmless. Failures never publish a partial import
    or change the source Chroma directory, and populated SQLite stores are preserved.
    """
    directory = Path(data_dir)
    source, target = directory / "chroma", directory / "rag.db"
    if target.exists():
        with closing(_readonly(target)) as db:
            completed = _completed(db)
        if completed:
            return {"status": "already_migrated", "migrated": False, "chunks": completed[0]}
    files = [source / name for name in ("manifest.sqlite3", "chroma.sqlite3")]
    if not any(path.exists() for path in files):
        return {"status": "no_legacy_store", "migrated": False, "chunks": 0}
    if not all(path.is_file() for path in files):
        raise RagError("The legacy evidence store is incomplete; restore both Chroma and manifest databases before migration.")
    try:
        with tempfile.TemporaryDirectory(prefix="pricing-rag-migration-") as temporary:
            snapshot = Path(temporary) / "chroma"
            _snapshot(source, snapshot)
            manifest, dimensions = _manifest(snapshot / "manifest.sqlite3")
            rows = _chunks(snapshot, manifest, dimensions)
        with closing(sqlite3.connect(target, timeout=30)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(sql("manifest_ddl.sql") + sql("manifest_dml.sql") + sql("rag_ddl.sql"))
            with db:
                db.execute("BEGIN IMMEDIATE")
                completed = _completed(db)
                if completed:
                    return {"status": "already_migrated", "migrated": False, "chunks": completed[0]}
                _empty_target(db, manifest["embedding_identity"][0]["identity"])
                for table in MANIFEST_TABLES:
                    for row in manifest[table]:
                        columns = list(row)
                        operation = "INSERT OR REPLACE" if table == "corpus" else "INSERT OR IGNORE"
                        db.execute(f"{operation} INTO {table} ({','.join(columns)}) "
                                   f"VALUES ({','.join('?' for _ in columns)})", list(row.values()))
                db.executemany("INSERT OR IGNORE INTO rag_collections(name,dimensions) VALUES(?,?)",
                               [(name, dimensions) for name in COLLECTION_NAMES])
                db.executemany(f"INSERT INTO rag_chunks({','.join(CHUNK_COLUMNS)}) "
                               f"VALUES({','.join('?' for _ in CHUNK_COLUMNS)})", rows)
                if db.execute("PRAGMA foreign_key_check").fetchone():
                    raise RagError("Migrated evidence failed its reference checks; no import was committed.")
                db.execute("INSERT INTO rag_migrations VALUES(?,?,?)",
                           (MIGRATION, datetime.now(timezone.utc).isoformat(), len(rows)))
        return {"status": "migrated", "migrated": True, "chunks": len(rows),
                "versions": len(manifest["versions"]), "active_documents": len(manifest["active_documents"])}
    except RagError:
        raise
    except Exception:
        raise RagError("Legacy evidence migration failed without publication. Stop the application, "
                       "check the legacy index and permissions, and retry; the source is preserved.") from None
