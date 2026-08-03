"""Receives GitHub webhook events (e.g. an issue labeled "codegate") and
turns them into an IntentRequest for the pipeline.

Signature verification is HMAC-SHA256 over the raw body against
GITHUB_WEBHOOK_SECRET (the standard X-Hub-Signature-256 scheme). If the
secret is unset the endpoint refuses events rather than accepting them
unverified.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Request

from shared.schemas import IntentRequest

from .pipeline import run_pipeline

router = APIRouter(prefix="/webhooks")

# only issues labeled with this trigger the pipeline
TRIGGER_LABEL = os.environ.get("CODEGATE_TRIGGER_LABEL", "codegate")


def verify_signature(body: bytes, signature_header: str | None, secret: str) -> bool:
    """Constant-time check of GitHub's X-Hub-Signature-256 header."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)


def intent_from_issue_event(payload: dict) -> IntentRequest | None:
    """Maps an 'issues' event (opened/labeled with the trigger label) to
    an IntentRequest. Returns None for events we don't act on."""
    issue = payload.get("issue") or {}
    labels = {lb.get("name", "") for lb in issue.get("labels", [])}
    if TRIGGER_LABEL not in labels:
        return None
    if payload.get("action") not in {"opened", "labeled", "reopened"}:
        return None

    repo_full = (payload.get("repository") or {}).get("name", "")
    title = issue.get("title", "")
    body = issue.get("body") or ""
    prompt = f"{title}\n\n{body}".strip()
    if not repo_full or not prompt:
        return None

    return IntentRequest(
        intent_id=f"gh-issue-{issue.get('number', 'unknown')}",
        repo=repo_full,
        prompt=prompt,
        submitted_by=(issue.get("user") or {}).get("login", "github"),
    )


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    body = await request.body()

    if not secret:
        raise HTTPException(status_code=503, detail="webhook secret not configured")
    if not verify_signature(body, x_hub_signature_256, secret):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    if x_github_event == "ping":
        return {"pong": True}
    if x_github_event != "issues":
        return {"received": True, "ignored": f"unhandled event: {x_github_event}"}

    payload = await request.json()
    intent = intent_from_issue_event(payload)
    if intent is None:
        return {"received": True, "ignored": "no codegate trigger on this event"}

    result = await run_pipeline(intent)
    return {"received": True, "intent_id": intent.intent_id, "result": result}
