"""Startup metadata initialization releases SQLite handles even when it fails."""

import sqlite3

import pytest

from platform_app.storage import Store


@pytest.mark.parametrize("fail_metadata", [False, True])
def test_startup_closes_every_database_connection_on_success_and_metadata_failure(tmp_path, monkeypatch, fail_metadata):
    import platform_app.storage as module
    connections, connect = [], sqlite3.connect

    class Connection(sqlite3.Connection):
        was_closed = False

        def executescript(self, sql, *args, **kwargs):
            if fail_metadata and "CREATE TABLE IF NOT EXISTS cache_metadata" in sql:
                raise OSError("Explicit metadata initialization failure")
            return super().executescript(sql, *args, **kwargs)

        def close(self):
            self.was_closed = True
            super().close()

    def tracked(*args, **kwargs):
        db = connect(*args, **kwargs, factory=Connection)
        connections.append(db)
        return db

    monkeypatch.setattr(module.sqlite3, "connect", tracked)
    if fail_metadata:
        with pytest.raises(OSError, match="metadata initialization failure"):
            Store(tmp_path)
    else:
        Store(tmp_path)
    assert len(connections) == 2
    assert all(db.was_closed for db in connections)
    for db in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            db.execute("SELECT 1")
