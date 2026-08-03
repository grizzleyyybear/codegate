"""Codegen service — turns a Plan into an actual diff.

Model routing is the "optimize model, reasoning, latency, cost" bullet
made concrete: try a cheap/fast model first, escalate to a stronger one
only if the plan is flagged complex or a first attempt fails validation.
"""
from fastapi import FastAPI

from shared.otel_setup import setup_otel
from shared.schemas import CodegenRequest, CodePatch

from .agent import generate_patch

setup_otel("codegate-codegen")
app = FastAPI(title="Codegate Codegen")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=CodePatch)
async def generate(req: CodegenRequest) -> CodePatch:
    return await generate_patch(req.plan, feedback=req.feedback, escalate=req.escalate)
