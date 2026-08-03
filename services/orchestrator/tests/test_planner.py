import asyncio
from types import SimpleNamespace

from app.agents import planner

from shared.schemas import IntentRequest, RetrievedChunk


def test_parse_steps_valid():
    raw = '[{"description": "add login", "target_files": ["auth.py", 42]}, "junk", {"description": ""}]'
    steps = planner._parse_steps(raw)
    assert len(steps) == 1
    assert steps[0].step_id == "1"
    assert steps[0].description == "add login"
    assert steps[0].target_files == ["auth.py"]


def test_parse_steps_invalid_json():
    assert planner._parse_steps("[oops") == []


def test_parse_steps_no_array():
    assert planner._parse_steps("no json here at all") == []


class FakePlanner:
    def __init__(self, text=None, exc=None):
        self.text = text
        self.exc = exc
        self.prompt = None

    async def complete(self, prompt, system=None, temperature=0.3):
        self.prompt = prompt
        if self.exc:
            raise self.exc
        return SimpleNamespace(text=self.text, model="m", prompt_tokens=0, completion_tokens=0, latency_ms=1.0)


def _state(context=None):
    intent = IntentRequest(intent_id="i1", repo="r", prompt="add rate limiting", submitted_by="u")
    return {"intent": intent, "context": context or []}


def test_plan_steps_uses_llm(monkeypatch):
    fake = FakePlanner('[{"description": "add login", "target_files": ["auth.py"]}]')
    monkeypatch.setattr(planner, "get_client", lambda model: fake)
    out = asyncio.run(planner.plan_steps(_state()))
    assert out["plan"].intent_id == "i1"
    assert out["plan"].steps[0].description == "add login"
    assert "add rate limiting" in fake.prompt


def test_plan_steps_falls_back_on_exception(monkeypatch):
    fake = FakePlanner(exc=RuntimeError("network down"))
    monkeypatch.setattr(planner, "get_client", lambda model: fake)
    out = asyncio.run(planner.plan_steps(_state()))
    assert len(out["plan"].steps) == 1
    assert out["plan"].steps[0].description == "add rate limiting"
    assert out["plan"].steps[0].target_files == []


def test_plan_steps_falls_back_on_unparsable(monkeypatch):
    fake = FakePlanner("I have no idea")
    monkeypatch.setattr(planner, "get_client", lambda model: fake)
    out = asyncio.run(planner.plan_steps(_state()))
    assert len(out["plan"].steps) == 1


def test_plan_steps_includes_context(monkeypatch):
    fake = FakePlanner('[{"description": "step one", "target_files": ["a.py"]}]')
    monkeypatch.setattr(planner, "get_client", lambda model: fake)
    context = [
        {"file_path": "src/a.py", "content": "code here", "similarity": 0.9},
        {"file_path": "src/b.py", "content": "more code", "similarity": 0.8},
    ]
    out = asyncio.run(planner.plan_steps(_state(context)))
    assert "src/a.py" in fake.prompt
    assert out["plan"].context == [
        RetrievedChunk(file_path="src/a.py", content="code here", similarity=0.9),
        RetrievedChunk(file_path="src/b.py", content="more code", similarity=0.8),
    ]
