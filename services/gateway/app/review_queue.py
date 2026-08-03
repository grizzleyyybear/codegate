"""SQLite-backed human-review queue (stdlib sqlite3, zero dependencies).

Replaces the flat reviews.json file: safe under concurrent writes (WAL),
stores the intent prompt properly, and keeps decided items with their
status instead of silently dropping them.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone


def _db_path() -> str:
    return os.environ.get("REVIEW_QUEUE_DB", "/work/reviews.db")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reviews (
            intent_id    TEXT PRIMARY KEY,
            repo         TEXT NOT NULL,
            prompt       TEXT NOT NULL DEFAULT '',
            diff         TEXT NOT NULL,
            confidence   REAL NOT NULL,
            reason       TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            decided_at   TEXT
        )"""
    )
    return conn


def enqueue(
    intent_id: str,
    repo: str,
    prompt: str,
    diff: str,
    confidence: float,
    reason: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO reviews
               (intent_id, repo, prompt, diff, confidence, reason, status, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
               ON CONFLICT(intent_id) DO UPDATE SET
                 repo=excluded.repo, prompt=excluded.prompt, diff=excluded.diff,
                 confidence=excluded.confidence, reason=excluded.reason,
                 status='pending', submitted_at=excluded.submitted_at,
                 decided_at=NULL""",
            (
                intent_id,
                repo,
                prompt,
                diff,
                confidence,
                reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def list_pending() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE status = 'pending' ORDER BY submitted_at"
        ).fetchall()
    return [dict(r) for r in rows]


def get(intent_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM reviews WHERE intent_id = ?", (intent_id,)
        ).fetchone()
    return dict(row) if row else None


def decide(intent_id: str, approve: bool) -> dict | None:
    """Marks a pending review approved/rejected. Returns the item, or
    None if it doesn't exist."""
    status = "approved" if approve else "rejected"
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE reviews SET status = ?, decided_at = ?
               WHERE intent_id = ? AND status = 'pending'""",
            (status, datetime.now(timezone.utc).isoformat(), intent_id),
        )
        if cur.rowcount == 0 and not get(intent_id):
            return None
    return get(intent_id)
