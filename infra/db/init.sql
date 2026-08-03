-- Bootstraps the pgvector schema once when the postgres container first
-- initializes (docker-entrypoint-initdb.d). Idempotent guards keep it safe
-- to re-run against an existing database.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS code_chunks (
    id SERIAL PRIMARY KEY,
    repo TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(384)
);

CREATE INDEX IF NOT EXISTS idx_code_chunks_repo ON code_chunks (repo);
CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding
    ON code_chunks USING ivfflat (embedding vector_cosine_ops);
