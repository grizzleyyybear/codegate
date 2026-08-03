import asyncio

import httpx
import pytest

from shared.llm_clients import (
    FREE_MODEL_ROUTES,
    LLMClient,
    LLMResponse,
    OpenAICompatClient,
    OpenRouterClient,
    get_client,
)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeAClient:
    """Replaces httpx.AsyncClient for the duration of one complete() call."""

    def __init__(self, payload, timeout=None):
        self.timeout = timeout
        self.payload = payload
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self.payload)


def _run(coro):
    return asyncio.run(coro)


def test_get_client_resolves_logical_route():
    client = get_client("judge")
    assert isinstance(client, OpenRouterClient)
    assert client.model == FREE_MODEL_ROUTES["judge"]


def test_get_client_passes_unknown_through():
    client = get_client("openai/gpt-4o:free")
    assert isinstance(client, OpenRouterClient)
    assert client.model == "openai/gpt-4o:free"


def test_openrouter_client_reads_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "http://router:8080/v1")
    client = OpenRouterClient(model="m")
    assert client.api_key == "sk-test"
    assert client.base_url == "http://router:8080/v1"


def test_openrouter_client_defaults_base_url(monkeypatch):
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    client = OpenRouterClient(model="m")
    assert client.base_url == "https://openrouter.ai/api/v1"


def test_complete_sends_expected_request(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAClient)
    client = OpenAICompatClient(model="m", base_url="http://x", api_key="k")
    fake = FakeAClient(
        {
            "choices": [{"message": {"content": "hi"}}],
            "model": "m",
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
        }
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: fake)

    response = _run(client.complete("hello", system="sys"))

    assert isinstance(response, LLMResponse)
    assert response.text == "hi"
    assert response.model == "m"
    assert response.prompt_tokens == 5
    assert response.completion_tokens == 7
    assert response.latency_ms >= 0

    call = fake.calls[0]
    assert call["url"] == "http://x/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer k"
    assert call["json"]["model"] == "m"
    assert call["json"]["temperature"] == 0.3
    assert call["json"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]


def test_complete_uses_default_temperature_and_no_system(monkeypatch):
    fake = FakeAClient({"choices": [{"message": {"content": "x"}}]})
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: fake)
    client = OpenAICompatClient(model="m", base_url="http://x")

    _run(client.complete("hi"))

    call = fake.calls[0]
    assert call["json"]["temperature"] == 0.3
    assert call["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert "Authorization" not in call["headers"]


def test_complete_missing_usage_defaults_to_zero(monkeypatch):
    fake = FakeAClient({"choices": [{"message": {"content": "x"}}]})
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: fake)
    client = OpenAICompatClient(model="m", base_url="http://x")

    response = _run(client.complete("hi"))

    assert response.prompt_tokens == 0
    assert response.completion_tokens == 0


def test_base_client_raises_not_implemented():
    client = LLMClient()
    with pytest.raises(NotImplementedError):
        _run(client.complete("hi"))
    assert client.name == "base"


def test_complete_propagates_http_error(monkeypatch):
    class Boom:
        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("POST", "http://x"),
                response=httpx.Response(500),
            )

    class FailingClient(FakeAClient):
        async def post(self, url, headers=None, json=None):
            self.calls.append({"url": url, "headers": headers, "json": json})
            return Boom()

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: FailingClient({}))
    client = OpenAICompatClient(model="m", base_url="http://x")
    with pytest.raises(httpx.HTTPStatusError):
        _run(client.complete("hi"))
