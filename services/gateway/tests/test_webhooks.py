import hashlib
import hmac

from app.main import app
from app.webhooks import intent_from_issue_event, verify_signature
from fastapi.testclient import TestClient

client = TestClient(app)

_SECRET = "s3cret"


def _sig(body: bytes) -> str:
    return "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _issue_payload(label=True, action="opened", repo="punrek", title="add rate limiting", body="to the auth endpoint"):
    return {
        "action": action,
        "issue": {
            "number": 42,
            "title": title,
            "body": body,
            "labels": [{"name": "codegate"}] if label else [{"name": "other"}],
            "user": {"login": "mrinal"},
        },
        "repository": {"name": repo},
    }


def test_verify_signature_ok():
    body = b"hello"
    assert verify_signature(body, _sig(body), _SECRET) is True


def test_verify_signature_wrong():
    body = b"hello"
    assert verify_signature(body, "sha256=" + "0" * 64, _SECRET) is False


def test_verify_signature_bad_header_shape():
    assert verify_signature(b"hello", "abc", _SECRET) is False
    assert verify_signature(b"hello", None, _SECRET) is False


def test_intent_from_issue_event_valid():
    intent = intent_from_issue_event(_issue_payload())
    assert intent is not None
    assert intent.intent_id == "gh-issue-42"
    assert intent.repo == "punrek"
    assert "add rate limiting" in intent.prompt
    assert intent.submitted_by == "mrinal"


def test_intent_from_issue_event_missing_trigger_label():
    assert intent_from_issue_event(_issue_payload(label=False)) is None


def test_intent_from_issue_event_wrong_action():
    assert intent_from_issue_event(_issue_payload(action="closed")) is None


def test_intent_from_issue_event_empty_prompt():
    assert intent_from_issue_event(_issue_payload(title="", body="")) is None


def test_intent_from_issue_event_missing_repo():
    assert intent_from_issue_event(_issue_payload(repo="")) is None


def test_webhook_requires_secret(monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    resp = client.post("/webhooks/github", json={})
    assert resp.status_code == 503


def test_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
    resp = client.post(
        "/webhooks/github",
        content=b"{}",
        headers={"X-Hub-Signature-256": "sha256=" + "f" * 64},
    )
    assert resp.status_code == 401


def test_webhook_ping(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
    body = b'{"zen": "keep it simple"}'
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sig(body), "X-GitHub-Event": "ping"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}


def test_webhook_unhandled_event(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
    body = b"{}"
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sig(body), "X-GitHub-Event": "push"},
    )
    assert resp.json()["ignored"] == "unhandled event: push"


def test_webhook_no_trigger_label(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
    body = b'{"action": "opened", "issue": {"labels": [{"name": "other"}]}, "repository": {"name": "r"}}'
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sig(body), "X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 200
    assert resp.json()["ignored"] == "no codegate trigger on this event"


def test_webhook_runs_pipeline(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)

    async def fake_run_pipeline(intent):
        return {"patch": {}, "validation": {}, "decision": {"action": "reject"}, "outcome": {"rejected": True}}

    monkeypatch.setattr("app.webhooks.run_pipeline", fake_run_pipeline)
    body = (
        b'{"action": "opened", '
        b'"issue": {"number": 42, "title": "t", "body": "b", '
        b'"labels": [{"name": "codegate"}], "user": {"login": "u"}}, '
        b'"repository": {"name": "punrek"}}'
    )
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sig(body), "X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 200
    assert resp.json()["intent_id"] == "gh-issue-42"
    assert resp.json()["result"]["outcome"]["rejected"] is True
