CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);

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

CREATE INDEX IF NOT EXISTS audit_run ON audit(run_id,id);
