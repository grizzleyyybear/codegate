"""Codegen agent: builds the prompt from the Plan + retrieved context,
picks a model, calls it, and turns the response into a CodePatch.

Editing strategy: the model rewrites each file in full ("whole-file edit"),
and this agent computes the unified diff itself with difflib. That keeps
hunk headers and line counts correct regardless of model — asking a small
local model to emit exact hunks is unreliable. The diff is the contract
the validator and guardrail consume.
"""
from __future__ import annotations

import os

from shared.llm_clients import get_client
from shared.schemas import CodePatch, Plan

from .patch_builder import build_patch_from_rewrites, parse_rewritten_files
from .prompt_templates import render_codegen_prompt

# cheap-first, escalate-on-low-confidence routing table. Logical role
# names resolved in shared/llm_clients.py to OpenRouter free-tier models.
DEFAULT_MODEL = "codegen-default"
ESCALATION_MODEL = "codegen-escalation"

REPOS_ROOT = os.environ.get("REPOS_ROOT", "/work")


def _read_files(plan: Plan) -> list[tuple[str, str]]:
    """(repo-relative path, current content) for every file mentioned in
    the retrieved context. Paths inside the container look like
    /work/<repo>/<path>."""
    seen: dict[str, str] = {}
    for chunk in plan.context:
        path = chunk.file_path
        if "/" + plan.repo + "/" not in path.replace("\\", "/"):
            continue
        rel = path.split(plan.repo + "/", 1)[1]
        if rel in seen:
            continue
        try:
            with open(path, errors="ignore") as fh:
                seen[rel] = fh.read()
        except OSError:
            continue
    return list(seen.items())


async def generate_patch(
    plan: Plan,
    model_override: str | None = None,
    feedback: str | None = None,
    escalate: bool = False,
) -> CodePatch:
    """Cheap-first routing: use the default model unless the caller asks
    for escalation (a previous attempt failed validation), in which case
    route to the stronger escalation model from a different family."""
    model_name = model_override or (ESCALATION_MODEL if escalate else DEFAULT_MODEL)
    client = get_client(model_name)

    files = _read_files(plan)
    prompt = render_codegen_prompt(plan, files, feedback)
    response = await client.complete(prompt=prompt, system=CODEGEN_SYSTEM_PROMPT)

    rewrites = parse_rewritten_files(response.text)
    diff = build_patch_from_rewrites(files, rewrites)

    return CodePatch(
        intent_id=plan.intent_id,
        repo=plan.repo,
        diff=diff,
        model_used=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
    )


CODEGEN_SYSTEM_PROMPT = """You are a codegen agent. You are given a plan and
grounding context from the target repository. For every file under
"## Files to edit", output the COMPLETE new file content — never a diff.

Strict output contract:
- One section per file, in this exact format:
  === <repo-relative path> ===
  <entire new file content>
- Preserve every unchanged line exactly as-is.
- Do not add commentary, markdown fences, or files not listed."""