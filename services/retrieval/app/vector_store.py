"""pgvector-backed store. Reuses the same Postgres instance the stack
already runs — just adds the vector extension and one table.

Schema is bootstrapped by infra/db/init.sql on first postgres startup and
defensively re-ensured by ensure_schema() at retrieval-service startup.
"""
from __future__ import annotations

import os

import psycopg
from pgvector.psycopg import register_vector  # type: ignore[import-untyped]

SCHEMA_DDL = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS code_chunks (
        id SERIAL PRIMARY KEY,
        repo TEXT NOT NULL,
        file_path TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding VECTOR(384)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_code_chunks_repo ON code_chunks (repo)",
    """CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding
       ON code_chunks USING ivfflat (embedding vector_cosine_ops)""",
]


def get_conn():
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def ensure_schema() -> None:
    """Idempotent — safe to call on every startup."""
    with get_conn() as conn, conn.cursor() as cur:
        for stmt in SCHEMA_DDL:
            cur.execute(stmt)
        conn.commit()


def upsert_chunks(repo: str, rows: list[tuple[str, str, list[float]]]) -> int:
    """rows: list of (file_path, content, embedding). Re-indexing a repo
    replaces its previous chunks so repeated /index calls stay idempotent."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM code_chunks WHERE repo = %s", (repo,))
        cur.executemany(
            """
            INSERT INTO code_chunks (repo, file_path, content, embedding)
            VALUES (%s, %s, %s, %s)
            """,
            [(repo, fp, content, emb) for fp, content, emb in rows],
        )
        conn.commit()
    return len(rows)


def similarity_search(repo: str, query_embedding: list[float], top_k: int):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT file_path, content, 1 - (embedding <=> %s::vector) AS similarity
            FROM code_chunks
            WHERE repo = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_embedding, repo, query_embedding, top_k),
        )
        return cur.fetchall()
