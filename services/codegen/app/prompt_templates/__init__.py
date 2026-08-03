from __future__ import annotations

from shared.schemas import Plan


def render_codegen_prompt(
    plan: Plan, files: list[tuple[str, str]], feedback: str | None = None
) -> str:
    context_block = "\n\n".join(
        f"# {c.file_path}\n{c.content}" for c in plan.context
    )
    files_block = "\n\n".join(f"=== {rel} ===\n{content}" for rel, content in files)
    steps_block = "\n".join(f"- {s.description}" for s in plan.steps)
    feedback_block = ""
    if feedback:
        feedback_block = (
            "\n\n## Previous attempt failed\n"
            "Your previous attempt failed validation:\n"
            f"{feedback}\n\n"
            "Fix the reported problem and output the corrected full files "
            "again, every file under its === <path> === header."
        )
    return CODEGEN_PROMPT.format(
        steps=steps_block,
        context=context_block,
        files=files_block,
        feedback=feedback_block,
    )


CODEGEN_PROMPT = """## Plan
{steps}

## Grounding context
{context}

## Files to edit
For each file below, output the COMPLETE new file content under a
"=== <path> ===" header. Do not emit diffs.

Rules:
- Keep every existing line byte-for-byte unless the change requires editing it.
- Preserve all existing blank lines and PEP8 spacing between functions.
- If the change needs a new import, add it to the existing import statement;
  never call a function that is not imported.
- Rewrite ALL files listed below, even if only one needs changes.
{feedback}
{files}"""
