from app.main import app
from fastapi.testclient import TestClient

from shared.schemas import CodePatch

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_generate_route(monkeypatch):
    fake = CodePatch(
        intent_id="i1",
        repo="r",
        diff="--- a/x\n+++ b/x\n",
        model_used="m",
        prompt_tokens=1,
        completion_tokens=2,
    )

    async def fake_generate(req, feedback=None, escalate=False):
        return fake

    monkeypatch.setattr("app.main.generate_patch", fake_generate)
    resp = client.post(
        "/generate",
        json={
            "plan": {
                "intent_id": "i1",
                "repo": "r",
                "steps": [{"step_id": "1", "description": "d", "target_files": []}],
                "context": [],
            },
            "feedback": None,
            "escalate": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent_id"] == "i1"
    assert body["diff"].startswith("--- a/x")
    assert body["prompt_tokens"] == 1
