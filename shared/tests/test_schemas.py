from shared.schemas import (
    CodegenRequest,
    CodePatch,
    GuardrailAction,
    GuardrailDecision,
    IntentRequest,
    Plan,
    PlanStep,
    RetrievedChunk,
    ValidationResult,
)


def test_intent_request_defaults():
    intent = IntentRequest(intent_id="i1", repo="r", prompt="p", submitted_by="u")
    assert intent.created_at is not None
    dump = intent.model_dump(mode="json")
    assert dump["intent_id"] == "i1"


def test_plan_step_default_target_files():
    step = PlanStep(step_id="1", description="d")
    assert step.target_files == []


def test_plan_defaults_context():
    plan = Plan(intent_id="i", steps=[], repo="r")
    assert plan.context == []
    assert plan.repo == "r"


def test_retrieved_chunk_round_trip():
    chunk = RetrievedChunk(file_path="a.py", content="x = 1", similarity=0.5)
    dumped = chunk.model_dump()
    assert RetrievedChunk(**dumped) == chunk


def test_code_patch_accepts_model_used():
    patch = CodePatch(
        intent_id="i",
        diff="d",
        model_used="deepseek-r1",
        prompt_tokens=1,
        completion_tokens=2,
    )
    assert patch.model_used == "deepseek-r1"
    assert patch.repo == ""


def test_codegen_request_defaults():
    plan = Plan(intent_id="i", steps=[])
    req = CodegenRequest(plan=plan)
    assert req.feedback is None
    assert req.escalate is False


def test_validation_result_fields():
    v = ValidationResult(
        intent_id="i",
        static_analysis_passed=True,
        tests_passed=False,
        test_output="",
        llm_judge_score=0.5,
        llm_judge_reasoning="r",
        confidence=0.4,
    )
    assert v.llm_judge_score == 0.5


def test_guardrail_action_enum_values():
    assert GuardrailAction.AUTO_MERGE.value == "auto_merge"
    assert GuardrailAction.HUMAN_REVIEW.value == "human_review"
    assert GuardrailAction.REJECT.value == "reject"


def test_guardrail_decision_serialization():
    decision = GuardrailDecision(
        intent_id="i",
        action=GuardrailAction.HUMAN_REVIEW,
        reason="touches a sensitive path",
        touches_sensitive_path=True,
    )
    dumped = decision.model_dump(mode="json")
    assert dumped["action"] == "human_review"
    assert dumped["touches_sensitive_path"] is True
