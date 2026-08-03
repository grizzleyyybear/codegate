from app.indexer import _chunk_file, _fixed_size_chunks, _walk_files


def _write(tmp_path, rel, content):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return str(target)


def test_fixed_size_chunks_splits_long_text():
    chunks = _fixed_size_chunks("a" * 5000)
    assert len(chunks) == 4
    assert all(len(c) <= 1500 for c in chunks)


def test_python_file_chunks_at_function_granularity(tmp_path):
    code = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "class Calculator:\n"
        "    def multiply(self, a, b):\n"
        "        return a * b\n"
    )
    path = _write(tmp_path, "math_utils.py", code)
    chunks = _chunk_file(path)
    assert len(chunks) >= 2
    assert any("def add" in c for c in chunks)
    assert any("class Calculator" in c for c in chunks)


def test_non_code_file_falls_back_to_fixed_size(tmp_path):
    path = _write(tmp_path, "notes.md", "# heading\n\n" + "word " * 100)
    assert _chunk_file(path)


def test_walk_skips_git_and_node_modules(tmp_path):
    _write(tmp_path, ".git/config", "[core]\n")
    _write(tmp_path, "node_modules/pkg/index.js", "x = 1")
    _write(tmp_path, "app/main.py", "def main():\n    pass\n")
    _write(tmp_path, "app/notes.md", "hello")
    files = list(_walk_files(str(tmp_path)))
    assert all(".git" not in f and "node_modules" not in f for f in files)
    assert len(files) == 2
