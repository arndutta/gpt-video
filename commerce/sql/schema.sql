CREATE TABLE IF NOT EXISTS schema_versions (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    family_id TEXT NOT NULL, size INTEGER NOT NULL CHECK(size > 0),
    currency TEXT NOT NULL, cost TEXT NOT NULL, map_price TEXT NOT NULL,
    min_price TEXT NOT NULL, max_price TEXT NOT NULL,
    max_change_pct REAL NOT NULL, minimum_margin_pct REAL NOT NULL,
    rounding_increment TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prices (
    sku TEXT PRIMARY KEY REFERENCES products(sku), current_price TEXT NOT NULL,
    price_version INTEGER NOT NULL CHECK(price_version > 0), updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT PRIMARY KEY REFERENCES products(sku), on_hand INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku),
    date TEXT NOT NULL, price TEXT NOT NULL, units INTEGER NOT NULL CHECK(units >= 0),
    promotion INTEGER NOT NULL, seasonal_index REAL NOT NULL,
    UNIQUE(sku, date)
);
CREATE INDEX IF NOT EXISTS sales_sku_date ON sales(sku, date);
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku),
    batch_key TEXT, prior_price TEXT NOT NULL, new_price TEXT NOT NULL,
    prior_version INTEGER NOT NULL, new_version INTEGER NOT NULL,
    actor TEXT NOT NULL, approval_kind TEXT NOT NULL, applied_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_sku ON price_history(sku, id);
CREATE TABLE IF NOT EXISTS batches (
    batch_key TEXT PRIMARY KEY, payload_digest TEXT NOT NULL,
    result_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_truth (
    sku TEXT PRIMARY KEY REFERENCES products(sku), elasticity REAL NOT NULL,
    baseline_demand REAL NOT NULL
);
