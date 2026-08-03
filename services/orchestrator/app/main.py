"""Orchestrator service.

Entry point for the pipeline. Takes an IntentRequest, runs it through the
LangGraph orchestration graph (parse -> retrieve context -> plan steps),
and hands the resulting Plan to the gateway to route to codegen.

This is the "build and orchestrate multi-agent AI systems" piece of the
JD, made concrete.
"""
from fastapi import FastAPI

from shared.otel_setup import setup_otel
from shared.schemas import IntentRequest, Plan

from .graph import build_orchestration_graph

setup_otel("codegate-orchestrator")
app = FastAPI(title="Codegate Orchestrator")
graph = build_orchestration_graph()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/plan", response_model=Plan)
async def plan(intent: IntentRequest) -> Plan:
    """Run the intent through the orchestration graph and return a Plan."""
    result = await graph.ainvoke({"intent": intent})
    return result["plan"]
