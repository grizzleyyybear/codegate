import asyncio

import httpx
from app.agents.router import parse_intent, retrieve_context, scope_intent

from shared.schemas import IntentRequest


def test_scope_intent_matches_keywords():
    assert "auth" in scope_intent("add token validation to the login flow")
    assert "database" in scope_intent("fix the sql query in the schema migration")
    assert "tests" in scope_intent("write pytest coverage for the endpoint")
    assert "ui" in scope_intent("add a button to the settings page")


def test_scope_intent_no_match():
    assert scope_intent("bake a cake") == []


def test_parse_intent_sets_scopes_and_query():
    intent = IntentRequest(intent_id="i", repo="r", prompt="fix the auth token endpoint", submitted_by="u")
    out = asyncio.run(parse_intent({"intent": intent}))
    assert set(out["scopes"]) == {"auth", "api"}
    assert "auth, api" in out["retrieval_query"]


def test_parse_intent_no_scopes_keeps_prompt():
    intent = IntentRequest(intent_id="i", repo="r", prompt="unrelated task", submitted_by="u")
    out = asyncio.run(parse_intent({"intent": intent}))
    assert out["scopes"] == []
    assert out["retrieval_query"] == "unrelated task"


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeAClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(self.payload)


def test_retrieve_context(monkeypatch):
    chunks = [{"file_path": "a.py", "content": "x", "similarity": 0.9}]
    fake = FakeAClient({"chunks": chunks})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: fake)
    intent = IntentRequest(intent_id="i", repo="r", prompt="p", submitted_by="u")
    out = asyncio.run(retrieve_context({"intent": intent, "retrieval_query": "query here"}))
    assert out["context"] == chunks
    assert fake.calls[0]["url"] == "http://retrieval:8002/retrieve"
    assert fake.calls[0]["json"] == {"repo": "r", "query": "query here", "top_k": 8}


def test_retrieve_context_defaults_query_to_prompt(monkeypatch):
    fake = FakeAClient({"chunks": []})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: fake)
    intent = IntentRequest(intent_id="i", repo="r", prompt="p", submitted_by="u")
    asyncio.run(retrieve_context({"intent": intent}))
    assert fake.calls[0]["json"]["query"] == "p"
