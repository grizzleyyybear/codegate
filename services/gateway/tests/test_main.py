
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_intents_requires_api_key(monkeypatch):
    monkeypatch.setenv("GATEWAY_API_KEY", "sekret")
    body = {"intent_id": "i1", "repo": "r", "prompt": "p", "submitted_by": "u"}
    assert client.post("/intents", json=body).status_code == 401
    assert client.post("/intents", json=body, headers={"X-API-Key": "wrong"}).status_code == 401

    async def fake_run_pipeline(intent):
        return {"patch": {}, "validation": {}, "decision": {"action": "reject"}, "outcome": {"rejected": True}}

    monkeypatch.setattr("app.main.run_pipeline", fake_run_pipeline)
    resp = client.post("/intents", json=body, headers={"X-API-Key": "sekret"})
    assert resp.status_code == 200
    assert resp.json()["outcome"] == {"rejected": True}


def test_reviews_list_and_decide(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_QUEUE_DB", str(tmp_path / "reviews.db"))
    assert client.get("/reviews").json() == []

    from app import review_queue

    review_queue.enqueue("i2", "repo", "prompt", "diff", 0.6, "reason")
    assert client.get("/reviews").json()[0]["intent_id"] == "i2"

    resp = client.post("/reviews/i2", json={"approve": False})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    resp = client.post("/reviews/missing", json={"approve": True})
    assert resp.status_code == 404


def test_review_approve_merges(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_QUEUE_DB", str(tmp_path / "reviews.db"))
    monkeypatch.setenv("GATEWAY_API_KEY", "sekret")

    from app import review_queue

    review_queue.enqueue("i3", "repo", "prompt", "diff", 0.8, "reason")

    def fake_auto_merge(patch):
        assert patch["intent_id"] == "i3"
        assert patch["model_used"] == "human-approved"
        return {"merged": True, "detail": "committed"}

    monkeypatch.setattr("app.main._auto_merge", fake_auto_merge)
    resp = client.post("/reviews/i3", json={"approve": True}, headers={"X-API-Key": "sekret"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["merge"]["merged"] is True
