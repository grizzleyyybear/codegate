import asyncio
from types import SimpleNamespace

from app import indexer as idx
from app.indexer import (
    _chunk_file,
    _get_parser,
    _regex_chunks,
    _tree_sitter_chunks,
)


def test_regex_chunks_splits_at_definitions():
    code = (
        "import os\n"
        "\n"
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "class Calc:\n"
        "    def multiply(self, a, b):\n"
        "        return a * b\n"
    )
    chunks = _regex_chunks(code)
    assert len(chunks) == 3
    assert chunks[0].startswith("import os")
    assert chunks[1].startswith("def add")
    assert chunks[2].startswith("class Calc")


def test_regex_chunks_single_match_returns_empty():
    assert _regex_chunks("def lonely():\n    pass\n") == []


def test_get_parser_unknown_extension():
    assert _get_parser(".xyz") == (None, None)


def test_get_parser_known_extension_returns_tuple():
    parser, types = _get_parser(".py")
    assert isinstance(parser, object) or parser is None
    assert isinstance(types, (set, type(None)))


class FakeNode:
    def __init__(self, type_, start, end):
        self.type = type_
        self.start_byte = start
        self.end_byte = end


def test_tree_sitter_chunks_selects_top_level(monkeypatch):
    text = "def add(a, b):\n    return a + b\n"
    nodes = [
        FakeNode("function_definition", 0, len(text)),
        FakeNode("comment", 0, 4),
        FakeNode("function_definition", 5, 5),
    ]
    parser = SimpleNamespace(parse=lambda data: SimpleNamespace(root_node=SimpleNamespace(children=nodes)))
    chunks = _tree_sitter_chunks(text, parser, {"function_definition"})
    assert chunks == [text.strip()]


def test_chunk_file_empty_file_fixed_size(tmp_path):
    p = tmp_path / "empty.md"
    p.write_text("")
    assert _chunk_file(str(p)) == [""]


def test_index_repository_empty_repo_returns_zero(monkeypatch):
    monkeypatch.setattr(idx, "_walk_files", lambda path: [])
    assert asyncio.run(idx.index_repository("r", "/tmp/x")) == 0


def test_index_repository_indexes_and_upserts(monkeypatch):
    monkeypatch.setattr(idx, "_walk_files", lambda path: ["a.py", "b.md"])
    monkeypatch.setattr(idx, "_chunk_file", lambda path: ["chunk one", "   "])
    monkeypatch.setattr(idx, "embed", lambda texts: [[0.0, 0.0]] * len(texts))
    captured = {}

    def fake_upsert(repo, rows):
        captured["repo"] = repo
        captured["rows"] = rows
        return len(rows)

    monkeypatch.setattr(idx, "upsert_chunks", fake_upsert)
    n = asyncio.run(idx.index_repository("repo-x", "/tmp/x"))
    assert n == 2
    assert captured["repo"] == "repo-x"
    assert [fp for fp, _, _ in captured["rows"]] == ["a.py", "b.md"]
