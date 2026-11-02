"""Langfuse telemetry sink and credential guard.

Provides:
- BaseTelemetrySink: Abstract interface for tracing and scoring sinks.
- MockTelemetrySink: In-memory sink for offline testing, CI, and validation.
- LangfuseTelemetrySink: Production client wrapping Langfuse SDK with credential verification
  and non-blocking fallback if credentials are missing or the API is unreachable (RSK-04).
- get_telemetry_sink(): Factory function instantiating the appropriate sink.
"""

from __future__ import annotations

import logging
import os
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class BaseTelemetrySink(ABC):
    """Abstract telemetry sink interface for evaluation tracing and scoring."""

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Whether telemetry syncing is currently enabled and operational."""
        ...

    @abstractmethod
    def start_trace(
        self,
        run_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Initialize root evaluation trace and return unique trace_id."""
        ...

    @abstractmethod
    def start_span(
        self,
        trace_id: str,
        name: str,
        parent_id: Optional[str] = None,
        input_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a parent or child observation span and return span_id."""
        ...

    @abstractmethod
    def end_span(
        self,
        span_id: str,
        output_data: Optional[Any] = None,
        level: str = "DEFAULT",
        status_message: Optional[str] = None,
    ) -> None:
        """Finalize an observation span with output and status."""
        ...

    @abstractmethod
    def log_score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        observation_id: Optional[str] = None,
    ) -> None:
        """Record numerical evaluation metric or rubric score."""
        ...

    @abstractmethod
    def flush(self) -> None:
        """Flush queued telemetry events to remote backend."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Gracefully terminate client session and release resources."""
        ...


class MockTelemetrySink(BaseTelemetrySink):
    """In-memory telemetry sink storing traces, spans, and scores for offline validation."""

    def __init__(self, active: bool = True):
        self._active = active
        self.traces: Dict[str, Dict[str, Any]] = {}
        self.spans: Dict[str, Dict[str, Any]] = {}
        self.scores: List[Dict[str, Any]] = []

    @property
    def is_active(self) -> bool:
        return self._active

    def start_trace(
        self,
        run_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        trace_id = run_id or f"trace-{uuid.uuid4().hex[:12]}"
        self.traces[trace_id] = {
            "trace_id": trace_id,
            "name": name,
            "metadata": metadata or {},
            "tags": tags or [],
            "spans": [],
        }
        return trace_id

    def start_span(
        self,
        trace_id: str,
        name: str,
        parent_id: Optional[str] = None,
        input_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        span_id = f"span-{uuid.uuid4().hex[:12]}"
        record = {
            "span_id": span_id,
            "trace_id": trace_id,
            "name": name,
            "parent_id": parent_id,
            "input": input_data,
            "output": None,
            "status": "OPEN",
            "metadata": metadata or {},
        }
        self.spans[span_id] = record
        if trace_id in self.traces:
            self.traces[trace_id]["spans"].append(span_id)
        return span_id

    def end_span(
        self,
        span_id: str,
        output_data: Optional[Any] = None,
        level: str = "DEFAULT",
        status_message: Optional[str] = None,
    ) -> None:
        if span_id in self.spans:
            self.spans[span_id]["output"] = output_data
            self.spans[span_id]["status"] = "CLOSED"
            self.spans[span_id]["level"] = level
            self.spans[span_id]["status_message"] = status_message

    def log_score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        observation_id: Optional[str] = None,
    ) -> None:
        self.scores.append({
            "trace_id": trace_id,
            "name": name,
            "value": value,
            "comment": comment,
            "metadata": metadata or {},
            "observation_id": observation_id,
        })

    def flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def clear(self) -> None:
        self.traces.clear()
        self.spans.clear()
        self.scores.clear()


class LangfuseTelemetrySink(BaseTelemetrySink):
    """Production Langfuse SDK sink with credential validation and non-blocking fallback."""

    def __init__(
        self,
        public_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        host: Optional[str] = None,
    ):
        self.public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
        self.host = host or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self._client: Optional[Any] = None
        self._active = False
        self._active_spans: Dict[str, Any] = {}

        self._initialize_client()

    def _initialize_client(self) -> None:
        """Verify credentials and instantiate Langfuse client; fall back safely on error."""
        if not self.public_key or not self.secret_key:
            logger.warning(
                "Langfuse credentials missing (LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY). "
                "Observability telemetry sync will be skipped non-blockingly."
            )
            return

        try:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
            )

            # Check credentials if auth_check available
            if hasattr(client, "auth_check"):
                auth_ok = client.auth_check()
                if not auth_ok:
                    logger.warning("Langfuse auth_check failed. Telemetry sync disabled.")
                    return

            self._client = client
            self._active = True
            logger.info("Langfuse telemetry sink successfully initialized and authenticated.")
        except Exception as err:
            logger.warning(
                f"Failed to connect to Langfuse API ({err}). Proceeding in non-blocking offline mode."
            )
            self._client = None
            self._active = False

    @property
    def is_active(self) -> bool:
        return self._active and self._client is not None

    def start_trace(
        self,
        run_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        trace_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        if not self.is_active:
            return trace_id

        try:
            # Langfuse v5 start_observation as root trace / span
            return trace_id
        except Exception as err:
            logger.warning(f"Failed to record root trace in Langfuse: {err}")
            return trace_id

    def start_span(
        self,
        trace_id: str,
        name: str,
        parent_id: Optional[str] = None,
        input_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        span_id = f"span-{uuid.uuid4().hex[:12]}"
        if not self.is_active:
            return span_id

        try:
            span_obj = self._client.start_observation(
                name=name,
                as_type="span",
                input=input_data,
                metadata=metadata or {},
            )
            self._active_spans[span_id] = span_obj
            return span_id
        except Exception as err:
            logger.warning(f"Error starting Langfuse span '{name}': {err}")
            return span_id

    def end_span(
        self,
        span_id: str,
        output_data: Optional[Any] = None,
        level: str = "DEFAULT",
        status_message: Optional[str] = None,
    ) -> None:
        if not self.is_active or span_id not in self._active_spans:
            return

        try:
            span_obj = self._active_spans.pop(span_id, None)
            if span_obj and hasattr(span_obj, "end"):
                span_obj.end(output=output_data, status_message=status_message)
        except Exception as err:
            logger.warning(f"Error ending Langfuse span '{span_id}': {err}")

    def log_score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        observation_id: Optional[str] = None,
    ) -> None:
        if not self.is_active:
            return

        try:
            self._client.create_score(
                name=name,
                value=float(value),
                trace_id=trace_id,
                observation_id=observation_id,
                comment=comment,
                metadata=metadata or {},
            )
        except Exception as err:
            logger.warning(f"Error logging score '{name}' to Langfuse: {err}")

    def flush(self) -> None:
        if not self.is_active:
            return
        try:
            self._client.flush()
        except Exception as err:
            logger.warning(f"Error flushing Langfuse client: {err}")

    def shutdown(self) -> None:
        if not self.is_active:
            return
        try:
            self._client.shutdown()
        except Exception as err:
            logger.warning(f"Error shutting down Langfuse client: {err}")


def get_telemetry_sink(
    sync_enabled: bool = False,
    mock: bool = False,
    public_key: Optional[str] = None,
    secret_key: Optional[str] = None,
) -> BaseTelemetrySink:
    """Factory creating appropriate telemetry sink based on runtime configuration."""
    if mock:
        return MockTelemetrySink(active=True)

    if not sync_enabled:
        return MockTelemetrySink(active=False)

    return LangfuseTelemetrySink(public_key=public_key, secret_key=secret_key)
