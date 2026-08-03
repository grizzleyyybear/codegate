"""API-key auth for the gateway's own endpoints (separate from GitHub
webhook signature verification in webhooks.py).

Enforcement is opt-in: if GATEWAY_API_KEY is unset/empty the check is a
no-op (local dev), and any request is accepted. Set it in .env to require
the X-API-Key header on /intents.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str | None = Header(default=None)):
    expected = os.environ.get("GATEWAY_API_KEY", "")
    if not expected:
        return  # auth disabled for local dev
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid API key")
