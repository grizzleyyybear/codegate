"""Research sub-agent: spawned dynamically when the first retrieval pass
comes back weak.

This is the "sub-agent spawning" piece: the graph doesn't always run the
same nodes — a conditional edge decides at runtime whether to spawn this
agent, which uses an LLM to reformulate the search from different angles
and merges what it finds into the grounding context.
"""
from __future__ import annotations

import json
import os
import re

import httpx

from shared.llm_clients import get_client

RETRIEVAL_URL = os.environ.get("RETRIEVAL_URL", "http://retrieval:8002")

# below this best-similarity the first-pass context is considered weak
RESEARCH_SIMILARITY_FLOOR = float(os.environ.get("RESEARCH_SIMILARITY_FLOOR", "0.55"))
MAX_RESEARCH_QUERIES = int(os.environ.get("MAX_RESEARCH_QUERIES", "3"))
# how many research rounds the graph may loop before forcing a plan —
# the loop is bounded so a hopeless task cannot spin forever
MAX_RESEARCH_ROUNDS = int(os.environ.get("MAX_RESEARCH_ROUNDS", "2"))

RESEARCHER_SYSTEM = """You are a code-search agent. The first search for
context in a repository came back weak for the given task. Propose up to
{n} alternative search queries that approach the task from different
angles (synonyms, likely file names, related subsystems, framework
terminology).

Reply with exactly one JSON array of strings, nothing else:
["query one", "query two"]"""

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _as_dicts(context: list) -> list[dict]:
    """Context chunks may be plain dicts (as retrieval returns them) or
    RetrievedChunk models (as tests construct them) — normalize."""
    return [c if isinstance(c, dict) else c.model_dump() for c in context]


def needs_research(state: dict) -> bool:
    context = _as_dicts(state.get("context", []))
    if not context:
        return True
    best = max((c.get("similarity", 0.0) for c in context), default=0.0)
    return best < RESEARCH_SIMILARITY_FLOOR


def parse_queries(raw: str) -> list[str]:
    match = _JSON_ARRAY_RE.search(raw)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [q.strip() for q in items if isinstance(q, str) and q.strip()][:MAX_RESEARCH_QUERIES]


async def research_context(state: dict) -> dict:
    """Sub-agent node: reformulate the search, run the extra queries, and
    merge deduplicated chunks into state["context"]. Best-effort — any
    failure leaves the original context untouched."""
    intent = state["intent"]
    context = _as_dicts(state.get("context", []))
    # one round of iterative deepening: the graph may route back here up
    # to MAX_RESEARCH_ROUNDS times while the context stays weak
    state["research_depth"] = int(state.get("research_depth", 0)) + 1
    try:
        client = get_client("planner")
        found = ", ".join(sorted({c["file_path"] for c in context})) or "nothing"
        response = await client.complete(
            prompt=f"Task: {intent.prompt}\nFirst search found: {found}",
            system=RESEARCHER_SYSTEM.format(n=MAX_RESEARCH_QUERIES),
        )
        queries = parse_queries(response.text)

        seen = {(c["file_path"], c["content"][:80]) for c in context}
        async with httpx.AsyncClient() as http:
            for query in queries:
                resp = await http.post(
                    f"{RETRIEVAL_URL}/retrieve",
                    json={"repo": intent.repo, "query": query, "top_k": 4},
                    timeout=120,
                )
                resp.raise_for_status()
                for chunk in resp.json()["chunks"]:
                    key = (chunk["file_path"], chunk["content"][:80])
                    if key not in seen:
                        seen.add(key)
                        context.append(chunk)
    except Exception:  # noqa: BLE001 — research is opportunistic, never fatal
        return state
    state["context"] = context
    return state
