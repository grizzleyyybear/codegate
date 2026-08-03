import asyncio
import os

import httpx
from app import pipeline
from app.pipeline import (
    _auto_merge,
    _retry_feedback,
    _validation_clean,
    repos_root,
    run_pipeline,
)
from test_pipeline_merge import _make_repo, _patch

from shared.schemas import IntentRequest


def test_repos_root_default():
    assert repos_root() == "/work"


def test_validation_clean_true():
    assert _validation_clean({"tests_passed": True, "static_analysis_passed": True, "confidence": 0.9}) is True


def test_validation_clean_false_variants():
    assert _validation_clean({"tests_passed": False, "static_analysis_passed": True, "confidence": 0.9}) is False
    assert _validation_clean({"tests_passed": True, "static_analysis_passed": False, "confidence": 0.9}) is False
    assert _validation_clean({"tests_passed": True, "static_analysis_passed": True, "confidence": 0}) is False
    assert _validation_clean({"tests_passed": True, "static_analysis_passed": True}) is False


def test_retry_feedback_static_only():
    fb = _retry_feedback({"static_analysis_passed": False, "tests_passed": True, "test_output": "", "llm_judge_reasoning": ""})
    assert "Static analysis" in fb


def test_retry_feedback_tests_with_output():
    fb = _retry_feedback({"static_analysis_passed": True, "tests_passed": False, "test_output": "1 failed", "llm_judge_reasoning": ""})
    assert "Tests FAILED" in fb
    assert "1 failed" in fb


def test_retry_feedback_judge_reasoning():
    fb = _retry_feedback({"static_analysis_passed": True, "tests_passed": True, "test_output": "", "llm_judge_reasoning": "scope creep"})
    assert "Reviewer notes: scope creep" in fb


def test_retry_feedback_fallback():
    fb = _retry_feedback({"static_analysis_passed": True, "tests_passed": True, "test_output": "", "llm_judge_reasoning": ""})
    assert fb == "Validation failed for an unknown reason."


def test_auto_merge_apply_failure(tmp_path):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)
    bad = _patch("repo")
    bad["diff"] = (
        "--- a/missing_file.py\n"
        "+++ b/missing_file.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    result = _auto_merge(bad)
    assert result["merged"] is False
    assert "git apply failed" in result["detail"]


def test_auto_merge_commit_failure(tmp_path, monkeypatch):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    class CommitFailure(FakeResult):
        returncode = 1
        stderr = "identity unknown"

    def fake_run(cmd, *args, **kwargs):
        if "commit" in cmd:
            return CommitFailure()
        return FakeResult()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    result = _auto_merge(_patch("repo"))
    assert result["merged"] is False
    assert "git commit failed" in result["detail"]


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeAClient:
    """Stateful fake: validator responses are popped per call."""

    def __init__(self, routes, validator_responses=None):
        self.routes = routes
        self.validator_responses = list(validator_responses or [])
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        self.calls.append((url, json))
        for prefix, payload in self.routes:
            if url.startswith(prefix):
                if "validator" in url and self.validator_responses:
                    return FakeResponse(self.validator_responses.pop(0))
                return FakeResponse(payload)
        raise AssertionError(f"unexpected url: {url}")


def _intent():
    return IntentRequest(intent_id="i1", repo="r", prompt="p", submitted_by="u")


_PATCH = {
    "intent_id": "i1",
    "repo": "r",
    "diff": "--- a/x\n+++ b/x\n",
    "model_used": "m",
    "prompt_tokens": 1,
    "completion_tokens": 1,
}
_CLEAN = {"tests_passed": True, "static_analysis_passed": True, "confidence": 0.9, "test_output": "", "llm_judge_reasoning": ""}


def _routes(guardrail_action):
    return [
        ("http://orchestrator:8001", {"intent_id": "i1", "repo": "r", "steps": [], "context": []}),
        ("http://codegen:8003", _PATCH),
        ("http://validator:8004", _CLEAN),
        ("http://guardrail:8005", {"action": guardrail_action, "reason": "why", "intent_id": "i1", "touches_sensitive_path": False}),
    ]


def test_run_pipeline_auto_merge(monkeypatch):
    fake = FakeAClient(_routes("auto_merge"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: fake)
    merged = {"merged": True, "detail": "committed"}
    monkeypatch.setattr(pipeline, "_auto_merge", lambda patch: merged)
    result = asyncio.run(run_pipeline(_intent()))
    assert result["outcome"] == merged
    assert result["decision"]["action"] == "auto_merge"


def test_run_pipeline_human_review(monkeypatch):
    fake = FakeAClient(_routes("human_review"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: fake)
    queued = {"queued": True, "intent_id": "i1"}
    monkeypatch.setattr(pipeline, "_queue_for_review", lambda *a, **kw: queued)
    result = asyncio.run(run_pipeline(_intent()))
    assert result["outcome"] == queued


def test_run_pipeline_reject(monkeypatch):
    fake = FakeAClient(_routes("reject"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: fake)
    result = asyncio.run(run_pipeline(_intent()))
    assert result["outcome"] == {"rejected": True}


def test_run_pipeline_retries_on_dirty_validation(monkeypatch):
    dirty = {"tests_passed": False, "static_analysis_passed": True, "confidence": 0.2, "test_output": "boom", "llm_judge_reasoning": "nope"}
    fake = FakeAClient(_routes("auto_merge"), validator_responses=[dirty, _CLEAN])
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: fake)
    merged = {"merged": True, "detail": "committed"}
    monkeypatch.setattr(pipeline, "_auto_merge", lambda patch: merged)
    result = asyncio.run(run_pipeline(_intent()))
    assert result["validation"]["confidence"] == 0.9

    codegen_calls = [c for c in fake.calls if "codegen" in c[0]]
    assert len(codegen_calls) == 2
    retry_body = codegen_calls[1][1]
    assert retry_body["escalate"] is True
    assert "boom" in retry_body["feedback"]


def test_run_pipeline_hits_attempt_cap(monkeypatch):
    dirty = {"tests_passed": False, "static_analysis_passed": False, "confidence": 0.1, "test_output": "x", "llm_judge_reasoning": ""}
    monkeypatch.setattr(pipeline, "MAX_CODEGEN_ATTEMPTS", 2)
    fake = FakeAClient(_routes("human_review"), validator_responses=[dirty, dirty])
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: fake)
    queued = {"queued": True, "intent_id": "i1"}
    monkeypatch.setattr(pipeline, "_queue_for_review", lambda *a, **kw: queued)
    result = asyncio.run(run_pipeline(_intent()))
    assert result["validation"]["tests_passed"] is False
    codegen_calls = [c for c in fake.calls if "codegen" in c[0]]
    assert len(codegen_calls) == 2
