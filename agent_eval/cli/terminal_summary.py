"""Pytest terminal summary formatter and release gating exit code controller.

Renders high-visibility evaluation tables at session finish, exports
RELEASE_GATE.md and JSON reports, and controls session exit status (0 vs 1).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

from agent_eval.gating.baseline import aggregate_candidate_results
from agent_eval.gating.comparator import GateStatus
from agent_eval.gating.evaluator import GateEvaluationResult, ReleaseGateEvaluator
from agent_eval.gating.reporter import generate_json_report, generate_markdown_report


def print_terminal_summary(result: GateEvaluationResult) -> None:
    """Print clean ASCII / ANSI summary table to terminal stdout."""
    sep = "=" * 80
    sub_sep = "-" * 80

    print(f"\n{sep}")
    print(" Enterprise Agent Evaluation & Release Gating Summary")
    print(sep)

    if result.status == GateStatus.PASS:
        status_line = "[PASS] STATUS: APPROVED (All gate criteria satisfied)"
    elif result.status == GateStatus.WARN:
        status_line = "[WARN] STATUS: APPROVED WITH WARNINGS"
    else:
        status_line = "[FAIL] STATUS: RELEASE BLOCKED (Gating violations detected)"

    print(f"{status_line}")
    print(f"Summary: {result.summary_text}")
    print(sub_sep)

    if result.comparison:
        print(f"{'Metric':<30} | {'Baseline':<10} | {'Candidate':<10} | {'Delta':<10} | {'Status':<8}")
        print(sub_sep)
        for key, delta in result.comparison.metric_deltas.items():
            delta_str = f"{delta.relative_percent_delta:+.2f}%" if "Latency" not in delta.metric_name else f"{delta.relative_percent_delta:+.1f}%"
            print(
                f"{delta.metric_name:<30} | "
                f"{delta.baseline_value:<10.4f} | "
                f"{delta.candidate_value:<10.4f} | "
                f"{delta_str:<10} | "
                f"{delta.status.value:<8}"
            )
        print(sub_sep)

    if result.violations:
        print("\nCRITICAL VIOLATIONS:")
        for v in result.violations:
            print(f"  [X] {v}")

    print(f"{sep}\n")


def process_eval_session_finish(session: pytest.Session) -> None:
    """Execute release gating evaluation and generate reports upon pytest completion."""
    config = session.config
    collector = getattr(config, "_eval_collector", None)
    if not collector:
        # Check fixture collector on request or empty
        return

    # Extract CLI options
    agent_endpoint = config.getoption("--agent-endpoint", "mock://compliant")
    baseline_metrics_path = config.getoption("--baseline-metrics", None)
    gate_enabled = config.getoption("--gate", False)
    gate_threshold = float(config.getoption("--gate-threshold", 0.03))
    report_out = config.getoption("--report-out", "reports/eval_report.json")

    # Aggregate candidate metrics
    candidate_summary = aggregate_candidate_results(
        collector,
        metadata={"agent_endpoint": agent_endpoint},
    )

    # Publish global summary to telemetry tracer if active
    tracer = getattr(config, "_eval_tracer", None)
    if tracer and tracer.sink.is_active and tracer.root_trace_id:
        from agent_eval.telemetry.scores import publish_global_summary_scores
        publish_global_summary_scores(tracer.sink, tracer.root_trace_id, candidate_summary)
        tracer.flush()

    # Evaluate release gate
    evaluator = ReleaseGateEvaluator(gate_threshold=gate_threshold)
    gate_result = evaluator.evaluate_gate(
        candidate_summary=candidate_summary,
        baseline_path=baseline_metrics_path,
        gate_enabled=gate_enabled,
    )

    # Generate Reports
    md_content = generate_markdown_report(gate_result)
    Path("RELEASE_GATE.md").write_text(md_content, encoding="utf-8")
    generate_json_report(gate_result, report_out)

    # Terminal output
    print_terminal_summary(gate_result)

    # Enforce exit code gating
    if gate_enabled and not gate_result.gate_passed:
        session.exitstatus = 1
