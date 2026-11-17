-- External market observations are independent of the Commerce system of record.
CREATE TABLE IF NOT EXISTS market_metadata (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS competitor_quotes (
    sku TEXT NOT NULL, competitor TEXT NOT NULL,
    price TEXT NOT NULL CHECK(CAST(price AS REAL) > 0),
    observed_at TEXT NOT NULL,
    PRIMARY KEY (sku, competitor)
);
CREATE INDEX IF NOT EXISTS competitor_observed ON competitor_quotes(observed_at);
