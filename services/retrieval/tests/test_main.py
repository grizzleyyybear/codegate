from app.main import app
from fastapi.testclient import TestClient


def test_health():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_index_route(monkeypatch):
    async def fake_index(repo, repo_path):
        return 7

    monkeypatch.setattr("app.main.index_repository", fake_index)
    client = TestClient(app)
    resp = client.post("/index", json={"repo": "r", "repo_path": "/tmp/repo"})
    assert resp.status_code == 200
    assert resp.json() == {"repo": "r", "chunks_indexed": 7}


def test_retrieve_route(monkeypatch):
    async def fake_retrieve(repo, query, top_k):
        return []

    monkeypatch.setattr("app.main.retrieve_chunks", fake_retrieve)
    client = TestClient(app)
    resp = client.post("/retrieve", json={"repo": "r", "query": "q", "top_k": 4})
    assert resp.status_code == 200
    assert resp.json() == {"chunks": []}


def test_retrieve_route_default_top_k(monkeypatch):
    captured = {}

    async def fake_retrieve(repo, query, top_k):
        captured["top_k"] = top_k
        return []

    monkeypatch.setattr("app.main.retrieve_chunks", fake_retrieve)
    client = TestClient(app)
    client.post("/retrieve", json={"repo": "r", "query": "q"})
    assert captured["top_k"] == 8


def test_lifespan_ensures_schema(monkeypatch):
    called = []
    monkeypatch.setattr("app.main.ensure_schema", lambda: called.append(True))
    client = TestClient(app)
    with client:
        assert called == [True]
