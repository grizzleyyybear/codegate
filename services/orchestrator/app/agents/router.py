"""Nodes that figure out scope and pull grounding context.

parse_intent      cheap heuristic pass: which subsystem/files does this touch
retrieve_context  calls the retrieval service's /retrieve endpoint
"""
from __future__ import annotations

import re

import httpx

# keyword -> subsystem hints used to sharpen the retrieval query. Cheap
# heuristic on purpose: scoping doesn't need an LLM round-trip, and the
# planner (which does call an LLM) sees the retrieved context anyway.
_SCOPE_HINTS = {
    "auth": ["auth", "login", "token", "session", "password", "oauth"],
    "api": ["endpoint", "route", "api", "handler", "request", "response"],
    "database": ["database", "db", "migration", "schema", "query", "sql", "model"],
    "tests": ["test", "coverage", "pytest", "assert"],
    "config": ["config", "settings", "env", "environment"],
    "ui": ["ui", "frontend", "component", "page", "button", "form"],
}

_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]+")


def scope_intent(prompt: str) -> list[str]:
    words = {w.lower() for w in _WORD_RE.findall(prompt)}
    return [scope for scope, hints in _SCOPE_HINTS.items() if words & set(hints)]


async def parse_intent(state: dict) -> dict:
    intent = state["intent"]
    scopes = scope_intent(intent.prompt)
    state["scopes"] = scopes
    # sharpen the retrieval query with the detected subsystems
    state["retrieval_query"] = (
        f"{intent.prompt} ({', '.join(scopes)})" if scopes else intent.prompt
    )
    return state


async def retrieve_context(state: dict) -> dict:
    intent = state["intent"]
    query = state.get("retrieval_query", intent.prompt)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://retrieval:8002/retrieve",
            json={"repo": intent.repo, "query": query, "top_k": 8},
            timeout=30,
        )
        resp.raise_for_status()
        state["context"] = resp.json()["chunks"]
    return state
