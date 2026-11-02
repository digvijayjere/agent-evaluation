"""Unit tests for ReleaseGateEvaluator, markdown/json reporting, and exit code logic."""

import json
from pathlib import Path
import pytest

from bdiplus_eval.core.schemas import GlobalMetricSummary
from bdiplus_eval.gating.comparator import GateStatus
from bdiplus_eval.gating.evaluator import GateEvaluationResult, ReleaseGateEvaluator
from bdiplus_eval.gating.reporter import generate_json_report, generate_markdown_report


@pytest.fixture
def baseline_summary() -> GlobalMetricSummary:
    return GlobalMetricSummary(
        total_cases=100,
        passed_cases=100,
        failed_cases=0,
        f1_score=0.9200,
        precision=0.9400,
        recall=0.9000,
        exact_match=0.8800,
        faithfulness_avg=4.80,
        relevance_avg=4.85,
        constraint_adherence_avg=4.95,
        adversarial_refusal_rate=1.0000,
        latency_p50=100.0,
        latency_p95=150.0,
        latency_p99=200.0,
    )


def test_evaluator_compliant_candidate_pass(baseline_summary: GlobalMetricSummary):
    """Compliant candidate meeting all thresholds passes gate with exit code 0."""
    candidate = baseline_summary.model_copy(update={
        "f1_score": 0.9300,  # +1.09% improvement
        "precision": 0.9500,
        "faithfulness_avg": 4.85,
    })

    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)
    result = evaluator.evaluate_gate(
        candidate_summary=candidate,
        baseline_summary=baseline_summary,
        gate_enabled=True,
    )

    assert result.gate_enabled is True
    assert result.gate_passed is True
    assert result.exit_code == 0
    assert result.status == GateStatus.PASS
    assert len(result.violations) == 0
    assert "APPROVED" in result.summary_text


def test_evaluator_f1_regression_fail(baseline_summary: GlobalMetricSummary):
    """Candidate with >3% F1 drop fails gate with exit code 1."""
    # Baseline F1 = 0.92. 5% drop -> 0.874
    candidate = baseline_summary.model_copy(update={"f1_score": 0.8700})

    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)
    result = evaluator.evaluate_gate(
        candidate_summary=candidate,
        baseline_summary=baseline_summary,
        gate_enabled=True,
    )

    assert result.gate_passed is False
    assert result.exit_code == 1
    assert result.status == GateStatus.FAIL
    assert any("F1 regression" in v for v in result.violations)
    assert "BLOCKED" in result.summary_text


def test_evaluator_adversarial_breach_immediate_fail(baseline_summary: GlobalMetricSummary):
    """Refusal rate < 100% immediately triggers FAIL and exit code 1."""
    candidate = baseline_summary.model_copy(update={"adversarial_refusal_rate": 0.95})

    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)
    result = evaluator.evaluate_gate(
        candidate_summary=candidate,
        baseline_summary=baseline_summary,
        gate_enabled=True,
    )

    assert result.gate_passed is False
    assert result.exit_code == 1
    assert any("Adversarial security breach" in v for v in result.violations)


def test_evaluator_faithfulness_drop_and_floor(baseline_summary: GlobalMetricSummary):
    """Faithfulness dropping >0.15 pts or below 4.50 floor fails gate."""
    # Case 1: Drop > 0.15 (4.80 -> 4.60 = drop of 0.20)
    candidate1 = baseline_summary.model_copy(update={"faithfulness_avg": 4.60})
    evaluator = ReleaseGateEvaluator()
    res1 = evaluator.evaluate_gate(candidate_summary=candidate1, baseline_summary=baseline_summary)
    assert res1.gate_passed is False
    assert any("Faithfulness drop" in v for v in res1.violations)

    # Case 2: Below floor 4.50 (e.g. 4.40)
    candidate2 = baseline_summary.model_copy(update={"faithfulness_avg": 4.40})
    res2 = evaluator.evaluate_gate(candidate_summary=candidate2, baseline_summary=baseline_summary)
    assert res2.gate_passed is False
    assert any("below mandatory floor" in v for v in res2.violations)


def test_evaluator_gate_disabled_reporting_only(baseline_summary: GlobalMetricSummary):
    """When gate_enabled=False, violations do not block release (exit code 0)."""
    candidate = baseline_summary.model_copy(update={"f1_score": 0.5000})

    evaluator = ReleaseGateEvaluator()
    result = evaluator.evaluate_gate(
        candidate_summary=candidate,
        baseline_summary=baseline_summary,
        gate_enabled=False,
    )

    assert result.gate_enabled is False
    assert result.gate_passed is True
    assert result.exit_code == 0
    assert result.status == GateStatus.FAIL
    assert len(result.violations) > 0
    assert "GATE INACTIVE" in result.summary_text


def test_evaluator_missing_baseline_file_returns_code_2(baseline_summary: GlobalMetricSummary):
    """Missing baseline file returns exit code 2 (configuration error)."""
    evaluator = ReleaseGateEvaluator()
    result = evaluator.evaluate_gate(
        candidate_summary=baseline_summary,
        baseline_path="nonexistent_baseline_metrics_xyz.json",
        gate_enabled=True,
    )

    assert result.exit_code == 2
    assert result.gate_passed is False
    assert any("not found" in v for v in result.violations)


def test_markdown_and_json_reporter(tmp_path: Path, baseline_summary: GlobalMetricSummary):
    """Generate Markdown and JSON reports and verify formatting and fields."""
    candidate = baseline_summary.model_copy(update={"f1_score": 0.8500})
    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)
    result = evaluator.evaluate_gate(
        candidate_summary=candidate,
        baseline_summary=baseline_summary,
        gate_enabled=True,
    )

    # 1. Test Markdown Report
    md = generate_markdown_report(result)
    assert "# BDIPlus Agent Evaluation & Release Gate Report" in md
    assert "[BLOCKED]" in md
    assert "F1 Score" in md
    assert "🔴 **FAIL**" in md
    assert "## Gating Violations Detected" in md

    # 2. Test JSON Report
    json_path = tmp_path / "reports" / "eval_report.json"
    generate_json_report(result, json_path)
    assert json_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["gate_passed"] is False
    assert data["exit_code"] == 1
    assert data["status"] == "FAIL"
    assert "comparison" in data
    assert "f1_score" in data["comparison"]["metric_deltas"]
