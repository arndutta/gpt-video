CREATE TABLE IF NOT EXISTS governance_control (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1), mode TEXT NOT NULL,
    generation INTEGER NOT NULL, policy_version INTEGER NOT NULL, policy TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT NOT NULL, revision INTEGER NOT NULL, run_id TEXT NOT NULL,
    sku TEXT NOT NULL, created_at TEXT NOT NULL, evidence TEXT NOT NULL,
    PRIMARY KEY(id,revision)
);

CREATE INDEX IF NOT EXISTS recommendation_run ON recommendations(run_id,sku);

CREATE TABLE IF NOT EXISTS recommendation_state (
    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL,
    approval TEXT, hold_until TEXT, execution TEXT,
    FOREIGN KEY(id,revision) REFERENCES recommendations(id,revision)
);

CREATE TABLE IF NOT EXISTS price_outbox (
    batch_key TEXT PRIMARY KEY, created_at TEXT NOT NULL, generation INTEGER NOT NULL,
    payload TEXT NOT NULL, item_refs TEXT NOT NULL, status TEXT NOT NULL,
    receipt TEXT, attempts INTEGER NOT NULL DEFAULT 0
);

CREATE TRIGGER IF NOT EXISTS recommendation_no_update BEFORE UPDATE ON recommendations
    BEGIN SELECT RAISE(ABORT,'Recommendation evidence is immutable'); END;

CREATE TRIGGER IF NOT EXISTS recommendation_no_delete BEFORE DELETE ON recommendations
    BEGIN SELECT RAISE(ABORT,'Recommendation evidence is immutable'); END;

CREATE TRIGGER IF NOT EXISTS outbox_payload_immutable BEFORE UPDATE OF payload,item_refs ON price_outbox
    BEGIN SELECT RAISE(ABORT,'Dispatch payload is immutable'); END;
