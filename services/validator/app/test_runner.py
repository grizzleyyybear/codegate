"""Runs pytest against a checked-out copy of the repo with the patch
applied. `python -m pytest` is used (not the bare binary) so the repo
root lands on sys.path and `from <module> import ...` works in tests."""
from __future__ import annotations

import subprocess
import sys


def run_tests(repo_path: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0, result.stdout + result.stderr
