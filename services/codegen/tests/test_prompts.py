from app.prompt_templates import render_codegen_prompt

from shared.schemas import Plan, PlanStep, RetrievedChunk


def _plan():
    return Plan(
        intent_id="i",
        repo="r",
        steps=[PlanStep(step_id="1", description="add login")],
        context=[RetrievedChunk(file_path="auth.py", content="def login(): pass", similarity=0.9)],
    )


def test_render_without_feedback():
    prompt = render_codegen_prompt(_plan(), [("auth.py", "def login(): pass")])
    assert "add login" in prompt
    assert "auth.py" in prompt
    assert "def login(): pass" in prompt
    assert "Previous attempt failed" not in prompt


def test_render_with_feedback():
    prompt = render_codegen_prompt(
        _plan(), [("auth.py", "def login(): pass")], feedback="tests failed: 1/3"
    )
    assert "Previous attempt failed" in prompt
    assert "tests failed: 1/3" in prompt
    assert "=== auth.py ===" in prompt


def test_render_empty_plan():
    plan = Plan(intent_id="i", repo="r", steps=[], context=[])
    prompt = render_codegen_prompt(plan, [])
    assert "## Files to edit" in prompt
