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

import os
import subprocess

import httpx
from opentelemetry import trace

from shared.schemas import GuardrailAction, IntentRequest

from . import review_queue

tracer = trace.get_tracer("codegate-gateway")

ORCHESTRATOR_URL = "http://orchestrator:8001"
CODEGEN_URL = "http://codegen:8003"
VALIDATOR_URL = "http://validator:8004"
GUARDRAIL_URL = "http://guardrail:8005"
MAX_CODEGEN_ATTEMPTS = int(os.environ.get("MAX_CODEGEN_ATTEMPTS", "3"))


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
        ["git", "-C", checkout, "add", "-A"],
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


def _validation_clean(validation: dict) -> bool:
    """True when the patch applied, passed static analysis, and passed tests."""
    return bool(
        validation.get("tests_passed")
        and validation.get("static_analysis_passed")
        and (validation.get("confidence") or 0) > 0
    )


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
    async with httpx.AsyncClient(timeout=300) as client:
        with tracer.start_as_current_span("orchestrate"):
            plan = (
                await client.post(
                    f"{ORCHESTRATOR_URL}/plan",
                    json=intent.model_dump(mode="json"),
                )
            ).json()

        # if the first (cheap) model emits a broken patch, retry with the
        # validator's full failure feedback and escalate to the stronger
        # model family until validation is clean or attempts run out.
        with tracer.start_as_current_span("codegen"):
            patch = (await client.post(f"{CODEGEN_URL}/generate", json={"plan": plan})).json()

        with tracer.start_as_current_span("validate"):
            validation = (
                await client.post(f"{VALIDATOR_URL}/validate", json=patch)
            ).json()
            for _ in range(1, MAX_CODEGEN_ATTEMPTS):
                if _validation_clean(validation):
                    break
                with tracer.start_as_current_span("codegen_retry"):
                    patch = (
                        await client.post(
                            f"{CODEGEN_URL}/generate",
                            json={
                                "plan": plan,
                                "feedback": _retry_feedback(validation),
                                "escalate": True,
                            },
                        )
                    ).json()
                validation = (
                    await client.post(f"{VALIDATOR_URL}/validate", json=patch)
                ).json()

        with tracer.start_as_current_span("guardrail"):
            decision = (
                await client.post(
                    f"{GUARDRAIL_URL}/decide",
                    json={"patch": patch, "validation": validation},
                )
            ).json()

    action = decision["action"]
    if action == GuardrailAction.AUTO_MERGE:
        result = _auto_merge(patch)
    elif action == GuardrailAction.HUMAN_REVIEW:
        result = _queue_for_review(patch, validation, decision, prompt=intent.prompt)
    else:
        result = {"rejected": True}

    return {"patch": patch, "validation": validation, "decision": decision, "outcome": result}
