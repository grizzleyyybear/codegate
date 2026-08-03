"""Anthropic-specific request/response shaping, kept separate from the
common LLMClient interface in shared/llm_clients.py so provider-specific
quirks (tool use, prompt caching) don't leak into the agent logic."""
