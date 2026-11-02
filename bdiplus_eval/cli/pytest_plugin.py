"""Pytest plugin registering custom CLI flags and fixtures for BDIPlus Agent Evaluation.

Provides:
- Custom CLI options: --agent-endpoint, --suite, --baseline-metrics, --gate,
  --gate-threshold, --langfuse-sync, --report-out
- Reusable fixtures: eval_config, agent_client, eval_judge, eval_dataset, eval_results_collector
- Parametrization: pytest_generate_tests for dynamic 'eval_case' parametrization
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

from bdiplus_eval.core.agent_client import BaseAgentClient, create_agent_client
from bdiplus_eval.core.schemas import EvalTestCase, InputCategory
from bdiplus_eval.datasets.loader import (
    load_dataset_file,
    load_datasets_from_directory,
)
from bdiplus_eval.metrics.judge_client import (
    JudgeClient,
    LiteLLMJudgeProvider,
    MockJudgeProvider,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options for the evaluation suite."""
    group = parser.getgroup("bdiplus-eval", "BDIPlus Agent Evaluation & Release Gating")

    group.addoption(
        "--agent-endpoint",
        action="store",
        default="mock://compliant",
        help="Target agent HTTP endpoint URL or mock string (e.g. mock://compliant, mock://regressed)",
    )
    group.addoption(
        "--suite",
        action="store",
        default="all",
        choices=["all", "expected", "degraded", "segment", "adversarial"],
        help="Filter evaluation suite to run: expected, degraded, segment, adversarial, or all",
    )
    group.addoption(
        "--baseline-metrics",
        action="store",
        default=None,
        help="Path to baseline metrics JSON reference file for regression comparison",
    )
    group.addoption(
        "--gate",
        action="store_true",
        default=False,
        help="Enforce automated release gating; exit with code 1 upon regression threshold violation",
    )
    group.addoption(
        "--gate-threshold",
        action="store",
        type=float,
        default=0.03,
        help="Maximum allowable relative metric degradation threshold (e.g. 0.03 for 3%%)",
    )
    group.addoption(
        "--langfuse-sync",
        action="store_true",
        default=False,
        help="Stream traces, spans, and evaluation scores to Langfuse API",
    )
    group.addoption(
        "--report-out",
        action="store",
        default="reports/eval_report.json",
        help="File path to save the generated JSON evaluation and gating report",
    )


@pytest.fixture(scope="session")
def eval_config(request: pytest.FixtureRequest) -> Dict[str, Any]:
    """Provide dictionary of parsed CLI options for the evaluation run."""
    return {
        "agent_endpoint": request.config.getoption("--agent-endpoint"),
        "suite": request.config.getoption("--suite"),
        "baseline_metrics": request.config.getoption("--baseline-metrics"),
        "gate": request.config.getoption("--gate"),
        "gate_threshold": float(request.config.getoption("--gate-threshold")),
        "langfuse_sync": request.config.getoption("--langfuse-sync"),
        "report_out": request.config.getoption("--report-out"),
    }


@pytest.fixture(scope="session")
def agent_client(eval_config: Dict[str, Any]) -> BaseAgentClient:
    """Instantiate agent client connector based on CLI --agent-endpoint."""
    endpoint = eval_config["agent_endpoint"]
    return create_agent_client(endpoint)


@pytest.fixture(scope="session")
def eval_judge() -> JudgeClient:
    """Instantiate judge client with LiteLLM provider if API keys present, else Mock."""
    if os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"):
        provider = LiteLLMJudgeProvider()
    else:
        provider = MockJudgeProvider()
    return JudgeClient(provider=provider)


@pytest.fixture(scope="session")
def eval_dataset(eval_config: Dict[str, Any]) -> List[EvalTestCase]:
    """Load evaluation test cases according to selected --suite filter."""
    suite = eval_config["suite"]
    data_dir = Path("data/golden")
    manifest = Path("data/checksums.sha256")

    if suite == "all":
        return load_datasets_from_directory(
            data_dir,
            verify_checksums=manifest.exists(),
            manifest_path=manifest if manifest.exists() else None,
        )

    file_mapping = {
        "expected": "expected_cases.json",
        "degraded": "degraded_cases.json",
        "segment": "segment_cases.json",
        "adversarial": "adversarial_cases.json",
    }

    target_file = data_dir / file_mapping[suite]
    return load_dataset_file(
        target_file,
        verify_checksum=manifest.exists(),
        manifest_path=manifest if manifest.exists() else None,
    )


@pytest.fixture(scope="session")
def eval_results_collector(request: pytest.FixtureRequest) -> List[Dict[str, Any]]:
    """Session-level accumulator collecting evaluated test case outcomes."""
    if not hasattr(request.config, "_eval_collector"):
        request.config._eval_collector = []
    return request.config._eval_collector


@pytest.fixture(scope="session")
def eval_tracer(request: pytest.FixtureRequest, eval_config: Dict[str, Any]):
    """Instantiate and manage the session evaluation tracer and telemetry sink."""
    from bdiplus_eval.telemetry.langfuse_sink import get_telemetry_sink
    from bdiplus_eval.telemetry.tracer import EvaluationTracer

    sync_enabled = eval_config.get("langfuse_sync", False)
    sink = get_telemetry_sink(sync_enabled=sync_enabled)
    tracer = EvaluationTracer(
        sink=sink,
        candidate_version=eval_config.get("agent_endpoint", "candidate"),
        agent_endpoint=eval_config.get("agent_endpoint", "mock://compliant"),
    )
    tracer.start_run()
    request.config._eval_tracer = tracer
    yield tracer
    tracer.flush()
    tracer.shutdown()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Session finish hook triggering terminal summary and gate enforcement."""
    from bdiplus_eval.cli.terminal_summary import process_eval_session_finish
    process_eval_session_finish(session)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically parametrize tests requesting 'eval_case'."""
    if "eval_case" in metafunc.fixturenames:
        suite = metafunc.config.getoption("--suite", "all")
        data_dir = Path("data/golden")
        manifest = Path("data/checksums.sha256")

        if suite == "all":
            cases = load_datasets_from_directory(
                data_dir,
                verify_checksums=manifest.exists(),
                manifest_path=manifest if manifest.exists() else None,
            )
        else:
            file_mapping = {
                "expected": "expected_cases.json",
                "degraded": "degraded_cases.json",
                "segment": "segment_cases.json",
                "adversarial": "adversarial_cases.json",
            }
            target_file = data_dir / file_mapping.get(suite, "expected_cases.json")
            cases = load_dataset_file(
                target_file,
                verify_checksum=manifest.exists(),
                manifest_path=manifest if manifest.exists() else None,
            )

        metafunc.parametrize("eval_case", cases, ids=[c.test_case_id for c in cases])
