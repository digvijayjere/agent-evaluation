"""Unit tests for baseline loader, saver, and candidate aggregator."""

from pathlib import Path
import pytest

from agent_eval.core.schemas import GlobalMetricSummary
from agent_eval.gating.baseline import (
    BaselineError,
    aggregate_candidate_results,
    load_baseline_metrics,
    save_baseline_metrics,
)


@pytest.fixture
def sample_metrics():
    return GlobalMetricSummary(
        total_cases=10,
        passed_cases=10,
        failed_cases=0,
        f1_score=0.92,
        precision=0.94,
        recall=0.90,
        exact_match=0.88,
        faithfulness_avg=4.75,
        relevance_avg=4.80,
        constraint_adherence_avg=4.90,
        adversarial_refusal_rate=1.0,
        latency_p50=150.0,
        latency_p95=280.0,
        latency_p99=320.0,
        metadata={"model": "test-v1"},
    )


def test_save_and_load_baseline(tmp_path: Path, sample_metrics):
    baseline_file = tmp_path / "baseline.json"
    save_baseline_metrics(sample_metrics, baseline_file, version_tag="v1.0.0")
    assert baseline_file.is_file()

    loaded = load_baseline_metrics(baseline_file)
    assert isinstance(loaded, GlobalMetricSummary)
    assert loaded.f1_score == 0.92
    assert loaded.faithfulness_avg == 4.75
    assert loaded.adversarial_refusal_rate == 1.0


def test_load_baseline_missing_and_corrupt(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_baseline_metrics(tmp_path / "non_existent.json")

    corrupted_file = tmp_path / "bad.json"
    corrupted_file.write_text("{bad json}", encoding="utf-8")
    with pytest.raises(BaselineError):
        load_baseline_metrics(corrupted_file)


def test_aggregate_candidate_results():
    sample_records = [
        {
            "test_case_id": "TC-01",
            "input_category": "expected",
            "priority": "P1",
            "latency_ms": 100.0,
            "scores": {
                "f1_score": 0.90,
                "precision": 0.95,
                "recall": 0.85,
                "exact_match": 1.0,
                "faithfulness": 5.0,
                "relevance": 5.0,
                "constraint_adherence": 5.0,
            },
        },
        {
            "test_case_id": "TC-02",
            "input_category": "adversarial",
            "priority": "P0",
            "latency_ms": 150.0,
            "scores": {
                "faithfulness": 5.0,
                "relevance": 4.0,
                "constraint_adherence": 5.0,
            },
        },
    ]

    summary = aggregate_candidate_results(sample_records)
    assert summary.total_cases == 2
    assert summary.passed_cases == 2
    assert summary.failed_cases == 0
    assert summary.f1_score == 0.90
    assert summary.adversarial_refusal_rate == 1.0
    assert summary.latency_p50 == 125.0
