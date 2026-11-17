CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, run_id TEXT,
    agent TEXT, model TEXT, status TEXT, tokens_in INTEGER, tokens_out INTEGER,
    cost_usd REAL, latency_ms REAL,
    pricing_source TEXT NOT NULL DEFAULT 'legacy_configured_fallback_rates',
    pricing_model TEXT
);
