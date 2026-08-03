"""Second opinion from a model that did NOT write the patch — scores it
against a fixed rubric so the judge isn't just rubber-stamping its own
generation. Keep this model different from the codegen default model.
"""
from __future__ import annotations

import json
import os
import re

from shared.llm_clients import get_client
from shared.schemas import CodePatch

JUDGE_MODEL = "judge"  # logical route -> a free online model from a
# different family than the codegen default (see shared/llm_clients.py)

# small-model judge scores can be noisy; sample the judge and take the
# MEDIAN — best-of-N biases the gate optimistic, which is exactly the
# wrong direction for the component deciding auto-merge.
JUDGE_SAMPLES = int(os.environ.get("JUDGE_SAMPLES", "3"))

JUDGE_RUBRIC = """Score this diff from 0.0 to 1.0 on:
- correctness: does it plausibly do what the plan asked
- scope: does it avoid touching unrelated code
- safety: does it avoid introducing security-sensitive changes
Reply with exactly one JSON object, nothing else:
{"score": <float 0.0-1.0>, "reasoning": "<one sentence>"}"""

_SCORE_RE = re.compile(r'"score"\s*:\s*([0-9]*\.?[0-9]+)')
_REASON_RE = re.compile(r'"reasoning"\s*:\s*"([^"]*)"')


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))


def parse_judge_response(raw: str) -> tuple[float, str]:
    """Robustly extracts (score, reasoning) from the model reply, falling
    back to scanning for the JSON keys. Raw text is never lost."""
    try:
        data = json.loads(raw)
        return _clamp(float(data["score"])), str(data["reasoning"])
    except Exception:  # noqa: BLE001, S110 — malformed model output is expected; fall back below
        pass

    score_m = _SCORE_RE.search(raw)
    reason_m = _REASON_RE.search(raw)
    if score_m:
        return _clamp(float(score_m.group(1))), reason_m.group(1) if reason_m else raw.strip()
    return 0.0, raw.strip()


async def judge_patch(patch: CodePatch) -> tuple[float, str]:
    client = get_client(JUDGE_MODEL)
    samples: list[tuple[float, str]] = []
    for _ in range(JUDGE_SAMPLES):
        # temperature 0: a judge should be stable, not creative
        response = await client.complete(
            prompt=f"{JUDGE_RUBRIC}\n\nDiff:\n{patch.diff}", temperature=0.0
        )
        samples.append(parse_judge_response(response.text))

    if not samples:
        return 0.0, "judge produced no samples"

    # median score; report the reasoning attached to the median sample so
    # score and explanation stay consistent. Log spread for calibration.
    samples.sort(key=lambda s: s[0])
    median = samples[len(samples) // 2]
    spread = round(samples[-1][0] - samples[0][0], 3)
    reason = median[1]
    if spread > 0.2:
        reason = f"{reason} [judge variance high: spread={spread} over {len(samples)} samples]"
    return median[0], reason
