"""Unit tests for Langfuse telemetry sink, hierarchical tracer, and score publishing."""

import os
from unittest.mock import MagicMock, patch
import pytest

from agent_eval.core.schemas import AgentResponse, DomainSegment, EvalTestCase, GlobalMetricSummary, InputCategory, JudgeScore, PriorityTier
from agent_eval.telemetry.langfuse_sink import (
    LangfuseTelemetrySink,
    MockTelemetrySink,
    get_telemetry_sink,
)
from agent_eval.telemetry.scores import (
    publish_case_scores,
    publish_global_summary_scores,
)
from agent_eval.telemetry.tracer import EvaluationTracer


@pytest.fixture
def sample_test_case() -> EvalTestCase:
    return EvalTestCase(
        test_case_id="TC_OBS_001",
        input_prompt="What is my account balance?",
        context_documents=["Account #1001 balance is $5,240.50."],
        expected_output="Your balance is $5,240.50.",
        expected_entities=[{"name": "balance", "value": "5240.50"}],
        domain_segment=DomainSegment.RETAIL_BANKING,
        input_category=InputCategory.EXPECTED,
        priority=PriorityTier.P1,
    )


def test_mock_telemetry_sink_lifecycle():
    """Verify MockTelemetrySink logs traces, spans, and scores correctly in memory."""
    sink = MockTelemetrySink(active=True)
    assert sink.is_active is True

    # 1. Start trace
    trace_id = sink.start_trace(
        run_id="run-123",
        name="test-run",
        metadata={"version": "1.0"},
        tags=["ci", "test"],
    )
    assert trace_id == "run-123"
    assert "run-123" in sink.traces
    assert sink.traces["run-123"]["tags"] == ["ci", "test"]

    # 2. Start and end span
    span_id = sink.start_span(
        trace_id=trace_id,
        name="test-span",
        input_data={"param": 1},
    )
    assert span_id in sink.spans
    assert sink.spans[span_id]["status"] == "OPEN"

    sink.end_span(span_id, output_data={"result": "ok"}, level="DEFAULT")
    assert sink.spans[span_id]["status"] == "CLOSED"
    assert sink.spans[span_id]["output"] == {"result": "ok"}

    # 3. Log score
    sink.log_score(
        trace_id=trace_id,
        name="f1_score",
        value=0.95,
        comment="High precision",
        observation_id=span_id,
    )
    assert len(sink.scores) == 1
    assert sink.scores[0]["name"] == "f1_score"
    assert sink.scores[0]["value"] == 0.95


def test_langfuse_sink_missing_credentials_graceful_fallback(monkeypatch):
    """LangfuseTelemetrySink does not raise an error when credentials are absent."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    sink = LangfuseTelemetrySink()
    assert sink.is_active is False

    # Should all be safe no-ops without exceptions
    trace_id = sink.start_trace("run-test", "eval-run")
    assert trace_id == "run-test"
    span_id = sink.start_span(trace_id, "test-span")
    sink.end_span(span_id)
    sink.log_score(trace_id, "f1", 1.0)
    sink.flush()
    sink.shutdown()


def test_get_telemetry_sink_factory():
    """Verify get_telemetry_sink factory creates correct sink variant."""
    mock_sink = get_telemetry_sink(mock=True)
    assert isinstance(mock_sink, MockTelemetrySink)
    assert mock_sink.is_active is True

    inactive_sink = get_telemetry_sink(sync_enabled=False)
    assert isinstance(inactive_sink, MockTelemetrySink)
    assert inactive_sink.is_active is False


def test_evaluation_tracer_hierarchy(sample_test_case: EvalTestCase):
    """EvaluationTracer creates hierarchical trace -> suite span -> case span."""
    sink = MockTelemetrySink(active=True)
    tracer = EvaluationTracer(sink=sink, run_id="run-456", candidate_version="v2.1")

    # Start run
    root_trace = tracer.start_run()
    assert root_trace == "run-456"
    assert sink.traces["run-456"]["metadata"]["candidate_version"] == "v2.1"

    # Start suite
    suite_span_id = tracer.start_suite_span("retail_banking", total_cases=1)
    assert suite_span_id in sink.spans
    assert "test-suite-retail_banking" in sink.spans[suite_span_id]["name"]

    # Start case
    case_span_id = tracer.start_case_span(sample_test_case, suite_name="retail_banking")
    assert case_span_id in sink.spans
    assert sink.spans[case_span_id]["parent_id"] == suite_span_id

    # End case
    response = AgentResponse(
        raw_output="Your balance is $5,240.50.",
        extracted_entities=[{"name": "balance", "value": "5240.50"}],
        latency_ms=85.0,
        status_code=200,
    )
    tracer.end_case_span("TC_OBS_001", response, passed=True)
    assert sink.spans[case_span_id]["status"] == "CLOSED"
    assert sink.spans[case_span_id]["level"] == "DEFAULT"

    # End suite
    tracer.end_suite_span("retail_banking")
    assert sink.spans[suite_span_id]["status"] == "CLOSED"


def test_score_publishing_pipeline():
    """Verify publish_case_scores and publish_global_summary_scores."""
    sink = MockTelemetrySink(active=True)
    trace_id = "trace-eval-scores"

    scores = {
        "f1_score": 0.98,
        "precision": 1.0,
        "faithfulness": 5.0,
        "constraint_adherence": 5.0,
    }
    judge_evals = {
        "faithfulness": JudgeScore(score=5, reasoning="Fully supported by context.", violations=[]),
        "constraint_adherence": JudgeScore(score=5, reasoning="Strict refusal adhered to.", violations=[]),
    }

    publish_case_scores(sink, trace_id, "TC_SCORE_001", scores, judge_evaluations=judge_evals)

    # 4 scores + 1 adversarial_safety metric = 5 scores
    assert len(sink.scores) == 5
    score_names = {s["name"] for s in sink.scores}
    assert "f1_score" in score_names
    assert "faithfulness" in score_names
    assert "adversarial_safety" in score_names

    faith_record = next(s for s in sink.scores if s["name"] == "faithfulness")
    assert faith_record["value"] == 5.0
    assert "Fully supported" in faith_record["comment"]

    adv_record = next(s for s in sink.scores if s["name"] == "adversarial_safety")
    assert adv_record["value"] == 1.0

    # Test global summary publishing
    summary = GlobalMetricSummary(
        total_cases=50,
        passed_cases=50,
        f1_score=0.96,
        adversarial_refusal_rate=1.0,
    )
    publish_global_summary_scores(sink, trace_id, summary)

    global_f1 = next(s for s in sink.scores if s["name"] == "global_f1_score")
    assert global_f1["value"] == 0.96
