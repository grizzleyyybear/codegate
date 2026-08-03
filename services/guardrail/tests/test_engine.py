from app.engine import decide

from shared.schemas import CodePatch, GuardrailAction, ValidationResult


def _patch(diff="--- a/foo.py\n+++ b/foo.py\n"):
    return CodePatch(intent_id="i1", diff=diff, model_used="claude", prompt_tokens=1, completion_tokens=1)


def _validation(confidence):
    return ValidationResult(
        intent_id="i1",
        static_analysis_passed=True,
        tests_passed=True,
        test_output="",
        llm_judge_score=confidence,
        llm_judge_reasoning="",
        confidence=confidence,
    )


def test_high_confidence_auto_merges():
    decision = decide(_patch(), _validation(0.95))
    assert decision.action == GuardrailAction.AUTO_MERGE


def test_sensitive_path_forces_human_review():
    decision = decide(_patch(diff="--- a/auth/login.py\n+++ b/auth/login.py\n"), _validation(0.99))
    assert decision.action == GuardrailAction.HUMAN_REVIEW


def test_low_confidence_rejects():
    decision = decide(_patch(), _validation(0.1))
    assert decision.action == GuardrailAction.REJECT
