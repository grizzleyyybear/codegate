"""Turns a scoped intent plus retrieved context into an ordered Plan the
codegen agent can execute step by step.

Uses a free online model (the "planner" route in shared/llm_clients.py)
to propose ordered steps with target files. If the call or parsing fails,
falls back to a single-step plan wrapping the raw prompt — the pipeline
never blocks on the planner.
"""
from __future__ import annotations

import json
import re

from shared.llm_clients import get_client
from shared.schemas import Plan, PlanStep

from . import memory

PLANNER_SYSTEM = """You are a planning agent for a code-modification pipeline.
Given a task and code context from the target repo, break the task into a
short ordered list of concrete implementation steps (1-5 steps).

Reply with exactly one JSON array, nothing else:
[{"description": "<what to do>", "target_files": ["<repo-relative path>", ...]}]

Only list files that appear in the provided context. Keep steps small and
independently verifiable."""

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _parse_steps(raw: str) -> list[PlanStep]:
    match = _JSON_ARRAY_RE.search(raw)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    steps = []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not item.get("description"):
            continue
        files = item.get("target_files") or []
        steps.append(
            PlanStep(
                step_id=str(i),
                description=str(item["description"]),
                target_files=[str(f) for f in files if isinstance(f, str)],
            )
        )
    return steps


async def plan_steps(state: dict) -> dict:
    intent = state["intent"]
    context = state.get("context", [])
    feedback = state.get("feedback", "")

    steps: list[PlanStep] = []
    try:
        client = get_client("planner")
        context_block = "\n\n".join(
            f"--- {c['file_path']} ---\n{c['content'][:1200]}"
            for c in context[:8]
        )
        sections = [f"Task: {intent.prompt}"]
        # persistent memory: lessons from similar past runs in this repo
        try:
            lessons = memory.lessons_for(intent.prompt, intent.repo)
        except Exception:  # noqa: BLE001 — memory is advisory, never fatal
            lessons = ""
        if lessons:
            sections.append(lessons)
        # mid-task goal re-formulation: a previous plan failed validation,
        # so revise the approach instead of restating the same steps
        if feedback:
            sections.append(
                "A previous plan for this task FAILED validation with the "
                f"output below. Re-formulate the approach to avoid the same "
                f"failure — change strategy, not just wording:\n{feedback[:2000]}"
            )
        sections.append(
            f"Repository context:\n{context_block}" if context_block
            else "(no repository context retrieved)"
        )
        response = await client.complete(prompt="\n\n".join(sections), system=PLANNER_SYSTEM)
        steps = _parse_steps(response.text)
    except Exception:  # noqa: BLE001 — planner is best-effort; fall back below
        steps = []

    if not steps:
        steps = [PlanStep(step_id="1", description=intent.prompt, target_files=[])]

    state["plan"] = Plan(intent_id=intent.intent_id, repo=intent.repo, steps=steps, context=context)
    return state
