from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_plan_route(monkeypatch):
    class FakeGraph:
        async def ainvoke(self, state):
            return {
                "plan": {
                    "intent_id": "i1",
                    "repo": "r",
                    "steps": [{"step_id": "1", "description": "d", "target_files": []}],
                    "context": [],
                }
            }

    monkeypatch.setattr("app.main.graph", FakeGraph())
    resp = client.post(
        "/plan",
        json={"intent": {"intent_id": "i1", "repo": "r", "prompt": "p", "submitted_by": "u"}},
    )
    assert resp.status_code == 200
    assert resp.json()["intent_id"] == "i1"
    assert resp.json()["steps"][0]["description"] == "d"


def test_plan_route_passes_feedback(monkeypatch):
    seen = {}

    class FakeGraph:
        async def ainvoke(self, state):
            seen["state"] = state
            return {
                "plan": {
                    "intent_id": "i1",
                    "repo": "r",
                    "steps": [{"step_id": "1", "description": "d", "target_files": []}],
                    "context": [],
                }
            }

    monkeypatch.setattr("app.main.graph", FakeGraph())
    resp = client.post(
        "/plan",
        json={
            "intent": {"intent_id": "i1", "repo": "r", "prompt": "p", "submitted_by": "u"},
            "feedback": "Tests FAILED",
        },
    )
    assert resp.status_code == 200
    assert seen["state"]["feedback"] == "Tests FAILED"


def test_outcome_records_to_memory(monkeypatch):
    recorded = {}

    def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr("app.main.memory.record_outcome", fake_record)
    resp = client.post(
        "/outcome",
        json={
            "intent_id": "i9",
            "repo": "r",
            "prompt": "p",
            "action": "human_approved",
            "confidence": 0.8,
            "attempts": 2,
            "reasoning": "reviewer liked it",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"recorded": True}
    assert recorded["intent_id"] == "i9"
    assert recorded["action"] == "human_approved"
    assert recorded["reasoning"] == "reviewer liked it"
