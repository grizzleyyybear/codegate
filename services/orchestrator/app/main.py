"""Orchestrator service.

Entry point for the pipeline. Takes an intent, runs it through the
orchestration graph (parse -> retrieve -> [research sub-agent if needed]
-> plan), and returns the Plan. On a replan request the validator's
failure feedback flows into the planner so the goal is re-formulated,
not just retried.

Also owns the persistent task memory: the gateway reports every finished
run to /outcome, and future plans for similar intents start with those
lessons.
"""
from fastapi import FastAPI

from shared.otel_setup import setup_otel
from shared.schemas import Plan, PlanRequest, TaskOutcome

from .agents import memory
from .graph import build_orchestration_graph

setup_otel("codegate-orchestrator")
app = FastAPI(title="Codegate Orchestrator")
graph = build_orchestration_graph()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/plan", response_model=Plan)
async def plan(req: PlanRequest) -> Plan:
    """Run the intent through the orchestration graph and return a Plan.
    With feedback set, the planner re-formulates the approach around the
    previous failure (mid-task replanning)."""
    state: dict = {"intent": req.intent}
    if req.feedback:
        state["feedback"] = req.feedback
    result = await graph.ainvoke(state)
    return result["plan"]


@app.post("/outcome")
def record_outcome(outcome: TaskOutcome) -> dict:
    """Persist how a run ended into task memory."""
    memory.record_outcome(
        intent_id=outcome.intent_id,
        repo=outcome.repo,
        prompt=outcome.prompt,
        action=outcome.action,
        confidence=outcome.confidence,
        attempts=outcome.attempts,
        reasoning=outcome.reasoning,
    )
    return {"recorded": True}
