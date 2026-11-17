"""SQLite chunk storage and exact cosine retrieval without an external vector service."""

from contextlib import contextmanager
import math
from pathlib import Path
import sqlite3
import struct

from platform_app.database import sql
from .embedding_common import validate_vectors
from .models import EmbeddingMismatch


TEXT_FIELDS = ("document_key", "source_id", "version", "title", "content_hash")
INTEGER_FIELDS = ("chunk_index", "start_char", "end_char")
META_FIELDS = (*TEXT_FIELDS, *INTEGER_FIELDS, "source_uri")
COLUMNS = ("collection", "id", *META_FIELDS, "document", "embedding")


class SQLiteIndex:
    def __init__(self, path: Path, dimensions: int):
        if type(dimensions) is not int or dimensions < 1:
            raise ValueError("Embedding dimensions must be a positive integer")
        self.path, self.dimensions, self._closed = Path(path), dimensions, False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(sql("rag_ddl.sql"))

    @contextmanager
    def connection(self):
        if self._closed:
            raise RuntimeError("The SQLite retrieval index is closed")
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            db.create_function("cosine_distance", 2, self._distance, deterministic=True)
            with db:
                yield db
        finally:
            db.close()

    def get_or_create_collection(self, name, embedding_function=None, metadata=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A nonblank collection name is required")
        if embedding_function is not None or (metadata or {}).get("hnsw:space", "cosine") != "cosine":
            raise ValueError("SQLite retrieval requires supplied vectors and cosine distance")
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO rag_collections(name,dimensions) VALUES(?,?)",
                       (name, self.dimensions))
            dimensions = db.execute("SELECT dimensions FROM rag_collections WHERE name=?", (name,)).fetchone()[0]
            if dimensions != self.dimensions:
                raise EmbeddingMismatch("The stored collection uses different embedding dimensions")
        return SQLiteCollection(self, name)

    def _unpack(self, blob):
        if not isinstance(blob, bytes) or len(blob) != self.dimensions * 8:
            raise ValueError("The stored embedding has invalid dimensions")
        values = struct.unpack(f"<{self.dimensions}d", blob)
        if not all(math.isfinite(value) for value in values) or not any(values):
            raise ValueError("The stored embedding is invalid")
        return values

    @staticmethod
    def _unit(values):
        scale = max(map(abs, values))
        scaled = [value / scale for value in values]
        norm = math.sqrt(math.fsum(value * value for value in scaled))
        return [value / norm for value in scaled]

    def _distance(self, left, right):
        first, second = self._unit(self._unpack(left)), self._unit(self._unpack(right))
        similarity = math.fsum(a * b for a, b in zip(first, second, strict=True))
        return 1.0 - max(-1.0, min(1.0, similarity))

    def _pack(self, vectors, count):
        return [struct.pack(f"<{self.dimensions}d", *vector)
                for vector in validate_vectors(vectors, count, self.dimensions)]

    def close(self):
        self._closed = True


class SQLiteCollection:
    def __init__(self, index: SQLiteIndex, name: str):
        self.index, self.name = index, name

    @staticmethod
    def _include(include, defaults, allowed):
        fields = list(defaults if include is None else include)
        if any(field not in allowed for field in fields):
            raise ValueError("Unsupported retrieval result field")
        return fields

    def _filters(self, ids, where):
        clauses, values = ["collection=?"], [self.name]
        if ids is not None:
            ids = [ids] if isinstance(ids, str) else list(ids)
            if any(not isinstance(value, str) or not value for value in ids):
                raise ValueError("Chunk IDs must be nonempty strings")
            clauses.append("id IN (" + ",".join("?" for _ in ids) + ")" if ids else "0")
            values.extend(ids)
        if where is not None:
            if not isinstance(where, dict) or set(where) != {"document_key"}:
                raise ValueError("Only document_key filters are supported")
            keys = where["document_key"]
            if isinstance(keys, str):
                keys = [keys]
            elif isinstance(keys, dict) and set(keys) == {"$in"} and isinstance(keys["$in"], list):
                keys = keys["$in"]
            else:
                raise ValueError("Invalid document_key filter")
            if any(not isinstance(value, str) or not value for value in keys):
                raise ValueError("Document keys must be nonempty strings")
            clauses.append("document_key IN (" + ",".join("?" for _ in keys) + ")" if keys else "0")
            values.extend(keys)
        return " AND ".join(clauses), values

    def upsert(self, ids, documents, metadatas, embeddings):
        count = len(ids)
        if not count or any(len(values) != count for values in (documents, metadatas, embeddings)):
            raise ValueError("Chunk fields must have the same nonzero length")
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != count:
            raise ValueError("Chunk IDs must be unique nonempty strings")
        vectors = self.index._pack(embeddings, count)
        rows = []
        for identifier, document, metadata, vector in zip(ids, documents, metadatas, vectors, strict=True):
            if not isinstance(document, str) or not document.strip() or not isinstance(metadata, dict):
                raise ValueError("Chunks need nonblank text and source metadata")
            if (set(metadata) - {*META_FIELDS, "collection"}
                    or metadata.get("collection", self.name) != self.name
                    or any(not isinstance(metadata.get(key), str) or not metadata[key].strip() for key in TEXT_FIELDS)
                    or any(type(metadata.get(key)) is not int for key in INTEGER_FIELDS)
                    or metadata["chunk_index"] < 0 or metadata["start_char"] < 0
                    or metadata["end_char"] <= metadata["start_char"]
                    or not isinstance(metadata.get("source_uri"), (str, type(None)))):
                raise ValueError("Invalid chunk source metadata")
            rows.append((self.name, identifier, *(metadata.get(key) for key in META_FIELDS), document, vector))
        updates = ",".join(column + "=excluded." + column for column in COLUMNS[2:])
        statement = ("INSERT INTO rag_chunks(" + ",".join(COLUMNS) + ") VALUES("
                     + ",".join("?" for _ in COLUMNS) + ") ON CONFLICT(collection,id) DO UPDATE SET " + updates)
        with self.index.connection() as db:
            db.executemany(statement, rows)

    def _result(self, rows, include):
        result = {"ids": [row["id"] for row in rows], **{field: [] for field in include}}
        for row in rows:
            vector = self.index._unpack(row["embedding"])
            if "documents" in include:
                result["documents"].append(row["document"])
            if "metadatas" in include:
                result["metadatas"].append({"collection": row["collection"], **{
                    key: row[key] for key in META_FIELDS if row[key] is not None}})
            if "embeddings" in include:
                result["embeddings"].append(list(vector))
            if "distances" in include:
                result["distances"].append(row["distance"])
        return result

    def get(self, ids=None, where=None, include=None):
        fields = self._include(include, ("documents", "metadatas"), {"documents", "metadatas", "embeddings"})
        clause, values = self._filters(ids, where)
        with self.index.connection() as db:
            rows = db.execute("SELECT * FROM rag_chunks WHERE " + clause + " ORDER BY id", values).fetchall()
            return self._result(rows, fields)

    def query(self, query_embeddings, n_results=10, where=None, include=None):
        if type(n_results) is not int or n_results < 1:
            raise ValueError("The retrieval result count must be positive")
        if not len(query_embeddings):
            raise ValueError("At least one query embedding is required")
        vectors = self.index._pack(query_embeddings, len(query_embeddings))
        fields = self._include(include, ("documents", "metadatas", "distances"),
                               {"documents", "metadatas", "embeddings", "distances"})
        clause, values = self._filters(None, where)
        result = {"ids": [], **{field: [] for field in fields}}
        with self.index.connection() as db:
            for vector in vectors:
                rows = db.execute("SELECT *,cosine_distance(embedding,?) AS distance FROM rag_chunks WHERE "
                                  + clause + " ORDER BY distance,id LIMIT ?", [vector, *values, n_results]).fetchall()
                for field, items in self._result(rows, fields).items():
                    result[field].append(items)
        return result

    def delete(self, ids=None, where=None):
        clause, values = self._filters(ids, where)
        with self.index.connection() as db:
            db.execute("DELETE FROM rag_chunks WHERE " + clause, values)

    def count(self):
        with self.index.connection() as db:
            return db.execute("SELECT COUNT(*) FROM rag_chunks WHERE collection=?", (self.name,)).fetchone()[0]
