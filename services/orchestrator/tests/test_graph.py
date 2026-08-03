import asyncio

import app.graph as g

from shared.schemas import IntentRequest, Plan, PlanStep


def test_graph_runs_all_nodes(monkeypatch):
    intent = IntentRequest(intent_id="i1", repo="r", prompt="p", submitted_by="u")

    async def fake_parse(state):
        state["scopes"] = []
        state["retrieval_query"] = state["intent"].prompt
        return state

    async def fake_retrieve(state):
        state["context"] = []
        return state

    async def fake_plan(state):
        state["plan"] = Plan(
            intent_id=state["intent"].intent_id,
            repo=state["intent"].repo,
            steps=[PlanStep(step_id="1", description="do it")],
            context=state.get("context", []),
        )
        return state

    monkeypatch.setattr(g, "parse_intent", fake_parse)
    monkeypatch.setattr(g, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(g, "plan_steps", fake_plan)

    graph = g.build_orchestration_graph()
    result = asyncio.run(graph.ainvoke({"intent": intent}))

    assert result["plan"].intent_id == "i1"
    assert result["plan"].steps[0].description == "do it"
    assert result["plan"].context == []
