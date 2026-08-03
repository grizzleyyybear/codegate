from app.static_checks import run_bandit, run_mypy, run_ruff


def test_ruff_clean_file(tmp_path):
    (tmp_path / "clean.py").write_text("x = 1\n")
    ok, _ = run_ruff(str(tmp_path))
    assert ok is True


def test_ruff_flags_error(tmp_path):
    (tmp_path / "broken.py").write_text("import os\n\nprint(undefined_name)\n")
    ok, out = run_ruff(str(tmp_path))
    assert ok is False
    assert "undefined_name" in out


def test_mypy_clean_file(tmp_path):
    (tmp_path / "typed.py").write_text("x: int = 1\n")
    ok, _ = run_mypy(str(tmp_path))
    assert ok is True


def test_mypy_flags_type_error(tmp_path):
    (tmp_path / "bad.py").write_text("x: int = 'not an int'\n")
    ok, out = run_mypy(str(tmp_path))
    assert ok is False
    assert "error" in out.lower()


def test_bandit_clean_file(tmp_path):
    (tmp_path / "safe.py").write_text("def add(a, b):\n    return a + b\n")
    ok, _ = run_bandit(str(tmp_path))
    assert ok is True
