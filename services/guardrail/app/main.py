"""Guardrail service — the "governance, escalation, and human-AI
collaboration patterns for production AI systems" bullet, made concrete.

Takes a ValidationResult (+ the patch, to check touched paths) and
returns a GuardrailDecision: auto-merge, human review, or reject.
This is the one service every other service's output has to pass
through before anything reaches CI/CD.
"""
from fastapi import FastAPI

from shared.otel_setup import setup_otel
from shared.schemas import CodePatch, GuardrailDecision, ValidationResult

from .engine import decide

setup_otel("codegate-guardrail")
app = FastAPI(title="Codegate Guardrail")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/decide", response_model=GuardrailDecision)
async def decide_route(patch: CodePatch, validation: ValidationResult) -> GuardrailDecision:
    return decide(patch, validation)
