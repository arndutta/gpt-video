CREATE TABLE IF NOT EXISTS cache_metadata (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS llm_responses (
    exact_key TEXT PRIMARY KEY, namespace TEXT NOT NULL,
    equivalence_hash TEXT NOT NULL, embedding TEXT NOT NULL,
    response TEXT NOT NULL, created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS llm_semantic ON llm_responses(namespace,equivalence_hash);

CREATE TABLE IF NOT EXISTS llm_cache_stats (name TEXT PRIMARY KEY,value INTEGER NOT NULL);
