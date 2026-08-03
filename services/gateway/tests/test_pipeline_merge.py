import os
import subprocess

from app import review_queue
from app.pipeline import _auto_merge, _queue_for_review


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


def _patch(repo):
    return {
        "intent_id": "i1",
        "repo": repo,
        "model_used": "deepseek-r1",
        "diff": (
            "--- a/math_utils.py\n"
            "+++ b/math_utils.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def add(a, b):\n"
            "     return a + b\n"
            "+def double(n):\n"
            "+    return 2 * n\n"
        ),
    }


def test_auto_merge_applies_and_commits(tmp_path):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    repo = _make_repo(tmp_path)
    result = _auto_merge(_patch("repo"))
    assert result["merged"] is True, result
    log = subprocess.run(
        ["git", "-C", repo, "log", "--oneline", "-1"],
        capture_output=True, text=True, check=False,
    )
    assert "codegate: i1" in log.stdout
    with open(os.path.join(repo, "math_utils.py")) as fh:
        assert "double" in fh.read()


def test_auto_merge_missing_checkout(tmp_path):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    result = _auto_merge(_patch("nope"))
    assert result["merged"] is False
    assert "not found" in result["detail"]


def test_queue_for_review_persists(tmp_path):
    os.environ["REPOS_ROOT"] = str(tmp_path)
    os.environ["REVIEW_QUEUE_DB"] = str(tmp_path / "reviews.db")
    _make_repo(tmp_path)
    patch = _patch("repo")
    result = _queue_for_review(
        patch,
        {"confidence": 0.5},
        {"reason": "touches a sensitive path"},
        prompt="add a double() helper",
    )
    assert result["queued"] is True
    items = review_queue.list_pending()
    assert items[-1]["intent_id"] == "i1"
    assert items[-1]["diff"] == patch["diff"]
    assert items[-1]["prompt"] == "add a double() helper"


def test_review_decision_flow(tmp_path):
    os.environ["REVIEW_QUEUE_DB"] = str(tmp_path / "reviews.db")
    review_queue.enqueue("i2", "repo", "prompt", "diff", 0.6, "reason")
    assert review_queue.get("i2")["status"] == "pending"
    decided = review_queue.decide("i2", approve=False)
    assert decided["status"] == "rejected"
    assert review_queue.list_pending() == []
    assert review_queue.decide("nope", approve=True) is None
