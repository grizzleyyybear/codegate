"""Aggregates static analysis, tests, and the LLM judge into one
confidence score the guardrail service thresholds against.

The patch is applied to a fresh clone of the repo's committed state (never
the live checkout), so scoring is hermetic and re-runnable. If the diff
doesn't apply, that's a hard failure: confidence 0 and a clear reason.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from shared.schemas import CodePatch, ValidationResult

from .llm_judge import judge_patch
from .static_checks import run_bandit, run_mypy, run_ruff
from .test_runner import run_tests

WEIGHTS = {"static": 0.25, "tests": 0.4, "judge": 0.35}


def repos_root() -> str:
    return os.environ.get("REPOS_ROOT", "/work")


def _clone_with_patch(patch: CodePatch) -> tuple[str | None, str]:
    """Returns (repo_path_with_patch_applied, "") on success, or (None, reason)."""
    source = os.path.join(repos_root(), patch.repo)
    if not os.path.isdir(source):
        return None, f"repo checkout not found: {source}"

    scratch_root = os.path.join(repos_root(), ".validator")
    os.makedirs(scratch_root, exist_ok=True)
    target = os.path.join(scratch_root, patch.intent_id)
    shutil.rmtree(target, ignore_errors=True)

    clone = subprocess.run(
        ["git", "clone", "-q", "--local", source, target],
        capture_output=True,
        text=True,
        check=False,
    )
    if clone.returncode != 0:
        return None, f"clone failed: {clone.stderr.strip()}"

    diff_path = os.path.join(scratch_root, f"{patch.intent_id}.diff")
    with open(diff_path, "w") as fh:
        fh.write(patch.diff)

    applied = subprocess.run(
        ["git", "-C", target, "apply", diff_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if applied.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        return None, f"patch does not apply: {applied.stderr.strip()}"

    return target, ""


async def score_patch(patch: CodePatch) -> ValidationResult:
    repo_path, apply_error = _clone_with_patch(patch)
    if apply_error:
        return ValidationResult(
            intent_id=patch.intent_id,
            static_analysis_passed=False,
            tests_passed=False,
            test_output="",
            llm_judge_score=0.0,
            llm_judge_reasoning=apply_error,
            confidence=0.0,
        )

    assert repo_path is not None

    try:
        ruff_ok, _ = run_ruff(repo_path)
        mypy_ok, _ = run_mypy(repo_path)
        bandit_ok, _ = run_bandit(repo_path)
        static_ok = ruff_ok and mypy_ok and bandit_ok

        tests_ok, test_output = run_tests(repo_path)
    finally:
        shutil.rmtree(repo_path, ignore_errors=True)

    judge_score, judge_reasoning = await judge_patch(patch)

    confidence = (
        WEIGHTS["static"] * (1.0 if static_ok else 0.0)
        + WEIGHTS["tests"] * (1.0 if tests_ok else 0.0)
        + WEIGHTS["judge"] * judge_score
    )

    return ValidationResult(
        intent_id=patch.intent_id,
        static_analysis_passed=static_ok,
        tests_passed=tests_ok,
        test_output=test_output,
        llm_judge_score=judge_score,
        llm_judge_reasoning=judge_reasoning,
        confidence=round(confidence, 3),
    )
