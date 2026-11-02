"""Regression detection and release gating engine."""

from bdiplus_eval.gating.baseline import (
    BaselineError,
    aggregate_candidate_results,
    load_baseline_metrics,
    save_baseline_metrics,
)
from bdiplus_eval.gating.comparator import (
    ComparisonReport,
    GateStatus,
    MetricDelta,
    calculate_absolute_delta,
    calculate_relative_delta,
    compare_metrics,
)
from bdiplus_eval.gating.evaluator import (
    GateEvaluationResult,
    ReleaseGateEvaluator,
)
from bdiplus_eval.gating.reporter import (
    generate_json_report,
    generate_markdown_report,
)

__all__ = [
    "BaselineError",
    "load_baseline_metrics",
    "save_baseline_metrics",
    "aggregate_candidate_results",
    "GateStatus",
    "MetricDelta",
    "ComparisonReport",
    "calculate_relative_delta",
    "calculate_absolute_delta",
    "compare_metrics",
    "GateEvaluationResult",
    "ReleaseGateEvaluator",
    "generate_markdown_report",
    "generate_json_report",
]
