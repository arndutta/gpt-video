"""Persistent two-tier cache; semantic reuse requires verified equivalent input text.

Similarity alone can never authorize reuse. Only Unicode/case/whitespace-equivalent
instructions share the conservative semantic tier, with identical facts and evidence.
No prompt, evidence body, credentials, or raw provider response is persisted.
"""

from platform_app.database import sql

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
import unicodedata

from .safety import canonical, digest


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def vector(text: str) -> list[float]:
    result = [0.0] * 64
    for word in re.findall(r"\w+|[^\w\s]", text):
        number = int(hashlib.sha256(word.encode()).hexdigest(), 16)
        result[number % 64] += 1 if number & 64 else -1
    norm = math.sqrt(sum(item * item for item in result)) or 1
    return [item / norm for item in result]


class ResponseCache:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "llm_cache.db"
        self.lock = threading.Lock()
        with self.connection() as db:
            db.executescript(sql("cache_ddl.sql") + sql("cache_dml.sql"))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def keys(namespace: dict, prompt: str, query: str):
        exact = digest([namespace, prompt, query])
        semantic_text = normalized(prompt) + "\n" + normalized(query)
        return exact, digest(namespace), digest(semantic_text), vector(semantic_text)

    def get(self, keys):
        exact, namespace, equivalence, embedding = keys
        with self.connection() as db:
            row = db.execute("SELECT response FROM llm_responses WHERE exact_key=?", (exact,)).fetchone()
            tier = "exact"
            if row is None:
                candidates = db.execute("SELECT response,embedding FROM llm_responses WHERE namespace=? "
                                        "AND equivalence_hash=? LIMIT 8", (namespace, equivalence)).fetchall()
                row = next((item for item in candidates if sum(
                    left * right for left, right in zip(embedding, json.loads(item["embedding"]))
                ) >= 0.999999), None)
                tier = "semantic"
            stat = f"{tier}_hits" if row else "misses"
            db.execute("UPDATE llm_cache_stats SET value=value+1 WHERE name=?", (stat,))
            return (json.loads(row["response"]), tier) if row else (None, "miss")

    def put(self, keys, response: dict):
        exact, namespace, equivalence, embedding = keys
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO llm_responses VALUES(?,?,?,?,?,?)",
                       (exact, namespace, equivalence, canonical(embedding), canonical(response), time.time()))

    def remove(self, keys):
        with self.connection() as db:
            db.execute("DELETE FROM llm_responses WHERE exact_key=? OR (namespace=? AND equivalence_hash=?)", keys[:3])

    def stats(self):
        with self.connection() as db:
            values = {row["name"]: row["value"] for row in db.execute("SELECT * FROM llm_cache_stats")}
            values["entries"] = db.execute("SELECT count(*) FROM llm_responses").fetchone()[0]
        return {**values, "hits": values["exact_hits"] + values["semantic_hits"], "available": True}
