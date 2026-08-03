"""Persistent task memory: every finished pipeline run is recorded and
mined for lessons when planning new tasks.

This is what turns the fixed pipeline into something that learns:
"the last time someone asked for rate limiting here, the patch failed
tests twice before escalation fixed it" is context the planner gets for
free on the next similar intent. Storage is SQLite on the shared /work
volume (stdlib only, no new deps).
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone

_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{2,}")


def _db_path() -> str:
    return os.environ.get("AGENT_MEMORY_DB", "/work/agent_memory.db")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS task_memory (
            intent_id   TEXT PRIMARY KEY,
            repo        TEXT NOT NULL,
            prompt      TEXT NOT NULL,
            action      TEXT NOT NULL,
            confidence  REAL NOT NULL,
            attempts    INTEGER NOT NULL DEFAULT 1,
            reasoning   TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL
        )"""
    )
    return conn


def record_outcome(
    intent_id: str,
    repo: str,
    prompt: str,
    action: str,
    confidence: float,
    attempts: int = 1,
    reasoning: str = "",
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO task_memory
               (intent_id, repo, prompt, action, confidence, attempts, reasoning, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(intent_id) DO UPDATE SET
                 action=excluded.action, confidence=excluded.confidence,
                 attempts=excluded.attempts, reasoning=excluded.reasoning""",
            (intent_id, repo, prompt, action, confidence, attempts, reasoning,
             datetime.now(timezone.utc).isoformat()),
        )


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def similar_tasks(prompt: str, repo: str, k: int = 3) -> list[dict]:
    """Past tasks ranked by keyword overlap with the new prompt (same repo
    first). Cheap Jaccard-ish scoring — no embeddings needed for a memory
    of hundreds of tasks."""
    query = _tokens(prompt)
    if not query:
        return []
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM task_memory ORDER BY created_at DESC LIMIT 500"
        ).fetchall()]
    scored = []
    for row in rows:
        overlap = len(query & _tokens(row["prompt"]))
        if overlap == 0:
            continue
        score = overlap / len(query | _tokens(row["prompt"]))
        if row["repo"] == repo:
            score *= 2
        scored.append((score, row))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [row for _, row in scored[:k]]


def lessons_for(prompt: str, repo: str) -> str:
    """Human-readable lessons block for the planner prompt. Empty string
    when memory has nothing relevant."""
    matches = similar_tasks(prompt, repo)
    if not matches:
        return ""
    lines = []
    for m in matches:
        outcome = {
            "auto_merge": "succeeded and auto-merged",
            "human_review": "needed human review",
            "reject": "was rejected",
            "human_approved": "was approved by a human reviewer",
            "human_rejected": "was rejected by a human reviewer",
        }.get(m["action"], m["action"])
        line = f"- A similar past task ({m['prompt'][:100]!r}) {outcome}"
        if m["attempts"] > 1:
            line += f" after {m['attempts']} attempts"
        if m["reasoning"]:
            line += f"; reviewer noted: {m['reasoning'][:150]}"
        lines.append(line)
    return "Lessons from past similar tasks in this codebase:\n" + "\n".join(lines)
