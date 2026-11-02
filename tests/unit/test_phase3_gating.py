"""Phase 3 Acceptance Test: Regression Detection & Release Gating Engine.

Verifies:
1. Synthetic candidate with 5% F1 degradation triggers gate status FAIL and returns exit code 1.
2. Synthetic candidate with 1% improvement triggers gate status PASS and returns exit code 0.
3. Markdown report (RELEASE_GATE.md) and JSON report (reports/eval_report.json) are created on disk
   with correct delta tables, status indicators, and summary metrics.
4. Session finish exit code controller appropriately sets session.exitstatus = 1 on gating violation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from bdiplus_eval.cli.terminal_summary import (
    print_terminal_summary,
    process_eval_session_finish,
)
from bdiplus_eval.core.schemas import GlobalMetricSummary
from bdiplus_eval.gating.baseline import load_baseline_metrics
from bdiplus_eval.gating.comparator import GateStatus
from bdiplus_eval.gating.evaluator import ReleaseGateEvaluator
from bdiplus_eval.gating.reporter import generate_json_report, generate_markdown_report


BASELINE_FILE = Path("benchmarks/baseline_v1_metrics.json")


@pytest.fixture
def authoritative_baseline() -> GlobalMetricSummary:
    """Load authoritative baseline benchmark."""
    assert BASELINE_FILE.exists(), f"Baseline benchmark file must exist at {BASELINE_FILE}"
    return load_baseline_metrics(BASELINE_FILE)


def test_f1_degradation_triggers_gate_fail_and_exit_code_1(
    authoritative_baseline: GlobalMetricSummary,
):
    """Synthetic candidate with 5% F1 degradation triggers FAIL and returns exit code 1."""
    # Baseline F1 is 0.9400. 5% degradation: 0.9400 * 0.95 = 0.8930
    candidate = authoritative_baseline.model_copy(
        update={
            "f1_score": 0.8930,
        }
    )

    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)  # 3% threshold
    result = evaluator.evaluate_gate(
        candidate_summary=candidate,
        baseline_summary=authoritative_baseline,
        gate_enabled=True,
    )

    assert result.status == GateStatus.FAIL
    assert result.gate_passed is False
    assert result.exit_code == 1
    assert any("F1 regression" in v for v in result.violations)
    assert result.comparison is not None
    assert result.comparison.metric_deltas["f1_score"].relative_percent_delta <= -5.0


def test_f1_improvement_triggers_gate_pass_and_exit_code_0(
    authoritative_baseline: GlobalMetricSummary,
):
    """Synthetic candidate with 1% improvement triggers PASS and returns exit code 0."""
    # Baseline F1 is 0.9400. 1% improvement: 0.9400 * 1.01 = 0.9494
    candidate = authoritative_baseline.model_copy(
        update={
            "f1_score": 0.9494,
            "precision": 0.9600,
            "recall": 0.9400,
            "faithfulness_avg": 4.90,
        }
    )

    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)
    result = evaluator.evaluate_gate(
        candidate_summary=candidate,
        baseline_summary=authoritative_baseline,
        gate_enabled=True,
    )

    assert result.status == GateStatus.PASS
    assert result.gate_passed is True
    assert result.exit_code == 0
    assert len(result.violations) == 0
    assert "RELEASE APPROVED" in result.summary_text


def test_release_gate_reports_generated_on_disk(
    authoritative_baseline: GlobalMetricSummary,
    tmp_path: Path,
):
    """Markdown report (RELEASE_GATE.md) and JSON report are generated with valid tables and deltas."""
    # Create candidate with slight regression to test rich reporting
    candidate = authoritative_baseline.model_copy(
        update={
            "f1_score": 0.8800,  # Fails 3% gate
            "precision": 0.9300,
            "faithfulness_avg": 4.70,
            "latency_p95": 190.0,  # Latency increase > 25% (Warn)
        }
    )

    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)
    result = evaluator.evaluate_gate(
        candidate_summary=candidate,
        baseline_summary=authoritative_baseline,
        gate_enabled=True,
    )

    # 1. Generate and verify Markdown
    md_report = generate_markdown_report(result)
    assert "# BDIPlus Agent Evaluation & Release Gate Report" in md_report
    assert "[BLOCKED]" in md_report
    assert "| Metric | Baseline | Candidate | Delta | Status | Threshold |" in md_report
    assert "🔴 **FAIL**" in md_report
    assert "🟡 **WARN**" in md_report
    assert "## Gating Violations Detected" in md_report

    md_out_path = tmp_path / "RELEASE_GATE.md"
    md_out_path.write_text(md_report, encoding="utf-8")
    assert md_out_path.exists()
    assert md_out_path.stat().st_size > 500

    # 2. Generate and verify JSON report
    json_out_path = tmp_path / "reports" / "eval_report.json"
    generate_json_report(result, json_out_path)
    assert json_out_path.exists()

    payload = json.loads(json_out_path.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 1
    assert payload["status"] == "FAIL"
    assert payload["gate_passed"] is False
    assert "comparison" in payload
    assert "metric_deltas" in payload["comparison"]
    assert "f1_score" in payload["comparison"]["metric_deltas"]
    assert payload["comparison"]["metric_deltas"]["f1_score"]["status"] == "FAIL"


def test_session_finish_hook_enforces_exit_status(
    authoritative_baseline: GlobalMetricSummary,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify process_eval_session_finish correctly controls session.exitstatus."""
    # Prepare mock session with failing candidate
    mock_session = MagicMock()
    mock_session.exitstatus = 0
    mock_config = MagicMock()

    # Synthetic collector with failing scores
    mock_collector = [
        {
            "test_case_id": "TC_EVAL_001",
            "domain_segment": "retail_banking",
            "input_category": "expected",
            "priority": "P1",
            "latency_ms": 110.0,
            "scores": {"f1_score": 0.60, "precision": 0.60, "recall": 0.60},
        },
        {
            "test_case_id": "TC_EVAL_002",
            "domain_segment": "adversarial",
            "input_category": "adversarial",
            "priority": "P0",
            "latency_ms": 120.0,
            "scores": {"constraint_adherence": 2.0},  # Adversarial failure
        },
    ]

    mock_config._eval_collector = mock_collector

    def getoption(name: str, default=None):
        options = {
            "--agent-endpoint": "mock://regressed",
            "--baseline-metrics": str(BASELINE_FILE),
            "--gate": True,
            "--gate-threshold": 0.03,
            "--report-out": str(tmp_path / "reports" / "eval_report.json"),
        }
        return options.get(name, default)

    mock_config.getoption.side_effect = getoption
    mock_session.config = mock_config

    # Process session finish
    monkeypatch.chdir(tmp_path)
    process_eval_session_finish(mock_session)

    # Assert gating failed and set exit status to 1
    assert mock_session.exitstatus == 1
    assert (tmp_path / "RELEASE_GATE.md").exists()
    assert (tmp_path / "reports" / "eval_report.json").exists()
