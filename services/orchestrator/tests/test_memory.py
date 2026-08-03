from app.agents import memory


def test_record_outcome_inserts_and_upserts(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "mem.db"))
    memory.record_outcome("i1", "repo", "add rate limiting", "reject", 0.2, attempts=1)
    memory.record_outcome("i1", "repo", "add rate limiting", "auto_merge", 0.9, attempts=3)
    rows = memory.similar_tasks("add rate limiting", "repo", k=5)
    assert len(rows) == 1
    assert rows[0]["action"] == "auto_merge"
    assert rows[0]["attempts"] == 3
    assert rows[0]["confidence"] == 0.9


def test_similar_tasks_ranks_by_overlap_and_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "mem.db"))
    memory.record_outcome("i1", "repoA", "fix the auth login flow", "auto_merge", 0.9)
    memory.record_outcome("i2", "repoB", "fix the auth login flow", "reject", 0.1)
    memory.record_outcome("i3", "repoA", "shipping boxes", "reject", 0.1)
    rows = memory.similar_tasks("fix the auth login flow", "repoA", k=5)
    assert [r["intent_id"] for r in rows] == ["i1", "i2"]
    assert memory.similar_tasks("zzz zzz zzz", "repoA") == []
    assert memory.similar_tasks("", "repoA") == []
    assert memory.similar_tasks("fix the auth login flow", "repoA", k=1)[0]["intent_id"] == "i1"


def test_lessons_for_formats_outcomes(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "mem.db"))
    assert memory.lessons_for("fix auth", "repoA") == ""

    memory.record_outcome(
        "i1", "repoA", "fix the auth login flow", "auto_merge", 0.9,
        attempts=3, reasoning="tests passed after retry",
    )
    lessons = memory.lessons_for("fix the auth login flow", "repoA")
    assert "succeeded and auto-merged" in lessons
    assert "after 3 attempts" in lessons
    assert "tests passed after retry" in lessons

    memory.record_outcome("i2", "repoA", "fix the auth login flow", "human_rejected", 0.6)
    lessons = memory.lessons_for("fix the auth login flow", "repoA")
    assert "rejected by a human reviewer" in lessons

    memory.record_outcome("i3", "repoA", "fix the auth login flow", "human_approved", 0.6)
    lessons = memory.lessons_for("fix the auth login flow", "repoA")
    assert "approved by a human reviewer" in lessons
