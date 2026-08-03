import asyncio
from types import SimpleNamespace

from app import llm_judge
from app.llm_judge import judge_patch

from shared.schemas import CodePatch


class FakeJudgeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
        self.temperatures = []

    async def complete(self, prompt, system=None, temperature=0.3):
        self.prompts.append(prompt)
        self.temperatures.append(temperature)
        raw = self.responses.pop(0)
        return SimpleNamespace(
            text=raw, model="judge-m", prompt_tokens=1, completion_tokens=1, latency_ms=1.0
        )


def _patch():
    return CodePatch(
        intent_id="i1", repo="r", diff="--- a/x\n+++ b/x\n", model_used="m",
        prompt_tokens=0, completion_tokens=0,
    )


def test_judge_takes_median_and_annotates_variance(monkeypatch):
    fake = FakeJudgeClient(
        [
            '{"score": 0.4, "reasoning": "a"}',
            '{"score": 0.9, "reasoning": "b"}',
            '{"score": 0.6, "reasoning": "c"}',
        ]
    )
    monkeypatch.setattr(llm_judge, "get_client", lambda model: fake)
    monkeypatch.setattr(llm_judge, "JUDGE_SAMPLES", 3)

    score, reason = asyncio.run(judge_patch(_patch()))

    assert score == 0.6
    assert reason.startswith("c")
    assert "judge variance high: spread=0.5" in reason
    assert fake.temperatures == [0.0, 0.0, 0.0]
    assert len(fake.prompts) == 3
    assert "--- a/x" in fake.prompts[0]


def test_judge_low_variance_keeps_reason(monkeypatch):
    fake = FakeJudgeClient(
        [
            '{"score": 0.5, "reasoning": "x"}',
            '{"score": 0.55, "reasoning": "y"}',
            '{"score": 0.6, "reasoning": "z"}',
        ]
    )
    monkeypatch.setattr(llm_judge, "get_client", lambda model: fake)
    monkeypatch.setattr(llm_judge, "JUDGE_SAMPLES", 3)

    score, reason = asyncio.run(judge_patch(_patch()))

    assert score == 0.55
    assert reason == "y"
    assert "variance" not in reason
