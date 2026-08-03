"""LangGraph definition for the orchestrator.

Nodes: parse_intent -> retrieve_context -> plan_steps

parse_intent    figures out which files/subsystems the prompt touches
retrieve_context  calls the retrieval service for grounding chunks
plan_steps      breaks the intent into ordered PlanSteps for codegen

Wire each node to the retrieval service via httpx once that service is up.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from shared.schemas import IntentRequest, Plan, RetrievedChunk

from .agents.planner import plan_steps
from .agents.router import parse_intent, retrieve_context


class OrchestratorState(TypedDict):
    intent: IntentRequest
    context: list[RetrievedChunk]
    plan: Plan


def build_orchestration_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("plan_steps", plan_steps)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "retrieve_context")
    graph.add_edge("retrieve_context", "plan_steps")
    graph.add_edge("plan_steps", END)

    return graph.compile()
