"""LangGraph definition for the orchestrator.

No longer a fixed chain — the graph routes dynamically:

    parse_intent -> retrieve_context -+-> research <-> (loop while weak)
                                      |        |        |
                                      |        +--------+ (bounded)
                                      +-> plan_steps -> END

research is a sub-agent spawned only when retrieval is weak, and the
graph loops back into it while the context stays weak (bounded by
MAX_RESEARCH_ROUNDS) — iterative deepening, not a single blind pass.

plan_steps also consumes persistent task memory (lessons from similar
past runs) and, on a replan, the validator's failure feedback — so the
goal can be re-formulated mid-task instead of blindly retried.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from shared.schemas import IntentRequest, Plan, RetrievedChunk

from .agents.planner import plan_steps
from .agents.researcher import (
    MAX_RESEARCH_ROUNDS,
    needs_research,
    research_context,
)
from .agents.router import parse_intent, retrieve_context


class OrchestratorState(TypedDict, total=False):
    intent: IntentRequest
    context: list[RetrievedChunk]
    plan: Plan
    scopes: list[str]
    retrieval_query: str
    feedback: str  # validator failure output on a replan
    research_depth: int  # research rounds already run (iterative deepening)


def _after_research(state: dict) -> str:
    """Loop back into research while the context is still weak, but never
    more than MAX_RESEARCH_ROUNDS times — after that, plan on what we
    have rather than spinning forever."""
    if (
        needs_research(state)
        and int(state.get("research_depth", 0)) < MAX_RESEARCH_ROUNDS
    ):
        return "research"
    return "plan_steps"


def build_orchestration_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("research", research_context)
    graph.add_node("plan_steps", plan_steps)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "retrieve_context")
    # dynamic routing: spawn the research sub-agent only when the first
    # retrieval pass came back weak
    graph.add_conditional_edges(
        "retrieve_context",
        lambda state: "research" if needs_research(state) else "plan_steps",
        {"research": "research", "plan_steps": "plan_steps"},
    )
    # iterative deepening: keep researching while weak, bounded
    graph.add_conditional_edges(
        "research",
        _after_research,
        {"research": "research", "plan_steps": "plan_steps"},
    )
    graph.add_edge("plan_steps", END)

    return graph.compile()
