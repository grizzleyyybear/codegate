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
        json={"intent_id": "i1", "repo": "r", "prompt": "p", "submitted_by": "u"},
    )
    assert resp.status_code == 200
    assert resp.json()["intent_id"] == "i1"
    assert resp.json()["steps"][0]["description"] == "d"
