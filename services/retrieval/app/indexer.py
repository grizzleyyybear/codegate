"""Walks a repo, chunks source files (function/class granularity via
tree-sitter, falling back to fixed-size chunks for non-code files), embeds
each chunk, and writes it to the vector store.
"""
from __future__ import annotations

import os
import re
from typing import Any, cast

from .embedder import embed
from .vector_store import upsert_chunks

CHUNK_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".sql", ".md"}

# tree-sitter node types that delimit a meaningful chunk per language.
_TOP_LEVEL_TYPES = {
    "python": {
        "function_definition",
        "class_definition",
        "import_statement",
        "import_from_statement",
    },
    "typescript": {
        "function_declaration",
        "class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "import_statement",
        "export_statement",
    },
    "tsx": {
        "function_declaration",
        "class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "import_statement",
        "export_statement",
        "jsx_element",
    },
    "javascript": {
        "function_declaration",
        "class_declaration",
        "import_statement",
        "export_statement",
    },
}

_LANG_BY_EXT = {".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript"}

_FIXED_SIZE = 1500

_TOP_LEVEL_RE = re.compile(
    r"(?m)^(?:async\s+)?def\s+\w+|^class\s+\w+|^import\s+\w+|^from\s+\w+"
)


def _is_skipped_dir(root: str) -> bool:
    parts = set(root.split(os.sep))
    return bool(parts & {".git", "node_modules", "venv", ".venv", "__pycache__", "dist"})


def _walk_files(repo_path: str):
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "venv", ".venv", "__pycache__", "dist"}]
        if _is_skipped_dir(root):
            continue
        for f in files:
            if os.path.splitext(f)[1] in CHUNK_EXTENSIONS:
                yield os.path.join(root, f)


def _get_parser(ext: str):
    """Lazily import the language pack so the module loads even if the
    optional grammar dependency is missing (falls back to fixed-size)."""
    lang = _LANG_BY_EXT.get(ext)
    if not lang:
        return None, None
    try:
        from tree_sitter_language_pack import get_parser

        return cast(Any, get_parser)(lang), _TOP_LEVEL_TYPES[lang]
    except Exception:  # noqa: BLE001 — bindings missing/failing is a fallback trigger
        return None, None


def _tree_sitter_chunks(text: str, parser, top_level_types: set[str]) -> list[str]:
    tree = parser.parse(text.encode("utf-8"))
    chunks = []
    for node in tree.root_node.children:
        if node.type in top_level_types and node.end_byte > node.start_byte:
            chunk = text[node.start_byte : node.end_byte].strip()
            if chunk:
                chunks.append(chunk)
    return chunks


def _regex_chunks(text: str) -> list[str]:
    """Pure-Python fallback used when the tree-sitter bindings aren't
    available (some Windows installs). Splits on top-level def/class/
    import lines so code files still chunk at function granularity."""
    matches = list(_TOP_LEVEL_RE.finditer(text))
    if len(matches) < 2:
        return []
    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _fixed_size_chunks(text: str) -> list[str]:
    return [text[i : i + _FIXED_SIZE] for i in range(0, len(text), _FIXED_SIZE)] or [""]


def _chunk_file(path: str) -> list[str]:
    with open(path, errors="ignore") as fh:
        text = fh.read()

    ext = os.path.splitext(path)[1]
    parser, top_level_types = _get_parser(ext)
    if parser and text.strip():
        try:
            chunks = _tree_sitter_chunks(text, parser, top_level_types)
            if chunks:
                return chunks
        except Exception:  # noqa: BLE001, S110 — fall back to regex/fixed-size chunking
            pass

    if ext in _LANG_BY_EXT:
        chunks = _regex_chunks(text)
        if chunks:
            return chunks
    return _fixed_size_chunks(text)


async def index_repository(repo: str, repo_path: str) -> int:
    rows = []
    for path in _walk_files(repo_path):
        for chunk in _chunk_file(path):
            if not chunk.strip():
                continue
            rows.append((path, chunk))

    if not rows:
        return 0

    embeddings = embed([content for _, content in rows])
    upsert_rows = [(fp, content, emb) for (fp, content), emb in zip(rows, embeddings)]
    return upsert_chunks(repo, upsert_rows)
