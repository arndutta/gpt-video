# SQLite data installation

The application reads business data from SQLite. Python includes the SQLite driver;
no database server or additional database dependency is required.

From the repository root, install the schema and initial data:

```sh
.venv/bin/python -m scripts.database
./startup.sh
```

The installer preserves an existing catalog, price versions, sales, runs, approvals,
policies, and edited model rates. Only an empty catalog receives the reproducible
500-SKU, 180-day synthetic dataset. The report lists every installed table and row
count and checks database integrity and foreign keys. Installation does not interrupt
active runs or change execution authorization. Normal application startup still applies
its existing restart fences and switches execution to supervised mode.

To install into another directory, or create tables without generating catalog data:

```sh
.venv/bin/python -m scripts.database --data-dir data/demo --sku-count 100 --days 90 --as-of 2026-11-17
.venv/bin/python -m scripts.database --data-dir data/empty --schema-only
.venv/bin/python -m scripts.database status
```

Set `DATA_DIR` when launching the app to use a different directory. Installation also
honors `DATA_DIR` when `--data-dir` is omitted. As before, the launcher passes the
corresponding Commerce database path to the Commerce service.

| Database | Saved records |
|---|---|
| `commerce.db` | Products, current prices and versions, inventory, sales, price history, batch receipts, evaluator truth, dataset metadata |
| `market.db` | Competitor quotes and one-time migration metadata |
| `app.db` | Runs, audit events, recommendation revisions and approvals, dispatch outbox, policies, feedback and learning, scenarios, loop history, grounding upload jobs, A2A mappings, model usage and model pricing rates |
| `llm_cache.db` | Response cache and cache counters |
| `rag.db` | Grounding documents, chunks, embedding vectors, collection dimensions, source/version manifests, citations, and migration metadata |

Grounding stores both its text and vectors in SQLite and computes cosine similarity
locally when retrieving evidence. The installer creates its schema without selecting
an embedding model; the first configured store records the embedding identity. The
workflow also persists SQLite checkpoints. Operational telemetry remains
an allowlisted JSONL log. Browser theme preferences remain browser settings.

## DDL and DML

The runtime executes the same packaged SQL assets used by installation:

- `commerce/sql/schema.sql`: Commerce table definitions, constraints, and indexes.
- `commerce/sql/seed.sql`: named, parameterized INSERT statements used by the data generator.
- `commerce/sql/market_schema.sql` and `market_seed.sql`: competitor quote schema and INSERT DML.
- `platform_app/sql/*_ddl.sql`: platform, governance, feedback, uploads, loops, scenarios,
  discovery, usage, cache, grounding manifest, SQLite retrieval, and model pricing schemas.
- `platform_app/sql/*_dml.sql`: initial policy, schema/cache/corpus metadata, attributed
  model pricing rates, and provenance.

Catalog generation binds values to parameterized DML inside a transaction. Model
rates are installed once and subsequently read from `app.db`; restarting does not
overwrite SQL edits or restore deliberately deleted rates. Unrecognized models use
the configured fallback rates, as before. The included rates retain their original
source and retrieval timestamp; installation does not refresh prices from the internet.

Competitor quotes are read from `market.db` for every request. An existing
`competitor_feed.json` is imported once when initializing the market database and is
then ignored. Existing SQLite quotes take precedence. New seeding creates no JSON
data sidecars. Offline evaluation tools read `evaluation_truth` from Commerce SQLite.

To remove the two obsolete data copies after installation:

```sh
.venv/bin/python -m scripts.database cleanup-legacy
```

Cleanup imports the legacy competitor feed when needed, then compares all its quotes
with `market.db` and all evaluator values with `commerce.db`. It removes only
`competitor_feed.json` and `evaluation_truth.json`, and only when both existing files
match their saved SQLite data. A mismatch or malformed file stops cleanup without
removing either file. Reports, model/tokenizer metadata, package files, and other JSON
files remain in place.

Stop the application before the first legacy RAG migration. The installer migrates an existing Chroma grounding store into `rag.db` before creating
an empty retrieval store. Existing source versions, citations, document text, vectors,
and embedding identity are preserved and verified. The legacy store remains available
as a migration source; it is no longer used for retrieval. To migrate it separately:

```sh
.venv/bin/python -m scripts.rag migrate
```

Normal SQLite retrieval and local ONNX inference do not require Chroma. If migrating
on a fresh environment that lacks the legacy reader, install the optional pinned
`requirements-legacy-rag.lock` first. `requirements.lock` contains the normal runtime
dependencies. SQLite uses exact cosine search over the active chunks; retrieval time
therefore grows with the number of stored active chunks.

The platform continues to read authoritative catalog, inventory, sales and prices
through Commerce HTTP. The independent market database is the external feed adapter;
the platform never opens `commerce.db` directly.

## Export installed data as SQL

```sh
.venv/bin/python -m scripts.database --export-dir data/sql
```

This creates `commerce.sql`, `market.sql`, `app.sql`, `llm_cache.sql`, and `rag.sql`, each containing
replayable CREATE statements and INSERT statements for the saved rows. Existing exports
in that directory are replaced. Each export uses a consistent SQLite read transaction,
including committed WAL data. Restore each file into a separate, empty SQLite database.
Exports preserve floating-point values exactly, binary data, embedded NULs, immutable
audit triggers, foreign keys, and AUTOINCREMENT sequence state. Files are replaced only
after each database export finishes successfully.
These five exports include grounding text, vectors, and manifests. They do not include
workflow checkpoints, downloaded model files, or operational logs; retain those
separately for a workspace backup.

To deliberately replace synthetic Commerce data, the existing explicit reset command
is still available:

```sh
.venv/bin/python -m commerce.seed --data-dir data/demo --reset
```

Reset replaces that directory's Commerce catalog and market quotes. Validation happens
before catalog changes. Each database commits separately; an I/O failure between the two
commits can require rerunning the explicit reset after fixing storage. The ordinary
installer never resets a populated database.
