"""Phase 2 Acceptance Test: Scoring Engines & Evaluation Harness Verification.

Terminal command:
    pytest tests/unit/test_phase2_scoring.py -v
"""

import pytest

from bdiplus_eval.core.agent_client import MockAgent, create_agent_client
from bdiplus_eval.core.schemas import (
    DomainSegment,
    EvalTestCase,
    InputCategory,
    JudgeScore,
    PriorityTier,
)
from bdiplus_eval.metrics.deterministic import (
    calculate_entity_metrics,
    calculate_exact_match,
    calculate_latency_stats,
    validate_json_schema,
)
from bdiplus_eval.metrics.judge_client import JudgeClient, MockJudgeProvider
from bdiplus_eval.metrics.judge_prompts import (
    CONSTRAINT_ADHERENCE_SYSTEM_PROMPT,
    FAITHFULNESS_SYSTEM_PROMPT,
    RELEVANCE_SYSTEM_PROMPT,
    parse_judge_json_response,
)


def test_deterministic_scoring_fixtures():
    """Verify deterministic metrics calculations."""
    # Exact Match
    assert calculate_exact_match("Result A", "result a") == 1.0
    assert calculate_exact_match("Result A", "Result B") == 0.0

    # Entity Precision, Recall, F1
    expected = [
        {"type": "acct", "value": "1234"},
        {"type": "balance", "value": "$500"},
    ]
    actual_full = [
        {"type": "acct", "value": "1234"},
        {"type": "balance", "value": "$500"},
    ]
    p, r, f1 = calculate_entity_metrics(actual_full, expected)
    assert p == 1.0 and r == 1.0 and f1 == 1.0

    # Latency Stats
    stats = calculate_latency_stats([100.0, 200.0, 300.0, 400.0, 500.0])
    assert stats["p50"] == 300.0
    assert stats["min"] == 100.0
    assert stats["max"] == 500.0


def test_judge_rubrics_and_parser():
    """Verify LLM-as-a-judge prompt templates, rubrics, and clamping."""
    assert "EVALUATION RUBRIC" in FAITHFULNESS_SYSTEM_PROMPT
    assert "EVALUATION RUBRIC" in RELEVANCE_SYSTEM_PROMPT
    assert "EVALUATION RUBRIC" in CONSTRAINT_ADHERENCE_SYSTEM_PROMPT

    raw_fence = """```json
{"score": 6, "reasoning": "Exceeded max range", "violations": []}
```"""
    score = parse_judge_json_response(raw_fence)
    assert score.score == 5  # Clamped to 5


def test_judge_retry_and_resilience():
    """Verify JudgeClient retry mechanism on transient network failure."""
    calls = 0

    class FailingProvider:
        def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0, seed: int = 42) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("Simulated timeout")
            return '{"score": 5, "reasoning": "Success after retry", "violations": []}'

    judge = JudgeClient(provider=FailingProvider(), max_retries=3)
    res = judge.evaluate_relevance("Prompt", "Response")
    assert calls == 2
    assert res.score == 5


def test_pytest_cli_and_fixtures(eval_config, agent_client, eval_judge):
    """Verify pytest plugin recognized custom CLI arguments and instantiated fixtures."""
    assert "agent_endpoint" in eval_config
    assert "suite" in eval_config
    assert "gate" in eval_config
    assert "gate_threshold" in eval_config
    assert isinstance(agent_client, MockAgent)
    assert isinstance(eval_judge, JudgeClient)


def test_evaluation_test_case_execution():
    """Verify executing evaluation on a single test case with mock agent and judge."""
    agent = create_agent_client("mock://compliant")
    judge = JudgeClient(provider=MockJudgeProvider())

    tc = EvalTestCase(
        test_case_id="TC-PHASE2-TEST",
        domain_segment=DomainSegment.RETAIL_BANKING,
        input_category=InputCategory.EXPECTED,
        priority=PriorityTier.P1,
        input_prompt="What is my balance?",
        context_documents=["Balance: $750.00"],
        expected_output="Your balance is $750.00.",
        expected_entities=[{"type": "balance", "value": "$750.00"}],
    )

    response = agent.invoke(tc)
    assert response.status_code == 200

    judge_scores = judge.evaluate_all(tc, response)
    assert "faithfulness" in judge_scores
    assert "relevance" in judge_scores
    assert "constraint_adherence" in judge_scores
    assert judge_scores["faithfulness"].score == 5
