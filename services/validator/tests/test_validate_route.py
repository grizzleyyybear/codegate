from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

_PATCH = {
    "intent_id": "i1",
    "repo": "r",
    "diff": "--- a/x\n+++ b/x\n",
    "model_used": "m",
    "prompt_tokens": 1,
    "completion_tokens": 1,
}


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_validate_route(monkeypatch):
    async def fake_score_patch(patch):
        return {
            "intent_id": patch.intent_id,
            "static_analysis_passed": True,
            "tests_passed": True,
            "test_output": "3 passed",
            "llm_judge_score": 0.8,
            "llm_judge_reasoning": "looks good",
            "confidence": 0.85,
        }

    monkeypatch.setattr("app.main.score_patch", fake_score_patch)
    resp = client.post("/validate", json=_PATCH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["confidence"] == 0.85
    assert body["test_output"] == "3 passed"
