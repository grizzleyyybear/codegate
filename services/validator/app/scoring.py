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
from .static_checks import (
    describe_new_violations,
    new_violations,
    static_violations,
)
from .test_runner import run_tests

WEIGHTS = {"static": 0.25, "tests": 0.4, "judge": 0.35}


def repos_root() -> str:
    return os.environ.get("REPOS_ROOT", "/work")


def _clone_to(source: str, target: str) -> tuple[bool, str]:
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.rmtree(target, ignore_errors=True)
    clone = subprocess.run(
        ["git", "clone", "-q", "--local", source, target],
        capture_output=True,
        text=True,
        check=False,
    )
    if clone.returncode != 0:
        return False, f"clone failed: {clone.stderr.strip()}"
    return True, ""


def _static_baseline(source: str, intent_id: str) -> dict[str, set[tuple[str, str]]]:
    """Static-analysis violations of the repo as-is — the debt the patch is
    allowed to inherit but not add to. Best-effort: an empty baseline makes
    every violation count as new."""
    scratch_root = os.path.join(repos_root(), ".validator")
    target = os.path.join(scratch_root, f"baseline-{intent_id}")
    try:
        ok, _ = _clone_to(source, target)
        if not ok:
            return {}
        return static_violations(target)
    finally:
        shutil.rmtree(target, ignore_errors=True)


def _clone_with_patch(patch: CodePatch) -> tuple[str | None, str]:
    """Returns (repo_path_with_patch_applied, "") on success, or (None, reason)."""
    source = os.path.join(repos_root(), patch.repo)
    if not os.path.isdir(source):
        return None, f"repo checkout not found: {source}"

    scratch_root = os.path.join(repos_root(), ".validator")
    os.makedirs(scratch_root, exist_ok=True)
    target = os.path.join(scratch_root, patch.intent_id)

    ok, err = _clone_to(source, target)
    if not ok:
        return None, err

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
    source = os.path.join(repos_root(), patch.repo)
    if not os.path.isdir(source):
        return ValidationResult(
            intent_id=patch.intent_id,
            static_analysis_passed=False,
            tests_passed=False,
            test_output="",
            llm_judge_score=0.0,
            llm_judge_reasoning=f"repo checkout not found: {source}",
            confidence=0.0,
        )

    # static analysis is baseline-diffed: pre-existing repo debt does not
    # block a merge — only violations the patch introduces do
    baseline = _static_baseline(source, patch.intent_id)

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
        current = static_violations(repo_path)
        new = new_violations(baseline, current)
        static_ok = not any(new.values())
        static_detail = describe_new_violations(new)

        tests_ok, test_output = run_tests(repo_path)
    finally:
        shutil.rmtree(repo_path, ignore_errors=True)

    judge_score, judge_reasoning = await judge_patch(patch)

    confidence = (
        WEIGHTS["static"] * (1.0 if static_ok else 0.0)
        + WEIGHTS["tests"] * (1.0 if tests_ok else 0.0)
        + WEIGHTS["judge"] * judge_score
    )
    if static_detail:
        judge_reasoning = f"NEW static violations:\n{static_detail}\n\n{judge_reasoning}"

    return ValidationResult(
        intent_id=patch.intent_id,
        static_analysis_passed=static_ok,
        tests_passed=tests_ok,
        test_output=test_output,
        llm_judge_score=judge_score,
        llm_judge_reasoning=judge_reasoning,
        confidence=round(confidence, 3),
    )
