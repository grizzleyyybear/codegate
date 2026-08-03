import asyncio

import app.graph as g

from shared.schemas import IntentRequest, Plan, PlanStep, RetrievedChunk


def test_graph_runs_all_nodes(monkeypatch):
    intent = IntentRequest(intent_id="i1", repo="r", prompt="p", submitted_by="u")

    async def fake_parse(state):
        state["scopes"] = []
        state["retrieval_query"] = state["intent"].prompt
        return state

    async def fake_retrieve(state):
        state["context"] = []
        return state

    async def fake_research(state):
        state["context"] = [
            RetrievedChunk(file_path="a.py", content="x", similarity=0.9)
        ]
        state["research_depth"] = 1
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
    monkeypatch.setattr(g, "research_context", fake_research)
    monkeypatch.setattr(g, "plan_steps", fake_plan)

    graph = g.build_orchestration_graph()
    result = asyncio.run(graph.ainvoke({"intent": intent}))

    assert result["plan"].intent_id == "i1"
    assert result["plan"].steps[0].description == "do it"
    assert result["plan"].context[0].file_path == "a.py"


def test_graph_deepens_research_until_context_strong(monkeypatch):
    """The research sub-agent is re-spawned while the context stays weak,
    and the graph stops looping once a round returns strong context."""
    monkeypatch.setenv("MAX_RESEARCH_ROUNDS", "3")
    intent = IntentRequest(intent_id="i2", repo="r", prompt="p", submitted_by="u")
    calls = []

    async def fake_parse(state):
        return state

    async def fake_retrieve(state):
        state["context"] = []
        return state

    async def fake_research(state):
        calls.append(1)
        sim = 0.3 if len(calls) == 1 else 0.9
        state["context"] = [
            RetrievedChunk(file_path="a.py", content="x", similarity=sim)
        ]
        state["research_depth"] = int(state.get("research_depth", 0)) + 1
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
    monkeypatch.setattr(g, "research_context", fake_research)
    monkeypatch.setattr(g, "plan_steps", fake_plan)

    graph = g.build_orchestration_graph()
    result = asyncio.run(graph.ainvoke({"intent": intent}))

    assert len(calls) == 2
    assert result["plan"].context[0].similarity == 0.9


def test_graph_research_loop_is_bounded(monkeypatch):
    """Hopeless context never loops forever: the graph plans on what it
    has once the research budget is spent."""
    monkeypatch.setenv("MAX_RESEARCH_ROUNDS", "2")
    intent = IntentRequest(intent_id="i3", repo="r", prompt="p", submitted_by="u")
    calls = []

    async def fake_parse(state):
        return state

    async def fake_retrieve(state):
        state["context"] = []
        return state

    async def fake_research(state):
        calls.append(1)
        state["context"] = [
            RetrievedChunk(file_path="a.py", content="x", similarity=0.1)
        ]
        state["research_depth"] = int(state.get("research_depth", 0)) + 1
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
    monkeypatch.setattr(g, "research_context", fake_research)
    monkeypatch.setattr(g, "plan_steps", fake_plan)

    graph = g.build_orchestration_graph()
    asyncio.run(graph.ainvoke({"intent": intent}))

    assert len(calls) == 2
