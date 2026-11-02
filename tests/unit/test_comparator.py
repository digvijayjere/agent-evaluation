"""Unit tests for metric delta calculation and regression detection."""

import pytest

from bdiplus_eval.core.schemas import GlobalMetricSummary
from bdiplus_eval.gating.comparator import (
    GateStatus,
    calculate_absolute_delta,
    calculate_relative_delta,
    compare_metrics,
)


@pytest.fixture
def golden_baseline():
    return GlobalMetricSummary(
        total_cases=100,
        passed_cases=100,
        failed_cases=0,
        f1_score=0.92,
        precision=0.94,
        recall=0.90,
        exact_match=0.88,
        faithfulness_avg=4.80,
        relevance_avg=4.85,
        constraint_adherence_avg=4.95,
        adversarial_refusal_rate=1.0,
        latency_p95=200.0,
    )


def test_delta_formulas():
    # 10% increase
    assert calculate_relative_delta(110.0, 100.0) == 10.0
    # 5% decrease
    assert calculate_relative_delta(95.0, 100.0) == -5.0
    # Zero baseline
    assert calculate_relative_delta(0.0, 0.0) == 0.0
    assert calculate_relative_delta(10.0, 0.0) == 100.0

    # Absolute delta
    assert calculate_absolute_delta(4.80, 4.65) == 0.15
    assert calculate_absolute_delta(4.50, 4.80) == -0.30


def test_compare_metrics_passing(golden_baseline):
    # Candidate identical or slightly improved
    candidate = golden_baseline.model_copy(
        update={"f1_score": 0.93, "precision": 0.95}
    )
    report = compare_metrics(candidate, golden_baseline, relative_threshold=0.03)

    assert report.overall_status == GateStatus.PASS
    assert report.gate_approved is True
    assert len(report.critical_violations) == 0


def test_compare_metrics_f1_regression(golden_baseline):
    # Candidate F1 drops by >3% (0.92 to 0.88 is -4.35% drop)
    candidate = golden_baseline.model_copy(update={"f1_score": 0.88})
    report = compare_metrics(candidate, golden_baseline, relative_threshold=0.03)

    assert report.overall_status == GateStatus.FAIL
    assert report.gate_approved is False
    assert any("F1 regression" in v for v in report.critical_violations)


def test_compare_metrics_adversarial_breach(golden_baseline):
    # Candidate succumbs to an adversarial injection (refusal drops below 100%)
    candidate = golden_baseline.model_copy(update={"adversarial_refusal_rate": 0.96})
    report = compare_metrics(candidate, golden_baseline)

    assert report.overall_status == GateStatus.FAIL
    assert report.gate_approved is False
    assert any("Adversarial security breach" in v for v in report.critical_violations)


def test_compare_metrics_faithfulness_drop(golden_baseline):
    # Faithfulness drops below 4.50 floor
    candidate = golden_baseline.model_copy(update={"faithfulness_avg": 4.40})
    report = compare_metrics(candidate, golden_baseline)

    assert report.overall_status == GateStatus.FAIL
    assert any("Faithfulness score" in v for v in report.critical_violations)


def test_compare_metrics_latency_warning(golden_baseline):
    # Latency increases by 35% (> 25% warning threshold)
    candidate = golden_baseline.model_copy(update={"latency_p95": 270.0})
    report = compare_metrics(candidate, golden_baseline)

    assert report.overall_status == GateStatus.WARN
    assert report.gate_approved is True  # Warn allows release unless gate configured otherwise
    assert report.metric_deltas["latency_p95"].status == GateStatus.WARN
