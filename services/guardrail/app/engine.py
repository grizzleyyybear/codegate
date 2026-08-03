from __future__ import annotations

from shared.schemas import (
    CodePatch,
    GuardrailAction,
    GuardrailDecision,
    ValidationResult,
)

from .policies.confidence_threshold import AUTO_MERGE_THRESHOLD, REJECT_THRESHOLD
from .policies.sensitive_paths import touches_sensitive_path


def decide(patch: CodePatch, validation: ValidationResult) -> GuardrailDecision:
    sensitive = touches_sensitive_path(patch.diff)

    if validation.confidence < REJECT_THRESHOLD:
        action, reason = GuardrailAction.REJECT, "confidence below reject threshold"
    elif sensitive:
        action, reason = GuardrailAction.HUMAN_REVIEW, "touches a sensitive path"
    elif validation.confidence >= AUTO_MERGE_THRESHOLD:
        action, reason = GuardrailAction.AUTO_MERGE, "confidence above auto-merge threshold"
    else:
        action, reason = GuardrailAction.HUMAN_REVIEW, "confidence below auto-merge threshold"

    return GuardrailDecision(
        intent_id=patch.intent_id,
        action=action,
        reason=reason,
        touches_sensitive_path=sensitive,
    )
