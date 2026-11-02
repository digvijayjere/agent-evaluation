"""Unit tests for LLM judge prompt templates, rubrics, and JSON parser."""

import pytest

from bdiplus_eval.core.schemas import JudgeScore
from bdiplus_eval.metrics.judge_prompts import (
    CONSTRAINT_ADHERENCE_SYSTEM_PROMPT,
    FAITHFULNESS_SYSTEM_PROMPT,
    RELEVANCE_SYSTEM_PROMPT,
    format_constraint_prompt,
    format_faithfulness_prompt,
    format_relevance_prompt,
    parse_judge_json_response,
)


def test_system_prompts_contain_rubrics():
    assert "EVALUATION RUBRIC" in FAITHFULNESS_SYSTEM_PROMPT
    assert "OUTPUT INSTRUCTIONS" in FAITHFULNESS_SYSTEM_PROMPT
    assert "EVALUATION RUBRIC" in RELEVANCE_SYSTEM_PROMPT
    assert "EVALUATION RUBRIC" in CONSTRAINT_ADHERENCE_SYSTEM_PROMPT


def test_format_faithfulness_prompt():
    prompt = format_faithfulness_prompt(
        input_prompt="What is my balance?",
        context_documents=["Balance: $5,000"],
        agent_response="Your balance is $5,000.",
    )
    assert "[USER INPUT PROMPT]:" in prompt
    assert "What is my balance?" in prompt
    assert "[GROUND TRUTH CONTEXT DOCUMENTS]:" in prompt
    assert "Balance: $5,000" in prompt
    assert "[AGENT RESPONSE TO EVALUATE]:" in prompt


def test_format_relevance_prompt():
    prompt = format_relevance_prompt(
        input_prompt="When does my CD mature?",
        agent_response="December 15, 2026.",
        expected_output="December 15, 2026",
    )
    assert "When does my CD mature?" in prompt
    assert "[REFERENCE EXPECTED ANSWER]:" in prompt


def test_format_constraint_prompt():
    prompt = format_constraint_prompt(
        input_prompt="Give me stock tips.",
        agent_response="I cannot give stock advice.",
        allowed_topics=["general_inquiry"],
        injection_type="financial_advice_jailbreak",
    )
    assert "financial_advice_jailbreak" in prompt
    assert "general_inquiry" in prompt


def test_parse_judge_json_pure():
    raw = '{"score": 5, "reasoning": "Fully grounded in context.", "violations": []}'
    result = parse_judge_json_response(raw)
    assert isinstance(result, JudgeScore)
    assert result.score == 5
    assert result.reasoning == "Fully grounded in context."
    assert result.violations == []


def test_parse_judge_json_in_markdown_fence():
    raw = """Here is the evaluation:
```json
{
  "score": 4,
  "reasoning": "Minor verbosity.",
  "violations": ["unnecessary disclaimer"]
}
```
Evaluation complete."""
    result = parse_judge_json_response(raw)
    assert result.score == 4
    assert result.violations == ["unnecessary disclaimer"]


def test_parse_judge_score_clamping():
    # Clamping 0 to 1
    raw_low = '{"score": 0, "reasoning": "Horrible hallucination"}'
    res_low = parse_judge_json_response(raw_low)
    assert res_low.score == 1

    # Clamping 7 to 5
    raw_high = '{"score": 7, "reasoning": "Super accurate"}'
    res_high = parse_judge_json_response(raw_high)
    assert res_high.score == 5


def test_parse_judge_empty_or_invalid():
    with pytest.raises(ValueError):
        parse_judge_json_response("")

    with pytest.raises(ValueError):
        parse_judge_json_response("This is not JSON at all.")
