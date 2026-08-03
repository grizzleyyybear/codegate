from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

_PATCH = {
    "intent_id": "i1",
    "repo": "",
    "diff": "--- a/foo.py\n+++ b/foo.py\n",
    "model_used": "m",
    "prompt_tokens": 0,
    "completion_tokens": 0,
}


def _validation(confidence=0.9):
    return {
        "intent_id": "i1",
        "static_analysis_passed": True,
        "tests_passed": True,
        "test_output": "",
        "llm_judge_score": confidence,
        "llm_judge_reasoning": "",
        "confidence": confidence,
    }


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_decide_auto_merge():
    resp = client.post("/decide", json={"patch": _PATCH, "validation": _validation(0.95)})
    assert resp.status_code == 200
    assert resp.json()["action"] == "auto_merge"


def test_decide_human_review_for_sensitive_path():
    patch = dict(_PATCH, diff="--- a/auth/login.py\n+++ b/auth/login.py\n")
    resp = client.post("/decide", json={"patch": patch, "validation": _validation(0.99)})
    assert resp.json()["action"] == "human_review"
    assert resp.json()["touches_sensitive_path"] is True


def test_decide_reject_low_confidence():
    resp = client.post("/decide", json={"patch": _PATCH, "validation": _validation(0.2)})
    assert resp.json()["action"] == "reject"
