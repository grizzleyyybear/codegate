"""Thin subprocess wrappers around ruff / mypy / bandit, run against a
checked-out copy of the repo with the patch applied.

Static analysis is baseline-diffed: the check runs once against the
pristine clone and once against the patched clone, and only NEW
violations block a merge. Blocking on every pre-existing violation in a
real repo would make the pipeline unusable against legacy code — the
agent's job is to not make things worse, not to pay down someone else's
debt in one patch.
"""
from __future__ import annotations

import os
import re
import subprocess

# ruff >=0.16 (new format): code and location on separate lines:
#   F821 Undefined name `undefined_name`
#    --> path/to/file.py:3:7
# older ruff: "path:line:col: CODE message"
_RUFF_CODE_RE = re.compile(r"^([A-Z]{1,4}\d{2,4})(?: \[\*\])? ", re.MULTILINE)
_RUFF_LOC_RE = re.compile(r"^\s*-->\s+(.+?):\d+:\d+$", re.MULTILINE)
_RUFF_OLD_RE = re.compile(r"^(.+?):\d+:\d+: ([A-Z]{1,4}\d{2,4}) ", re.MULTILINE)
# mypy output: "path:line: error: message"
_MYPY_RE = re.compile(r"^(.+?):\d+: error: (.+)$", re.MULTILINE)
# bandit: "Issue: [B\d{3}:name] ...", report lines ">> Issue:"
_BANDIT_RE = re.compile(r"Issue: \[([B]\d{3}):")


def _run(cmd: list[str], repo_path: str) -> tuple[int, str]:
    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def _norm(path: str, repo_root: str) -> str:
    """Repo-relative, forward-slashed path so violations from different
    clone directories (baseline vs patched) compare equal. Ruff/mypy emit
    CWD-relative paths when the repo root is the CWD, and absolute paths
    otherwise — both must collapse to the same repo-relative form."""
    path = path.replace("\\", "/")
    if not os.path.isabs(path):
        return path
    try:
        rel = os.path.relpath(path, repo_root)
    except ValueError:
        return path
    return rel.replace("\\", "/")


def ruff_violations(repo_path: str) -> set[tuple[str, str]]:
    # I001: import sorting is auto-fixable style; a local model's import order
    # should not block a merge
    _, out = _run(["ruff", "check", "--ignore", "I001", repo_path], repo_path)
    found: set[tuple[str, str]] = set()
    pending: str | None = None
    for line in out.splitlines():
        old = _RUFF_OLD_RE.match(line)
        if old:
            found.add((_norm(old.group(1), repo_path), old.group(2)))
            pending = None
            continue
        code = _RUFF_CODE_RE.match(line)
        if code:
            pending = code.group(1)
            continue
        loc = _RUFF_LOC_RE.match(line)
        if loc and pending:
            found.add((_norm(loc.group(1), repo_path), pending))
            pending = None
    return found


def mypy_violations(repo_path: str) -> set[tuple[str, str]]:
    _, out = _run(["mypy", repo_path], repo_path)
    return {
        (_norm(m.group(1), repo_path), m.group(2)) for m in _MYPY_RE.finditer(out)
    }


_LOCATION_RE = re.compile(r"Location: (.+):\d+:\d+$")


def bandit_violations(repo_path: str) -> set[tuple[str, str]]:
    # -x <abs>/tests: asserts in test files are normal, not a security signal.
    # The exclusion path must be absolute: bandit resolves -x via
    # os.path.isdir() relative to the CWD, so a bare "tests" silently fails
    # to exclude anything when the CWD happens to contain a tests/ dir.
    _, out = _run(
        ["bandit", "-r", repo_path, "-q", "-x", os.path.join(repo_path, "tests")],
        repo_path,
    )
    findings: set[tuple[str, str]] = set()
    code = ""
    for line in out.splitlines():
        issue = _BANDIT_RE.search(line)
        if issue:
            code = issue.group(1)
            continue
        loc = _LOCATION_RE.search(line)
        if loc and code:
            findings.add((_norm(loc.group(1), repo_path), code))
            code = ""
    return findings


def static_violations(repo_path: str) -> dict[str, set[tuple[str, str]]]:
    return {
        "ruff": ruff_violations(repo_path),
        "mypy": mypy_violations(repo_path),
        "bandit": bandit_violations(repo_path),
    }


def new_violations(
    baseline: dict[str, set[tuple[str, str]]],
    current: dict[str, set[tuple[str, str]]],
) -> dict[str, set[tuple[str, str]]]:
    """Only violations introduced by the patch — everything present in the
    pristine repo is pre-existing debt and does not block."""
    return {
        tool: current.get(tool, set()) - baseline.get(tool, set())
        for tool in current
    }


def run_ruff(repo_path: str) -> tuple[bool, str]:
    ok = not ruff_violations(repo_path)
    _, out = _run(["ruff", "check", "--ignore", "I001", repo_path], repo_path)
    return ok, out


def run_mypy(repo_path: str) -> tuple[bool, str]:
    ok = not mypy_violations(repo_path)
    _, out = _run(["mypy", repo_path], repo_path)
    return ok, out


def run_bandit(repo_path: str) -> tuple[bool, str]:
    ok = not bandit_violations(repo_path)
    _, out = _run(
        ["bandit", "-r", repo_path, "-q", "-x", os.path.join(repo_path, "tests")],
        repo_path,
    )
    return ok, out


def describe_new_violations(
    new: dict[str, set[tuple[str, str]]],
) -> str:
    """Human-readable summary of the violations a patch introduced."""
    lines = []
    for tool in ("ruff", "mypy", "bandit"):
        for path, code in sorted(new.get(tool, set())):
            lines.append(f"{tool}: {path}: {code}")
    return "\n".join(lines)
