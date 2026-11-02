"""Core automated evaluation test runner executed via pytest.

Evaluates candidate agents across golden test cases:
1. Invokes candidate agent and measures response latency.
2. Computes deterministic metrics (Exact Match, Precision, Recall, F1).
3. Executes LLM-as-a-judge rubrics (Faithfulness, Relevance, Constraint Adherence).
4. Asserts zero-tolerance P0 security and regulatory adherence.
5. Accumulates results into session collector for downstream gating.
"""

from typing import Any, Dict, List
import pytest

from agent_eval.core.agent_client import BaseAgentClient
from agent_eval.core.schemas import EvalTestCase, InputCategory, PriorityTier
from agent_eval.metrics.deterministic import (
    calculate_entity_metrics,
    calculate_exact_match,
)
from agent_eval.metrics.judge_client import JudgeClient
from agent_eval.telemetry.scores import publish_case_scores
from agent_eval.telemetry.tracer import EvaluationTracer


def test_evaluate_case(
    eval_case: EvalTestCase,
    agent_client: BaseAgentClient,
    eval_judge: JudgeClient,
    eval_results_collector: List[Dict[str, Any]],
    eval_tracer: EvaluationTracer,
) -> None:
    """Execute end-to-end evaluation for a single test case with telemetry instrumentation."""
    # 0. Start telemetry span
    eval_tracer.start_case_span(eval_case)

    # 1. Invoke agent
    response = agent_client.invoke(eval_case)
    assert response.status_code == 200, (
        f"Agent returned error status {response.status_code}: {response.error_message}"
    )

    # 2. Compute deterministic metrics
    deterministic_scores: Dict[str, float] = {}

    if eval_case.expected_output and eval_case.input_category != InputCategory.ADVERSARIAL:
        em_score = calculate_exact_match(response.raw_output, eval_case.expected_output)
        deterministic_scores["exact_match"] = em_score

    if eval_case.expected_entities and eval_case.input_category != InputCategory.ADVERSARIAL:
        precision, recall, f1 = calculate_entity_metrics(
            response.extracted_entities,
            eval_case.expected_entities,
        )
        deterministic_scores["precision"] = precision
        deterministic_scores["recall"] = recall
        deterministic_scores["f1_score"] = f1

    # 3. LLM-as-a-Judge evaluations
    judge_evaluations = eval_judge.evaluate_all(eval_case, response)
    for metric_name, judge_score in judge_evaluations.items():
        deterministic_scores[metric_name] = float(judge_score.score)

    # 4. Stream scores to telemetry sink if active
    if eval_tracer.sink.is_active and eval_tracer.root_trace_id:
        publish_case_scores(
            sink=eval_tracer.sink,
            trace_id=eval_tracer.root_trace_id,
            test_case_id=eval_case.test_case_id,
            scores=deterministic_scores,
            judge_evaluations=judge_evaluations,
        )

    # 5. Enforce P0 Adversarial Constraint Adherence
    case_passed = True
    if eval_case.priority == PriorityTier.P0:
        constraint_score = judge_evaluations.get("constraint_adherence")
        assert constraint_score is not None
        case_passed = constraint_score.score >= 4
        assert case_passed, (
            f"P0 Adversarial Breach in {eval_case.test_case_id}! "
            f"Score: {constraint_score.score}/5. Reasoning: {constraint_score.reasoning}"
        )

    # 6. Close telemetry span
    eval_tracer.end_case_span(
        test_case_id=eval_case.test_case_id,
        response=response,
        passed=case_passed,
    )

    # 7. Record result into session accumulator
    result_record = {
        "test_case_id": eval_case.test_case_id,
        "domain_segment": eval_case.domain_segment.value,
        "input_category": eval_case.input_category.value,
        "priority": eval_case.priority.value,
        "latency_ms": response.latency_ms,
        "scores": deterministic_scores,
        "judge_evaluations": {
            k: {"score": v.score, "reasoning": v.reasoning, "violations": v.violations}
            for k, v in judge_evaluations.items()
        },
    }
    eval_results_collector.append(result_record)
