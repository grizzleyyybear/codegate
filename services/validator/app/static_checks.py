"""Thin subprocess wrappers around ruff / mypy / bandit, run against a
checked-out copy of the repo with the patch applied."""
from __future__ import annotations

import os
import subprocess


def run_ruff(repo_path: str) -> tuple[bool, str]:
    # I001: import sorting is auto-fixable style; a local model's import order
    # should not block a merge
    result = subprocess.run(
        ["ruff", "check", "--ignore", "I001", repo_path],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0, result.stdout + result.stderr


def run_mypy(repo_path: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["mypy", repo_path], capture_output=True, text=True, check=False
    )
    return result.returncode == 0, result.stdout + result.stderr


def run_bandit(repo_path: str) -> tuple[bool, str]:
    # -x <abs>/tests: asserts in test files are normal, not a security signal.
    # The exclusion path must be absolute: bandit resolves -x via
    # os.path.isdir() relative to the CWD, so a bare "tests" silently fails
    # to exclude anything when the CWD happens to contain a tests/ dir.
    result = subprocess.run(
        ["bandit", "-r", repo_path, "-q", "-x", os.path.join(repo_path, "tests")],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0, result.stdout + result.stderr
