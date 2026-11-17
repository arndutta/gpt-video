CREATE TABLE IF NOT EXISTS embedding_identity (id INTEGER PRIMARY KEY, identity TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS corpus (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS versions (
    collection TEXT NOT NULL, source_id TEXT NOT NULL, version TEXT NOT NULL,
    document_key TEXT NOT NULL UNIQUE, signature TEXT NOT NULL,
    chunk_count INTEGER NOT NULL, ready INTEGER NOT NULL DEFAULT 0,
    indexed_at TEXT, PRIMARY KEY(collection, source_id, version)
);

CREATE TABLE IF NOT EXISTS active_documents (
    collection TEXT NOT NULL, source_id TEXT NOT NULL, version TEXT NOT NULL,
    PRIMARY KEY(collection, source_id),
    FOREIGN KEY(collection, source_id, version) REFERENCES versions(collection, source_id, version)
);
