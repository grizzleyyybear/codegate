"""Chains orchestrator -> codegen -> validator -> guardrail, then either
hits the CI/CD gate (auto-merge path) or writes to the human review queue.

This function is the pipeline drawn in the architecture diagram — every
box in that diagram is one httpx call here, wrapped in its own OTel span.

MVP merge semantics: "auto-merge" applies the patch to the shared scratch
checkout (/work/<repo>, bind-mounted from ./scratch) and commits it to
main. That commit is the end-to-end proof of the pipeline. Swapping this
for a real PyGithub PR open (step 8) touches only _auto_merge.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any

import httpx
from fastapi import HTTPException
from opentelemetry import trace

from shared.schemas import GuardrailAction, IntentRequest

from . import review_queue

logger = logging.getLogger("codegate.gateway.pipeline")

tracer = trace.get_tracer("codegate-gateway")

ORCHESTRATOR_URL = "http://orchestrator:8001"
CODEGEN_URL = "http://codegen:8003"
VALIDATOR_URL = "http://validator:8004"
GUARDRAIL_URL = "http://guardrail:8005"
MAX_CODEGEN_ATTEMPTS = int(os.environ.get("MAX_CODEGEN_ATTEMPTS", "3"))
# Free-tier LLM endpoints can take minutes (cold starts, provider queues);
# the per-request budget must comfortably exceed a full retry ladder.
REQUEST_TIMEOUT = int(os.environ.get("GATEWAY_REQUEST_TIMEOUT", "900"))


def repos_root() -> str:
    return os.environ.get("REPOS_ROOT", "/work")


def _auto_merge(patch: dict) -> dict:
    """Applies the patch to the scratch checkout and commits it to main.
    Returns {'merged': bool, 'detail': str}."""
    repo = patch.get("repo", "")
    checkout = os.path.join(repos_root(), repo)
    if not os.path.isdir(checkout):
        return {"merged": False, "detail": f"checkout not found: {checkout}"}

    diff_path = os.path.join(repos_root(), f".gateway-{patch['intent_id']}.diff")
    with open(diff_path, "w") as fh:
        fh.write(patch["diff"])

    apply = subprocess.run(
        # --ignore-space-change: tolerate CRLF vs LF working trees (e.g. a
        # repo checked out on Windows bind-mounted into a Linux container)
        ["git", "-C", checkout, "apply", "--ignore-space-change", diff_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if apply.returncode != 0:
        return {"merged": False, "detail": f"git apply failed: {apply.stderr.strip()}"}

    commit_msg = f"codegate: {patch['intent_id']} via {patch['model_used']}"
    stage = subprocess.run(
        # core.autocrlf=true normalizes the CRLF worktree (Windows bind
        # mount) back to LF blobs on stage, so a merge commit contains
        # only the real change — not line-ending churn across the repo.
        ["git", "-c", "core.autocrlf=true", "-C", checkout, "add", "-A"],
        capture_output=True,
        text=True,
        check=False,
    )
    commit = subprocess.run(
        ["git", "-C", checkout, "-c", "user.name=codegate", "-c", "user.email=codegate@localhost", "commit", "-q", "-m", commit_msg],
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        detail = (commit.stderr or stage.stderr or "").strip()
        return {"merged": False, "detail": f"git commit failed: {detail}"}

    return {
        "merged": True,
        "detail": f"committed to {repo} main: {commit_msg}",
        "commit": commit.stdout.strip() or commit_msg,
    }


def _queue_for_review(patch: dict, validation: dict, decision: dict, prompt: str = "") -> dict:
    review_queue.enqueue(
        intent_id=patch["intent_id"],
        repo=patch.get("repo", ""),
        prompt=prompt,
        diff=patch["diff"],
        confidence=validation["confidence"],
        reason=decision["reason"],
    )
    return {"queued": True, "intent_id": patch["intent_id"]}


def record_human_outcome(item: dict, approved: bool) -> None:
    """Feed a human review decision back into the orchestrator's task
    memory — the richest learning signal the pipeline has. Best-effort:
    memory is advisory, never fatal."""
    try:
        httpx.post(
            f"{ORCHESTRATOR_URL}/outcome",
            json={
                "intent_id": item["intent_id"],
                "repo": item.get("repo", ""),
                "prompt": item.get("prompt", ""),
                "action": "human_approved" if approved else "human_rejected",
                "confidence": item.get("confidence", 0.0),
                "attempts": 1,
                "reasoning": item.get("reason", ""),
            },
            timeout=5,
        )
    except Exception:  # noqa: BLE001, S110 — memory is advisory, never fatal
        pass


def _validation_clean(validation: dict) -> bool:
    """True when the patch applied, passed static analysis, and passed tests."""
    return bool(
        validation.get("tests_passed")
        and validation.get("static_analysis_passed")
        and (validation.get("confidence") or 0) > 0
    )


async def _post_json(
    client: httpx.AsyncClient, url: str, tag: str, intent_id: str, **kwargs: Any
) -> dict:
    """One pipeline hop: POST and parse JSON, with a log trail.

    A stage failure (transport error, non-JSON body, dead peer) must leave
    an actionable error with the stage name instead of a silent hang or an
    opaque 500 — the pipeline is long and the operator needs to know where
    it stopped.
    """
    logger.info("stage=%s intent=%s -> %s", tag, intent_id, url)
    started = time.monotonic()
    try:
        resp = await client.post(url, **kwargs)
    except httpx.HTTPError as e:
        raise RuntimeError(f"stage {tag}: transport error: {e}") from e
    elapsed = time.monotonic() - started
    status = getattr(resp, "status_code", None)
    try:
        body = resp.json()
    except ValueError as e:
        snippet = (getattr(resp, "text", "") or "<empty body>")[:200].strip()
        raise RuntimeError(
            f"stage {tag}: non-JSON response (status {status}): {snippet!r}"
        ) from e
    logger.info("stage=%s intent=%s status=%s in %.1fs", tag, intent_id, status, elapsed)
    return body


def _retry_feedback(validation: dict) -> str:
    """Everything the model needs to know about why the last attempt
    failed — not just the test output."""
    parts = []
    if not validation.get("static_analysis_passed"):
        parts.append("Static analysis (ruff/mypy/bandit) FAILED.")
    if not validation.get("tests_passed"):
        parts.append(f"Tests FAILED. Output:\n{validation.get('test_output', '')}")
    reasoning = validation.get("llm_judge_reasoning", "")
    if reasoning:
        parts.append(f"Reviewer notes: {reasoning}")
    return "\n\n".join(parts) or "Validation failed for an unknown reason."


async def run_pipeline(intent: IntentRequest) -> dict:
    """Chain the stages; any failure becomes a structured 502 naming the
    failing stage (and a full log trail) instead of a silent hang."""
    try:
        return await _run_pipeline(intent)
    except Exception as e:
        logger.exception("pipeline %s failed", intent.intent_id)
        raise HTTPException(
            status_code=502,
            detail=f"pipeline failed for {intent.intent_id}: {e}",
        ) from e


async def _run_pipeline(intent: IntentRequest) -> dict:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        with tracer.start_as_current_span("orchestrate"):
            plan = await _post_json(
                client,
                f"{ORCHESTRATOR_URL}/plan",
                "orchestrate",
                intent.intent_id,
                json={"intent": intent.model_dump(mode="json")},
            )

        # escalation ladder when validation fails:
        #   attempt 2: same plan, stronger model, full failure feedback
        #   attempt 3+: full REPLAN — the orchestrator re-formulates the
        #   goal around the failure, then the stronger model executes it
        attempts = 1
        with tracer.start_as_current_span("codegen"):
            patch = await _post_json(
                client,
                f"{CODEGEN_URL}/generate",
                "codegen",
                intent.intent_id,
                json={"plan": plan},
            )

        with tracer.start_as_current_span("validate"):
            validation = await _post_json(
                client,
                f"{VALIDATOR_URL}/validate",
                "validate",
                intent.intent_id,
                json=patch,
            )
            for attempt in range(1, MAX_CODEGEN_ATTEMPTS):
                if _validation_clean(validation):
                    break
                feedback = _retry_feedback(validation)
                if attempt >= 2:
                    with tracer.start_as_current_span("replan"):
                        plan = await _post_json(
                            client,
                            f"{ORCHESTRATOR_URL}/plan",
                            "replan",
                            intent.intent_id,
                            json={
                                "intent": intent.model_dump(mode="json"),
                                "feedback": feedback,
                            },
                        )
                with tracer.start_as_current_span("codegen_retry"):
                    patch = await _post_json(
                        client,
                        f"{CODEGEN_URL}/generate",
                        "codegen_retry",
                        intent.intent_id,
                        json={
                            "plan": plan,
                            "feedback": feedback,
                            "escalate": True,
                        },
                    )
                attempts += 1
                validation = await _post_json(
                    client,
                    f"{VALIDATOR_URL}/validate",
                    "validate_retry",
                    intent.intent_id,
                    json=patch,
                )

        with tracer.start_as_current_span("guardrail"):
            decision = await _post_json(
                client,
                f"{GUARDRAIL_URL}/decide",
                "guardrail",
                intent.intent_id,
                json={"patch": patch, "validation": validation},
            )

        # feed the outcome back into persistent task memory so the next
        # similar intent plans with this run's lessons (best-effort)
        with tracer.start_as_current_span("record_outcome"):
            try:
                await client.post(
                    f"{ORCHESTRATOR_URL}/outcome",
                    json={
                        "intent_id": intent.intent_id,
                        "repo": intent.repo,
                        "prompt": intent.prompt,
                        "action": decision["action"],
                        "confidence": validation.get("confidence", 0.0),
                        "attempts": attempts,
                        "reasoning": validation.get("llm_judge_reasoning", ""),
                    },
                )
            except Exception:  # noqa: BLE001, S110 — memory is advisory, never fatal
                pass

    action = decision["action"]
    if action == GuardrailAction.AUTO_MERGE:
        result = _auto_merge(patch)
    elif action == GuardrailAction.HUMAN_REVIEW:
        result = _queue_for_review(patch, validation, decision, prompt=intent.prompt)
    else:
        result = {"rejected": True}

    return {"patch": patch, "validation": validation, "decision": decision, "outcome": result}
