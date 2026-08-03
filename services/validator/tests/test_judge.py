from app.llm_judge import parse_judge_response


def test_parses_pure_json():
    score, reasoning = parse_judge_response('{"score": 0.8, "reasoning": "looks correct"}')
    assert score == 0.8
    assert reasoning == "looks correct"


def test_parses_json_inside_prose():
    raw = 'Sure!\n```json\n{"score": 0.6, "reasoning": "minor scope creep"}\n```\n'
    score, reasoning = parse_judge_response(raw)
    assert score == 0.6
    assert reasoning == "minor scope creep"


def test_clamps_score_to_unit_range():
    score, _ = parse_judge_response('{"score": 1.7, "reasoning": "overconfident"}')
    assert score == 1.0


def test_unparsable_returns_zero_with_raw_reasoning():
    score, reasoning = parse_judge_response("this diff is fine, i think")
    assert score == 0.0
    assert "diff is fine" in reasoning
