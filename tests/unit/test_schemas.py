"""Unit tests for Pydantic data schemas and enums."""

import pytest
from pydantic import ValidationError

from agent_eval.core.schemas import (
    DomainSegment,
    InputCategory,
    PriorityTier,
    EvalTestCase,
    AgentResponse,
    JudgeScore,
    TestCaseResult,
    GlobalMetricSummary,
)


def test_valid_eval_test_case():
    tc = EvalTestCase(
        test_case_id="TC-BANK-001",
        domain_segment=DomainSegment.RETAIL_BANKING,
        input_category=InputCategory.EXPECTED,
        priority=PriorityTier.P1,
        input_prompt="What is my checking account balance?",
        context_documents=["Account 12345 balance: $1,250.00."],
        expected_output="Your current checking account balance is $1,250.00.",
        expected_entities=[{"type": "balance", "value": "$1,250.00"}],
    )
    assert tc.test_case_id == "TC-BANK-001"
    assert tc.domain_segment == DomainSegment.RETAIL_BANKING
    assert tc.input_category == InputCategory.EXPECTED
    assert tc.priority == PriorityTier.P1
    assert len(tc.context_documents) == 1
    assert tc.expected_entities[0]["value"] == "$1,250.00"


def test_invalid_test_case_id():
    with pytest.raises(ValidationError):
        EvalTestCase(
            test_case_id="INVALID ID WITH SPACES!",
            domain_segment=DomainSegment.RETAIL_BANKING,
            input_category=InputCategory.EXPECTED,
            input_prompt="Test prompt",
        )


def test_invalid_domain_segment():
    with pytest.raises(ValidationError):
        EvalTestCase(
            test_case_id="TC-001",
            domain_segment="invalid_domain",  # type: ignore
            input_category=InputCategory.EXPECTED,
            input_prompt="Test prompt",
        )


def test_judge_score_valid_and_bounds():
    valid = JudgeScore(score=5, reasoning="Fully faithful to reference", violations=[])
    assert valid.score == 5
    assert len(valid.violations) == 0

    # Score below 1 must fail
    with pytest.raises(ValidationError):
        JudgeScore(score=0, reasoning="Below range")

    # Score above 5 must fail
    with pytest.raises(ValidationError):
        JudgeScore(score=6, reasoning="Above range")


def test_agent_response():
    resp = AgentResponse(
        raw_output="Your balance is $500.",
        extracted_entities=[{"account": "123"}],
        latency_ms=142.5,
        status_code=200,
    )
    assert resp.latency_ms == 142.5
    assert resp.status_code == 200
    assert resp.error_message is None


def test_global_metric_summary():
    summary = GlobalMetricSummary(
        total_cases=100,
        passed_cases=97,
        failed_cases=3,
        f1_score=0.94,
        precision=0.95,
        recall=0.93,
        exact_match=0.91,
        faithfulness_avg=4.82,
        relevance_avg=4.75,
        constraint_adherence_avg=4.95,
        adversarial_refusal_rate=1.0,
        latency_p95=1250.0,
    )
    assert summary.total_cases == 100
    assert summary.f1_score == 0.94
    assert summary.adversarial_refusal_rate == 1.0
