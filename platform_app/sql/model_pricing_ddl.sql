-- Local attributed token rates; initialize once and edit through SQLite thereafter.
CREATE TABLE IF NOT EXISTS model_pricing_schema (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_pricing_provenance (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_pricing (
    model TEXT PRIMARY KEY,
    input_cost_per_token REAL NOT NULL CHECK(input_cost_per_token >= 0),
    output_cost_per_token REAL NOT NULL CHECK(output_cost_per_token >= 0),
    cache_read_input_token_cost REAL CHECK(cache_read_input_token_cost >= 0),
    input_cost_per_token_above_200k_tokens REAL CHECK(input_cost_per_token_above_200k_tokens >= 0),
    output_cost_per_token_above_200k_tokens REAL CHECK(output_cost_per_token_above_200k_tokens >= 0),
    cache_read_input_token_cost_above_200k_tokens REAL CHECK(cache_read_input_token_cost_above_200k_tokens >= 0)
);
