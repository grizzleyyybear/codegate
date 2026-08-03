"""Shared pydantic models used across every Codegate service.

Every service imports from here instead of redefining its own version of
these objects. Keep this file dependency-free (pydantic only) so it can be
imported by any service without pulling in that service's own deps.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class IntentRequest(BaseModel):
    """A natural-language task submitted to the pipeline."""

    intent_id: str
    repo: str
    prompt: str
    submitted_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RetrievedChunk(BaseModel):
    """One piece of grounding context pulled from the codebase index."""

    file_path: str
    content: str
    similarity: float


class PlanStep(BaseModel):
    step_id: str
    description: str
    target_files: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    intent_id: str
    repo: str = ""
    steps: list[PlanStep]
    context: list[RetrievedChunk] = Field(default_factory=list)


class PlanRequest(BaseModel):
    """Body for POST /plan: the intent, plus optional validator failure
    feedback when the gateway asks for a mid-task re-formulation of the
    goal (replan) instead of a blind retry."""

    intent: IntentRequest
    feedback: str | None = None


class TaskOutcome(BaseModel):
    """Body for POST /outcome: how a pipeline run ended. Recorded in the
    orchestrator's persistent task memory so future plans for similar
    intents start with lessons learned."""

    intent_id: str
    repo: str = ""
    prompt: str = ""
    action: str  # auto_merge / human_review / reject
    confidence: float = 0.0
    attempts: int = 1
    reasoning: str = ""


class CodePatch(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    intent_id: str
    repo: str = ""
    diff: str
    model_used: str
    prompt_tokens: int
    completion_tokens: int


class CodegenRequest(BaseModel):
    """Body for POST /generate: the plan plus optional failure feedback
    from the validator, so a retry can fix the previous attempt."""

    plan: Plan
    feedback: str | None = None
    escalate: bool = False  # retry with the stronger escalation model


class ValidationResult(BaseModel):
    intent_id: str
    static_analysis_passed: bool
    tests_passed: bool
    test_output: str
    llm_judge_score: float  # 0-1
    llm_judge_reasoning: str
    confidence: float  # aggregate 0-1, drives the guardrail decision


class GuardrailAction(str, Enum):
    AUTO_MERGE = "auto_merge"
    HUMAN_REVIEW = "human_review"
    REJECT = "reject"


class GuardrailDecision(BaseModel):
    intent_id: str
    action: GuardrailAction
    reason: str
    touches_sensitive_path: bool
