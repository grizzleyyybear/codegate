import os
import subprocess

from app.scoring import WEIGHTS, _clone_with_patch

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
