import asyncio
import os
import subprocess

from app import scoring
from app.scoring import WEIGHTS, _clone_with_patch, score_patch

from shared.schemas import CodePatch


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-6


def _make_repo(tmp_path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "math_utils.py").write_text("def add(a, b):\n    return a + b\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "initial"],
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return str(repo)


def _patch(intent_id, diff):
    return CodePatch(
        intent_id=intent_id, repo="repo", diff=diff, model_used="test",
        prompt_tokens=0, completion_tokens=0,
    )


def test_patch_applies_to_fresh_clone(tmp_path):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)
    diff = (
        "--- a/math_utils.py\n"
        "+++ b/math_utils.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def add(a, b):\n"
        "     return a + b\n"
        "+def double(n):\n"
        "+    return 2 * n\n"
    )
    checkout, error = _clone_with_patch(_patch("i1", diff))
    assert error == "", error
    with open(os.path.join(checkout, "math_utils.py")) as fh:
        assert "double" in fh.read()


def test_patch_that_does_not_apply_fails(tmp_path):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)
    diff = (
        "--- a/missing_file.py\n"
        "+++ b/missing_file.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    checkout, error = _clone_with_patch(_patch("i2", diff))
    assert checkout is None
    assert "patch does not apply" in error


def test_missing_checkout_reports_error(tmp_path):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    patch = CodePatch(
        intent_id="i3", repo="no_such_repo", diff="", model_used="test",
        prompt_tokens=0, completion_tokens=0,
    )
    checkout, error = _clone_with_patch(patch)
    assert checkout is None
    assert "repo checkout not found" in error


def _good_diff():
    return (
        "--- a/math_utils.py\n"
        "+++ b/math_utils.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def add(a, b):\n"
        "     return a + b\n"
        "+def double(n):\n"
        "+    return 2 * n\n"
    )


def test_score_patch_full_path(tmp_path, monkeypatch):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)

    monkeypatch.setattr(scoring, "run_ruff", lambda p: (True, ""))
    monkeypatch.setattr(scoring, "run_mypy", lambda p: (True, ""))
    monkeypatch.setattr(scoring, "run_bandit", lambda p: (True, ""))

    def fake_run_tests(p):
        return (True, "3 passed")

    monkeypatch.setattr(scoring, "run_tests", fake_run_tests)

    async def fake_judge(patch):
        return (0.8, "looks good")

    monkeypatch.setattr(scoring, "judge_patch", fake_judge)

    result = asyncio.run(score_patch(_patch("i10", _good_diff())))

    assert result.static_analysis_passed is True
    assert result.tests_passed is True
    assert result.test_output == "3 passed"
    assert result.llm_judge_score == 0.8
    assert result.confidence == round(0.25 + 0.4 + 0.35 * 0.8, 3)


def test_score_patch_static_failure(tmp_path, monkeypatch):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)

    monkeypatch.setattr(scoring, "run_ruff", lambda p: (False, "ruff error"))
    monkeypatch.setattr(scoring, "run_mypy", lambda p: (True, ""))
    monkeypatch.setattr(scoring, "run_bandit", lambda p: (True, ""))
    monkeypatch.setattr(scoring, "run_tests", lambda p: (True, "ok"))

    async def fake_judge(patch):
        return (0.9, "fine")

    monkeypatch.setattr(scoring, "judge_patch", fake_judge)

    result = asyncio.run(score_patch(_patch("i11", _good_diff())))

    assert result.static_analysis_passed is False
    assert result.confidence == round(0.0 + 0.4 + 0.35 * 0.9, 3)


def test_score_patch_missing_checkout_zero_confidence(tmp_path, monkeypatch):
    os.environ["REPOS_ROOT"] = str(tmp_path)

    async def fake_judge(patch):
        return (0.9, "should not be called")

    monkeypatch.setattr(scoring, "judge_patch", fake_judge)

    result = asyncio.run(score_patch(_patch("i12", _good_diff())))

    assert result.confidence == 0.0
    assert result.tests_passed is False
    assert "repo checkout not found" in result.llm_judge_reasoning


def test_score_patch_patch_does_not_apply(tmp_path, monkeypatch):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)

    diff = (
        "--- a/missing_file.py\n"
        "+++ b/missing_file.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )

    async def fake_judge(patch):
        return (0.9, "should not be called")

    monkeypatch.setattr(scoring, "judge_patch", fake_judge)

    result = asyncio.run(score_patch(_patch("i13", diff)))

    assert result.confidence == 0.0
    assert "patch does not apply" in result.llm_judge_reasoning
