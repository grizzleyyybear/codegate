from app.static_checks import (
    bandit_violations,
    describe_new_violations,
    mypy_violations,
    new_violations,
    ruff_violations,
    run_bandit,
    run_mypy,
    run_ruff,
)


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


def test_ruff_violations_extract_code(tmp_path):
    (tmp_path / "broken.py").write_text("import os\n\nprint(undefined_name)\n")
    v = ruff_violations(str(tmp_path))
    assert ("broken.py", "F821") in v


def test_mypy_violations_extract_path(tmp_path):
    (tmp_path / "bad.py").write_text("x: int = 'not an int'\n")
    v = mypy_violations(str(tmp_path))
    assert any(path == "bad.py" for path, _ in v)


def test_bandit_violations_extract(tmp_path):
    (tmp_path / "unsafe.py").write_text("import subprocess\nsubprocess.call('ls')\n")
    v = bandit_violations(str(tmp_path))
    assert any(code == "B602" or code == "B603" or code == "B607" for _, code in v)


def test_new_violations_diffs_sets():
    baseline = {
        "ruff": {("legacy.py", "E711")},
        "mypy": set(),
        "bandit": set(),
    }
    current = {
        "ruff": {("legacy.py", "E711"), ("new.py", "F401")},
        "mypy": {("new.py", "x is untyped")},
        "bandit": set(),
    }
    new = new_violations(baseline, current)
    assert new["ruff"] == {("new.py", "F401")}
    assert new["mypy"] == {("new.py", "x is untyped")}
    assert new["bandit"] == set()


def test_describe_new_violations_formats():
    out = describe_new_violations(
        {"ruff": {("a.py", "F401"), ("b.py", "E711")}, "mypy": set(), "bandit": set()}
    )
    assert "ruff: a.py: F401" in out
    assert "ruff: b.py: E711" in out
