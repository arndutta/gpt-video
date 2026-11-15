"""Cache transactions release SQLite resources on both success and rollback."""

import sqlite3

import pytest

from platform_app.llm.cache import ResponseCache


@pytest.mark.parametrize("fail", [False, True])
def test_cache_transaction_closes_connection_and_preserves_commit_or_rollback(tmp_path, fail):
    cache = ResponseCache(tmp_path)
    db = None
    try:
        with cache.connection() as db:
            db.execute("UPDATE llm_cache_stats SET value=17 WHERE name='misses'")
            if fail:
                raise RuntimeError("Explicit transaction rollback fixture")
    except RuntimeError:
        assert fail
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")
    assert cache.stats()["misses"] == (0 if fail else 17)


def test_repeated_cache_reads_close_every_sqlite_handle(tmp_path, monkeypatch):
    import platform_app.llm.cache as module

    connections, connect = [], sqlite3.connect

    class TrackedConnection(sqlite3.Connection):
        was_closed = False

        def close(self):
            self.was_closed = True
            super().close()

    def tracked(*args, **kwargs):
        connection = connect(*args, **kwargs, factory=TrackedConnection)
        connections.append(connection)
        return connection

    monkeypatch.setattr(module.sqlite3, "connect", tracked)
    cache = ResponseCache(tmp_path)
    keys = cache.keys({"policy": "v1"}, "Explain policy", "Which rule?")
    cache.put(keys, {"citations": ["policy-v1:0"]})
    for _ in range(30):
        assert cache.get(keys)[1] == "exact"
    assert cache.stats()["hits"] == 30
    assert connections and all(connection.was_closed for connection in connections)
