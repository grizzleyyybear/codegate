"""Any diff touching these path patterns is never auto-merged, no matter
how high the confidence score — it always goes to human review.

Paths are parsed from `diff --git` headers (robust to spaces in paths and
to the a/ b/ prefixes), with +++/--- headers as a fallback. Added lines
are also scanned for secret-looking content, so a patch can't slip a
credential into an innocently-named file.
"""
from __future__ import annotations

import re

SENSITIVE_PATH_PATTERNS = [
    r"auth",
    r"secrets?",
    r"\.env",
    r"infra/",
    r"k8s/",
    r"payment",
    r"migrations?/",
]

# secret-looking content in ADDED lines: hardcoded keys, tokens, private keys
SENSITIVE_CONTENT_PATTERNS = [
    r"(?i)(api[_-]?key|secret|token|passwd|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"(?i)aws_secret_access_key",
    r"AKIA[0-9A-Z]{16}",  # AWS access key id
]

_GIT_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)


def _diff_paths(diff: str) -> list[str]:
    """File paths touched by the diff. Prefers `diff --git` headers; falls
    back to +++/--- lines (stripping the a/ b/ prefix) for raw hunks."""
    paths: set[str] = set()
    for m in _GIT_HEADER_RE.finditer(diff):
        paths.update(m.groups())
    if not paths:
        for line in diff.splitlines():
            if line.startswith(("+++ ", "--- ")):
                p = line[4:].strip()
                if p in {"/dev/null", ""}:
                    continue
                if p.startswith(("a/", "b/")):
                    p = p[2:]
                paths.add(p)
    return sorted(paths)


def _added_lines(diff: str) -> list[str]:
    return [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def touches_sensitive_path(diff: str) -> bool:
    for path in _diff_paths(diff):
        for pattern in SENSITIVE_PATH_PATTERNS:
            if re.search(pattern, path, re.IGNORECASE):
                return True
    for line in _added_lines(diff):
        for pattern in SENSITIVE_CONTENT_PATTERNS:
            if re.search(pattern, line):
                return True
    return False
