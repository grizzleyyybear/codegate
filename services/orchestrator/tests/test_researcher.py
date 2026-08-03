import asyncio

from app.agents import researcher

from shared.llm_clients import LLMResponse
from shared.schemas import IntentRequest, RetrievedChunk

INTENT = IntentRequest(intent_id="i1", repo="r", prompt="p", submitted_by="u")


def test_needs_research():
    assert researcher.needs_research({}) is True
    assert researcher.needs_research({"context": []}) is True
    weak = [{"file_path": "a.py", "content": "x", "similarity": 0.3}]
    assert researcher.needs_research({"context": weak}) is True
    strong = [{"file_path": "a.py", "content": "x", "similarity": 0.9}]
    assert researcher.needs_research({"context": strong}) is False
    # pydantic models work too
    model_context = [RetrievedChunk(file_path="a.py", content="x", similarity=0.3)]
    assert researcher.needs_research({"context": model_context}) is True


def test_parse_queries():
    assert researcher.parse_queries('["query one", "query two"]') == ["query one", "query two"]
    assert researcher.parse_queries("no json here") == []
    assert researcher.parse_queries("[not json") == []
    assert researcher.parse_queries('["ok", 42, "", "  ", null]') == ["ok"]
    long = '["a", "b", "c", "d", "e"]'
    assert len(researcher.parse_queries(long)) <= researcher.MAX_RESEARCH_QUERIES


def test_research_context_runs_queries_and_dedupes(monkeypatch):
    seen_urls = []

    class FakeResponse:
        def __init__(self, chunks):
            self._chunks = chunks

        def json(self):
            return {"chunks": self._chunks}

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, timeout=None):
            seen_urls.append((url, json))
            query = json["query"]
            if query == "auth":
                return FakeResponse(
                    [{"file_path": "new.py", "content": "n", "similarity": 0.8}]
                )
            return FakeResponse([])

    class FakeLLM:
        async def complete(self, prompt, system=None, temperature=0.3):
            return LLMResponse(
                text='["auth", "database"]', model="m", prompt_tokens=1,
                completion_tokens=1, latency_ms=1.0,
            )

    monkeypatch.setattr(researcher, "get_client", lambda role: FakeLLM())
    monkeypatch.setattr(researcher.httpx, "AsyncClient", FakeClient)
    state = {
        "intent": INTENT,
        "context": [{"file_path": "a.py", "content": "x", "similarity": 0.2}],
    }
    result = asyncio.run(researcher.research_context(state))

    assert result["research_depth"] == 1
    assert len(seen_urls) == 2
    assert seen_urls[0][0] == "http://retrieval:8002/retrieve"
    paths = {c["file_path"] for c in result["context"]}
    assert paths == {"a.py", "new.py"}
    # a second pass over the same chunk still dedupes
    state["context"] = result["context"]
    state["research_depth"] = 1
    result2 = asyncio.run(researcher.research_context(state))
    assert len(result2["context"]) == 2


def test_research_context_failure_keeps_context(monkeypatch):
    class Boom:
        async def complete(self, prompt, system=None, temperature=0.3):
            raise RuntimeError("llm down")

    monkeypatch.setattr(researcher, "get_client", lambda role: Boom())
    state = {"intent": INTENT, "context": [{"file_path": "a.py", "content": "x", "similarity": 0.2}]}
    result = asyncio.run(researcher.research_context(state))
    assert [c["file_path"] for c in result["context"]] == ["a.py"]
    assert result.get("research_depth") == 1
