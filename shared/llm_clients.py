"""Thin, swappable wrappers around the model providers Codegen and the
Validator call. Every wrapper returns the same shape so the caller doesn't
care which model answered — that's what lets the codegen agent route
cheap-model-first, expensive-model-on-low-confidence.

Default provider: OpenRouter's free-tier models (https://openrouter.ai).
One free API key (OPENROUTER_API_KEY) gives access to several ":free"
models from different families, which is exactly what the escalation and
judge-independence stories need — the second-opinion judge and the
escalation model come from different model families than the default
codegen model, at zero cost.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


class LLMClient:
    """Common interface. One subclass per provider."""

    @property
    def name(self) -> str:
        return "base"

    async def complete(
        self, prompt: str, system: str | None = None, temperature: float = 0.3
    ) -> LLMResponse:
        raise NotImplementedError


class OpenAICompatClient(LLMClient):
    """Any OpenAI-compatible chat-completions endpoint (OpenRouter, Groq,
    Together, a self-hosted server...). Uses httpx, imported lazily so this
    module stays importable in services that never call an LLM.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = extra_headers or {}

    @property
    def name(self) -> str:
        return self.model

    async def complete(
        self, prompt: str, system: str | None = None, temperature: float = 0.3
    ) -> LLMResponse:
        import asyncio

        import httpx

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = dict(self.extra_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        start = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        latency_ms = (asyncio.get_event_loop().time() - start) * 1000

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return LLMResponse(
            text=choice["message"]["content"],
            model=data.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=round(latency_ms, 1),
        )


class OpenRouterClient(OpenAICompatClient):
    """OpenRouter with a free-tier model. Requires OPENROUTER_API_KEY
    (free signup, no card). The optional referer/title headers are what
    OpenRouter asks apps to send."""

    def __init__(self, model: str):
        super().__init__(
            model=model,
            base_url=os.environ.get(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ),
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            extra_headers={
                "HTTP-Referer": "https://github.com/codegate",
                "X-Title": "codegate",
            },
        )

    async def complete(
        self, prompt: str, system: str | None = None, temperature: float = 0.3
    ) -> LLMResponse:
        # fail fast with an actionable message instead of an opaque 401
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Get a free key at "
                "https://openrouter.ai (no card required) and add it to .env"
            )
        return await super().complete(prompt, system=system, temperature=temperature)


# Logical role -> OpenRouter free model. Different families on purpose:
# the judge must not share a family with the codegen default, and the
# escalation model should be a stronger reasoner than the default.
# These slugs were verified live against OpenRouter (2026-08): the older
# llama/gemini/deepseek :free endpoints are gone. Override any of these
# via env without touching code.
FREE_MODEL_ROUTES = {
    "codegen-default": os.environ.get(
        "CODEGEN_MODEL", "cohere/north-mini-code:free"
    ),
    "codegen-escalation": os.environ.get(
        "ESCALATION_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"
    ),
    "judge": os.environ.get("JUDGE_MODEL", "google/gemma-4-26b-a4b-it:free"),
    "planner": os.environ.get(
        "PLANNER_MODEL", "google/gemma-4-26b-a4b-it:free"
    ),
}


def get_client(model_name: str) -> LLMClient:
    """Resolve a logical role ("codegen-default", "judge", ...) or a raw
    OpenRouter model id to a client. Every route is a free-tier online
    model — no local Ollama, no paid keys."""
    model = FREE_MODEL_ROUTES.get(model_name, model_name)
    return OpenRouterClient(model=model)
