from app.test_runner import run_tests


def test_run_tests_passes(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert 1 == 1\n")
    ok, out = run_tests(str(tmp_path))
    assert ok is True
    assert "passed" in out


def test_run_tests_fails(tmp_path):
    (tmp_path / "test_bad.py").write_text("def test_bad():\n    assert False\n")
    ok, out = run_tests(str(tmp_path))
    assert ok is False
    assert "failed" in out
