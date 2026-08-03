"""Validator service — the JD's "validate AI-generated code and outputs
for correctness, safety, quality, and relevance" bullet, made concrete.

/validate takes a CodePatch, runs static analysis + the generated/existing
test suite + an LLM-judge pass, and returns a ValidationResult with a
single confidence score the guardrail service acts on.
"""
from fastapi import FastAPI

from shared.otel_setup import setup_otel
from shared.schemas import CodePatch, ValidationResult

from .scoring import score_patch

setup_otel("codegate-validator")
app = FastAPI(title="Codegate Validator")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/validate", response_model=ValidationResult)
async def validate(patch: CodePatch) -> ValidationResult:
    return await score_patch(patch)
