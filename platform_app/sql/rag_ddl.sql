-- Chunk bodies, source metadata and float64 vectors share the retrieval manifest DB.
CREATE TABLE IF NOT EXISTS rag_collections (
    name TEXT PRIMARY KEY, dimensions INTEGER NOT NULL CHECK(dimensions > 0)
);
CREATE TABLE IF NOT EXISTS rag_chunks (
    collection TEXT NOT NULL REFERENCES rag_collections(name),
    id TEXT NOT NULL, document_key TEXT NOT NULL,
    source_id TEXT NOT NULL, version TEXT NOT NULL, title TEXT NOT NULL,
    content_hash TEXT NOT NULL, chunk_index INTEGER NOT NULL CHECK(chunk_index >= 0),
    start_char INTEGER NOT NULL CHECK(start_char >= 0),
    end_char INTEGER NOT NULL CHECK(end_char > start_char),
    source_uri TEXT, document TEXT NOT NULL,
    embedding BLOB NOT NULL CHECK(length(embedding) > 0 AND length(embedding) % 8 = 0),
    PRIMARY KEY(collection, id)
);
CREATE INDEX IF NOT EXISTS rag_chunks_document ON rag_chunks(collection, document_key);
CREATE TABLE IF NOT EXISTS rag_migrations (
    name TEXT PRIMARY KEY, completed_at TEXT NOT NULL, chunks INTEGER NOT NULL
);
