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


def _full_context_diff(repo_path, added_lines):
    """A real git-diff-style patch: the hunk carries full file context, so
    git apply (which requires trailing context after a change, or EOF)
    accepts it regardless of the change's position in the file."""
    path = os.path.join(repo_path, "repo", "math_utils.py")
    with open(path) as fh:
        lines = fh.read().splitlines()
    n = len(lines)
    new_n = n + len(added_lines)
    ctx = "".join(f" {line}\n" for line in lines)
    add = "".join(f"+{line}\n" for line in added_lines)
    return (
        f"--- a/math_utils.py\n+++ b/math_utils.py\n"
        f"@@ -1,{n} +1,{new_n} @@\n"
        f"{ctx}{add}"
    )


def _good_diff(tmp_path):
    return _full_context_diff(str(tmp_path), ["def double(n):", "    return 2 * n"])


def test_patch_applies_to_fresh_clone(tmp_path):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)
    diff = _good_diff(tmp_path)
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


def test_score_patch_full_path(tmp_path, monkeypatch):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)

    def fake_run_tests(p):
        return (True, "3 passed")

    monkeypatch.setattr(scoring, "run_tests", fake_run_tests)

    async def fake_judge(patch):
        return (0.8, "looks good")

    monkeypatch.setattr(scoring, "judge_patch", fake_judge)

    result = asyncio.run(score_patch(_patch("i10", _good_diff(tmp_path))))

    assert result.static_analysis_passed is True
    assert result.tests_passed is True
    assert result.test_output == "3 passed"
    assert result.llm_judge_score == 0.8
    assert result.confidence == round(0.25 + 0.4 + 0.35 * 0.8, 3)


def test_score_patch_static_failure(tmp_path, monkeypatch):
    """A violation INTRODUCED by the patch fails static analysis even when
    the repo's pre-existing debt is baseline-absorbed."""
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)

    # baseline repo is clean; the patch introduces an undefined-name error
    dirty_diff = _full_context_diff(
        str(tmp_path), ["result = undefined_name"]
    )

    monkeypatch.setattr(scoring, "run_tests", lambda p: (True, "ok"))

    async def fake_judge(patch):
        return (0.9, "fine")

    monkeypatch.setattr(scoring, "judge_patch", fake_judge)

    result = asyncio.run(score_patch(_patch("i11", dirty_diff)))

    assert result.static_analysis_passed is False
    assert result.confidence == round(0.0 + 0.4 + 0.35 * 0.9, 3)
    assert "undefined_name" in result.llm_judge_reasoning


def test_score_patch_preexisting_debt_absorbed(tmp_path, monkeypatch):
    """Baseline-diffing: repo debt that predates the patch does NOT block
    the merge — only new violations do."""
    os.environ["REPOS_ROOT"] = str(tmp_path)
    _make_repo(tmp_path)
    # give the repo pre-existing debt (an undefined name in committed code)
    with open(os.path.join(tmp_path, "repo", "math_utils.py"), "a") as fh:
        fh.write("\nlegacy = undefined_legacy_name\n")
    subprocess.run(["git", "-C", str(tmp_path / "repo"), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path / "repo"), "commit", "-q", "-m", "debt"],
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    monkeypatch.setattr(scoring, "run_tests", lambda p: (True, "ok"))

    async def fake_judge(patch):
        return (0.9, "fine")

    monkeypatch.setattr(scoring, "judge_patch", fake_judge)

    result = asyncio.run(score_patch(_patch("i14", _good_diff(tmp_path))))

    assert result.static_analysis_passed is True
    assert result.confidence == round(0.25 + 0.4 + 0.35 * 0.9, 3)


def test_score_patch_missing_checkout_zero_confidence(tmp_path, monkeypatch):
    os.environ["REPOS_ROOT"] = str(tmp_path)

    async def fake_judge(patch):
        return (0.9, "should not be called")

    monkeypatch.setattr(scoring, "judge_patch", fake_judge)

    result = asyncio.run(score_patch(_patch("i12", "--- a/math_utils.py\n+++ b/math_utils.py\n@@ -1,1 +1,1 @@\n x\n+y\n")))

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
