"""Hierarchical trace and span instrumentation for evaluation test executions.

Structures observability telemetry into:
1. Root Trace: `eval-run-{run_id}` tagged with candidate version, git commit, branch, runner ID.
2. Parent Span: `test-suite-{suite_name}`.
3. Child Span: `test-case-{test_case_id}` recording prompts, context documents, responses, latencies.
"""

from __future__ import annotations

import os
import platform
import socket
import uuid
from typing import Any, Dict, List, Optional

from bdiplus_eval.core.schemas import AgentResponse, EvalTestCase
from bdiplus_eval.telemetry.langfuse_sink import BaseTelemetrySink, MockTelemetrySink


class EvaluationTracer:
    """Manages hierarchical traces and spans across test suites and test cases."""

    def __init__(
        self,
        sink: BaseTelemetrySink,
        run_id: Optional[str] = None,
        candidate_version: str = "cdp-agent-candidate",
        agent_endpoint: str = "mock://compliant",
    ):
        self.sink = sink
        self.run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
        self.candidate_version = candidate_version
        self.agent_endpoint = agent_endpoint
        self.root_trace_id: Optional[str] = None
        self.suite_spans: Dict[str, str] = {}
        self.active_case_spans: Dict[str, str] = {}

    def start_run(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Initialize the root evaluation run trace with environment tags."""
        git_sha = (
            os.getenv("GITHUB_SHA")
            or os.getenv("GIT_COMMIT_SHA")
            or "local-dev"
        )
        git_branch = (
            os.getenv("GITHUB_REF_NAME")
            or os.getenv("GIT_BRANCH")
            or "main"
        )
        runner_id = (
            os.getenv("RUNNER_NAME")
            or socket.gethostname()
            or platform.node()
        )

        run_tags = [
            f"version:{self.candidate_version}",
            f"branch:{git_branch}",
            f"runner:{runner_id}",
        ]
        if tags:
            run_tags.extend(tags)

        trace_meta = {
            "candidate_version": self.candidate_version,
            "agent_endpoint": self.agent_endpoint,
            "git_commit_sha": git_sha,
            "git_branch": git_branch,
            "runner_id": runner_id,
            "python_version": platform.python_version(),
            "os": platform.system(),
        }
        if metadata:
            trace_meta.update(metadata)

        self.root_trace_id = self.sink.start_trace(
            run_id=self.run_id,
            name=f"eval-run-{self.run_id}",
            metadata=trace_meta,
            tags=run_tags,
        )
        return self.root_trace_id

    def start_suite_span(
        self,
        suite_name: str,
        total_cases: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create parent span for a test suite (e.g. test-suite-adversarial)."""
        if not self.root_trace_id:
            self.start_run()

        span_meta = {"suite_name": suite_name, "total_cases": total_cases}
        if metadata:
            span_meta.update(metadata)

        span_id = self.sink.start_span(
            trace_id=self.root_trace_id,  # type: ignore[arg-type]
            name=f"test-suite-{suite_name}",
            parent_id=None,
            input_data={"suite_name": suite_name, "case_count": total_cases},
            metadata=span_meta,
        )
        self.suite_spans[suite_name] = span_id
        return span_id

    def end_suite_span(
        self,
        suite_name: str,
        summary_stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Finalize parent test suite span."""
        span_id = self.suite_spans.pop(suite_name, None)
        if span_id:
            self.sink.end_span(
                span_id=span_id,
                output_data=summary_stats or {"status": "completed"},
                level="DEFAULT",
            )

    def start_case_span(
        self,
        test_case: EvalTestCase,
        suite_name: Optional[str] = None,
    ) -> str:
        """Create child span for a single test case execution."""
        if not self.root_trace_id:
            self.start_run()

        parent_span_id = self.suite_spans.get(suite_name) if suite_name else None

        input_payload = {
            "test_case_id": test_case.test_case_id,
            "input_prompt": test_case.input_prompt,
            "context_documents": test_case.context_documents,
            "domain_segment": test_case.domain_segment.value,
            "input_category": test_case.input_category.value,
            "priority": test_case.priority.value,
        }

        span_id = self.sink.start_span(
            trace_id=self.root_trace_id,  # type: ignore[arg-type]
            name=f"test-case-{test_case.test_case_id}",
            parent_id=parent_span_id,
            input_data=input_payload,
            metadata=test_case.metadata,
        )
        self.active_case_spans[test_case.test_case_id] = span_id
        return span_id

    def end_case_span(
        self,
        test_case_id: str,
        response: AgentResponse,
        passed: bool = True,
        violations: Optional[List[str]] = None,
    ) -> None:
        """Close child test case span with output data and status level."""
        span_id = self.active_case_spans.pop(test_case_id, None)
        if not span_id:
            return

        level = "DEFAULT" if passed else "ERROR"
        status_msg = "Passed" if passed else f"Failed: {violations or []}"

        output_data = {
            "raw_output": response.raw_output,
            "extracted_entities": response.extracted_entities,
            "latency_ms": response.latency_ms,
            "status_code": response.status_code,
            "error_message": response.error_message,
            "violations": violations or [],
        }

        self.sink.end_span(
            span_id=span_id,
            output_data=output_data,
            level=level,
            status_message=status_msg,
        )

    def flush(self) -> None:
        """Flush underlying telemetry sink."""
        self.sink.flush()

    def shutdown(self) -> None:
        """Terminate underlying telemetry sink."""
        self.sink.shutdown()
