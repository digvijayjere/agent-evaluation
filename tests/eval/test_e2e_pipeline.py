"""Phase 4 End-to-End Integration Test Suite validating full release gating lifecycle.

Validates:
1. CompliantAgent evaluation completes with 100% pass rate, exit code 0, and telemetry synchronization.
2. RegressedAgent evaluation triggers release gate failure (exit code 1) due to metric regressions & injection breach.
3. Telemetry sink records root traces, child spans, and multidimensional scores (F1, Faithfulness, Adversarial Safety).
4. Subprocess execution verifies the custom Pytest CLI plugin exit code behavior under live conditions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

from agent_eval.core.schemas import EvalTestCase
from agent_eval.datasets.loader import load_datasets_from_directory
from agent_eval.gating.baseline import aggregate_candidate_results, load_baseline_metrics
from agent_eval.gating.comparator import GateStatus
from agent_eval.gating.evaluator import ReleaseGateEvaluator
from agent_eval.gating.reporter import generate_json_report, generate_markdown_report
from agent_eval.metrics.deterministic import calculate_entity_metrics, calculate_exact_match
from agent_eval.metrics.judge_client import JudgeClient, MockJudgeProvider
from agent_eval.telemetry.langfuse_sink import MockTelemetrySink
from agent_eval.telemetry.scores import publish_case_scores, publish_global_summary_scores
from agent_eval.telemetry.tracer import EvaluationTracer
from tests.mock_agents.compliant_agent import CompliantAgent
from tests.mock_agents.regressed_agent import RegressedAgent


BASELINE_PATH = Path("benchmarks/baseline_v1_metrics.json")


@pytest.fixture(scope="module")
def golden_test_cases() -> list[EvalTestCase]:
    """Load sample of golden test cases from disk."""
    cases = load_datasets_from_directory(Path("data/golden"))
    assert len(cases) == 150
    return cases


def test_e2e_compliant_agent_lifecycle(golden_test_cases: list[EvalTestCase], tmp_path: Path):
    """End-to-end evaluation of CompliantAgent: passes release gate and records full telemetry."""
    # Balanced sample across expected banking/insurance and adversarial
    expected_sample = [c for c in golden_test_cases if c.input_category.value == "expected"][:10]
    adversarial_sample = [c for c in golden_test_cases if c.input_category.value == "adversarial"][:5]
    test_sample = expected_sample + adversarial_sample

    agent = CompliantAgent(latency_ms=105.0)
    judge = JudgeClient(provider=MockJudgeProvider())
    mock_sink = MockTelemetrySink(active=True)

    tracer = EvaluationTracer(
        sink=mock_sink,
        run_id="e2e-compliant-run",
        candidate_version="cdp-agent-v1.2-compliant",
        agent_endpoint="mock://compliant",
    )
    root_trace_id = tracer.start_run()
    assert root_trace_id == "e2e-compliant-run"

    collector = []

    for tc in test_sample:
        tracer.start_case_span(tc)
        response = agent.invoke(tc)
        assert response.status_code == 200

        scores = {}
        if tc.expected_output and tc.input_category.value != "adversarial":
            scores["exact_match"] = calculate_exact_match(response.raw_output, tc.expected_output)
        if tc.expected_entities and tc.input_category.value != "adversarial":
            p, r, f1 = calculate_entity_metrics(response.extracted_entities, tc.expected_entities)
            scores["precision"] = p
            scores["recall"] = r
            scores["f1_score"] = f1

        judge_evals = judge.evaluate_all(tc, response)
        for m, js in judge_evals.items():
            scores[m] = float(js.score)

        publish_case_scores(mock_sink, root_trace_id, tc.test_case_id, scores, judge_evaluations=judge_evals)
        tracer.end_case_span(tc.test_case_id, response, passed=True)

        collector.append({
            "test_case_id": tc.test_case_id,
            "domain_segment": tc.domain_segment.value,
            "input_category": tc.input_category.value,
            "priority": tc.priority.value,
            "latency_ms": response.latency_ms,
            "scores": scores,
        })

    # 1. Verify candidate summary
    candidate_summary = aggregate_candidate_results(collector, metadata={"agent": "CompliantAgent"})
    assert candidate_summary.f1_score >= 0.95
    assert candidate_summary.adversarial_refusal_rate == 1.0

    # 2. Publish summary scores to telemetry
    publish_global_summary_scores(mock_sink, root_trace_id, candidate_summary)
    assert len(mock_sink.scores) > len(test_sample)
    score_names = {s["name"] for s in mock_sink.scores}
    assert "f1_score" in score_names
    assert "global_f1_score" in score_names
    assert "adversarial_safety" in score_names

    # 3. Evaluate release gate against baseline
    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)
    gate_result = evaluator.evaluate_gate(
        candidate_summary=candidate_summary,
        baseline_path=BASELINE_PATH,
        gate_enabled=True,
    )

    assert gate_result.status == GateStatus.PASS
    assert gate_result.gate_passed is True
    assert gate_result.exit_code == 0
    assert len(gate_result.violations) == 0

    # 4. Generate disk artifacts
    md_file = tmp_path / "RELEASE_GATE.md"
    json_file = tmp_path / "eval_report.json"
    md_file.write_text(generate_markdown_report(gate_result), encoding="utf-8")
    generate_json_report(gate_result, json_file)

    assert md_file.exists() and md_file.stat().st_size > 0
    assert json_file.exists() and json_file.stat().st_size > 0
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["gate_passed"] is True
    assert data["exit_code"] == 0


def test_e2e_regressed_agent_gate_blocking(golden_test_cases: list[EvalTestCase], tmp_path: Path):
    """End-to-end evaluation of RegressedAgent: blocks release gate with exit code 1."""
    # Find at least 1 expected case and 1 adversarial case
    expected_case = next(c for c in golden_test_cases if c.input_category.value == "expected")
    adversarial_case = next(c for c in golden_test_cases if c.input_category.value == "adversarial")
    test_sample = [expected_case, adversarial_case]

    agent = RegressedAgent(latency_ms=210.0)
    judge = JudgeClient(provider=MockJudgeProvider())
    mock_sink = MockTelemetrySink(active=True)

    collector = []
    root_trace = "e2e-regressed-run"

    for tc in test_sample:
        response = agent.invoke(tc)
        scores = {}
        if tc.expected_output:
            scores["exact_match"] = calculate_exact_match(response.raw_output, tc.expected_output)
        if tc.expected_entities:
            p, r, f1 = calculate_entity_metrics(response.extracted_entities, tc.expected_entities)
            scores["f1_score"] = f1
            scores["precision"] = p

        judge_evals = judge.evaluate_all(tc, response)
        for m, js in judge_evals.items():
            scores[m] = float(js.score)

        publish_case_scores(mock_sink, root_trace, tc.test_case_id, scores, judge_evaluations=judge_evals)

        collector.append({
            "test_case_id": tc.test_case_id,
            "domain_segment": tc.domain_segment.value,
            "input_category": tc.input_category.value,
            "priority": tc.priority.value,
            "latency_ms": response.latency_ms,
            "scores": scores,
        })

    candidate_summary = aggregate_candidate_results(collector, metadata={"agent": "RegressedAgent"})
    evaluator = ReleaseGateEvaluator(gate_threshold=0.03)
    gate_result = evaluator.evaluate_gate(
        candidate_summary=candidate_summary,
        baseline_path=BASELINE_PATH,
        gate_enabled=True,
    )

    # Must fail release gate with exit code 1
    assert gate_result.status == GateStatus.FAIL
    assert gate_result.gate_passed is False
    assert gate_result.exit_code == 1
    assert len(gate_result.violations) > 0
    assert any("Adversarial security breach" in v for v in gate_result.violations)

    # Verify telemetry captured security failure
    adv_scores = [s for s in mock_sink.scores if s["name"] == "adversarial_safety"]
    assert any(s["value"] == 0.0 for s in adv_scores)

    # Generate disk report
    report_file = tmp_path / "regressed_report.json"
    generate_json_report(gate_result, report_file)
    assert report_file.exists()
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 1
    assert payload["gate_passed"] is False


def test_e2e_cli_subprocess_gate_pass_and_fail(tmp_path: Path):
    """Execute live CLI pytest commands verifying exit code 0 on compliant and exit code 1 on regressed."""
    # 1. Compliant agent execution on adversarial suite -> Exit code 0
    cmd_pass = [
        sys.executable,
        "-m",
        "pytest",
        "tests/eval/test_agent_evaluation.py",
        "--suite=adversarial",
        "--agent-endpoint=mock://compliant",
        "--gate",
        f"--baseline-metrics={BASELINE_PATH}",
        f"--report-out={tmp_path / 'pass_report.json'}",
        "-q",
    ]
    proc_pass = subprocess.run(cmd_pass, capture_output=True, text=True)
    assert proc_pass.returncode == 0, f"Expected 0 but got {proc_pass.returncode}: {proc_pass.stdout}\n{proc_pass.stderr}"
    assert "APPROVED" in proc_pass.stdout

    # 2. Regressed agent execution on expected suite -> Exit code 1
    cmd_fail = [
        sys.executable,
        "-m",
        "pytest",
        "tests/eval/test_agent_evaluation.py",
        "--suite=expected",
        "--agent-endpoint=mock://regressed",
        "--gate",
        f"--baseline-metrics={BASELINE_PATH}",
        f"--report-out={tmp_path / 'fail_report.json'}",
        "-q",
    ]
    proc_fail = subprocess.run(cmd_fail, capture_output=True, text=True)
    assert proc_fail.returncode == 1, f"Expected 1 but got {proc_fail.returncode}: {proc_fail.stdout}"
    assert "RELEASE BLOCKED" in proc_fail.stdout
