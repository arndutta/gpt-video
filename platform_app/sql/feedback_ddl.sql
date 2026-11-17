CREATE TABLE IF NOT EXISTS realized_outcomes(
  item_id TEXT PRIMARY KEY, sku TEXT NOT NULL, run_id TEXT NOT NULL,
  status TEXT NOT NULL, result TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS learning_versions(
  sku TEXT NOT NULL, version INTEGER NOT NULL, source_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL, state TEXT NOT NULL,
  PRIMARY KEY(sku,version));

CREATE TRIGGER IF NOT EXISTS learning_no_update BEFORE UPDATE ON learning_versions
  BEGIN SELECT RAISE(ABORT,'Learning versions are immutable'); END;

CREATE TRIGGER IF NOT EXISTS learning_no_delete BEFORE DELETE ON learning_versions
  BEGIN SELECT RAISE(ABORT,'Learning versions are immutable'); END;

CREATE TABLE IF NOT EXISTS observed_days(
  sku TEXT NOT NULL, day TEXT NOT NULL, item_id TEXT NOT NULL,
  PRIMARY KEY(sku,day));
