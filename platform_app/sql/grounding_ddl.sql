CREATE TABLE IF NOT EXISTS grounding_uploads (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL,
    source_id TEXT NOT NULL, title TEXT NOT NULL, collection TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    completed_at TEXT, error_code TEXT, error TEXT, result TEXT
);

CREATE INDEX IF NOT EXISTS grounding_uploads_created
    ON grounding_uploads(created_at DESC);
