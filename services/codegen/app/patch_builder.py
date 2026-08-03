"""Builds clean unified diffs out of model responses.

Two modes:
- whole-file rewrites (current default): the model rewrites each file in
  full; build_patch_from_rewrites diffs them with difflib so hunk headers
  are always correct.
- legacy: extract_diff still strips markdown fences from raw model text
  for backward compatibility.
"""
from __future__ import annotations

import difflib
import re

DIFF_FENCE = re.compile(r"```(?:diff)?\n(.*?)```", re.DOTALL)

FILE_SECTION = re.compile(r"^=== (.+?) ===\s*$", re.MULTILINE)


def extract_diff(raw_text: str) -> str:
    match = DIFF_FENCE.search(raw_text)
    return match.group(1).strip() if match else raw_text.strip()


def parse_rewritten_files(raw_text: str) -> dict[str, str]:
    """Splits the model output into {repo-relative path: new content}."""
    matches = list(FILE_SECTION.finditer(raw_text))
    if not matches:
        return {}
    rewrites: dict[str, str] = {}
    for i, m in enumerate(matches):
        path = m.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        content = raw_text[m.end() : end].strip("\n")
        if path:
            rewrites[path] = content
    return rewrites


def build_patch_from_rewrites(
    files: list[tuple[str, str]], rewrites: dict[str, str]
) -> str:
    """Diffs original vs rewritten content into one unified diff. Files
    whose content is unchanged are skipped."""
    hunks = []
    for rel, original in files:
        new = rewrites.get(rel)
        if new is None or new == original:
            continue
        if not new.endswith("\n"):
            new += "\n"
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        hunks.append("".join(diff))
    return "\n".join(h for h in hunks if h.strip())
