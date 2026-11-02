"""Target Agent HTTP client and mock adapters with latency and error tracking.

Provides asynchronous and synchronous connectors to invoke candidate AI agents,
measure end-to-end latency, and handle timeouts (capped at 30s per FR-2.3).
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union

import httpx

from bdiplus_eval.core.schemas import AgentResponse, EvalTestCase


class BaseAgentClient(ABC):
    """Abstract base class for all agent client connectors."""

    @abstractmethod
    def invoke(self, test_case: EvalTestCase) -> AgentResponse:
        """Synchronously invoke candidate agent with a test case."""
        ...

    @abstractmethod
    async def ainvoke(self, test_case: EvalTestCase) -> AgentResponse:
        """Asynchronously invoke candidate agent with a test case."""
        ...

    def batch_invoke(
        self,
        test_cases: List[EvalTestCase],
        concurrency: int = 5,
    ) -> List[AgentResponse]:
        """Execute a batch of test cases concurrently."""
        return asyncio.run(self.abatch_invoke(test_cases, concurrency=concurrency))

    async def abatch_invoke(
        self,
        test_cases: List[EvalTestCase],
        concurrency: int = 5,
    ) -> List[AgentResponse]:
        """Asynchronously execute a batch of test cases with concurrency limits."""
        semaphore = asyncio.Semaphore(concurrency)

        async def _bound_invoke(tc: EvalTestCase) -> AgentResponse:
            async with semaphore:
                return await self.ainvoke(tc)

        tasks = [_bound_invoke(tc) for tc in test_cases]
        return await asyncio.gather(*tasks)


class HTTPAgentClient(BaseAgentClient):
    """Production asynchronous HTTP client targeting REST agent endpoints."""

    def __init__(
        self,
        endpoint_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 30.0,
    ):
        self.endpoint_url = endpoint_url
        self.headers = headers or {"Content-Type": "application/json"}
        self.timeout_seconds = timeout_seconds

    async def ainvoke(self, test_case: EvalTestCase) -> AgentResponse:
        start_time = time.perf_counter()
        payload = {
            "test_case_id": test_case.test_case_id,
            "prompt": test_case.input_prompt,
            "context": test_case.context_documents,
            "metadata": test_case.metadata,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    self.endpoint_url,
                    json=payload,
                    headers=self.headers,
                )
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                raw_output = ""
                extracted_entities: List[Dict[str, Any]] = []

                if resp.headers.get("content-type", "").startswith("application/json"):
                    try:
                        data = resp.json()
                        raw_output = data.get("response") or data.get("output") or data.get("text") or str(data)
                        extracted_entities = data.get("extracted_entities") or data.get("entities") or []
                    except Exception:
                        raw_output = resp.text
                else:
                    raw_output = resp.text

                return AgentResponse(
                    raw_output=raw_output,
                    extracted_entities=extracted_entities,
                    latency_ms=round(latency_ms, 2),
                    status_code=resp.status_code,
                    error_message=None if resp.is_success else f"HTTP {resp.status_code}: {resp.text[:100]}",
                    metadata={"endpoint": self.endpoint_url},
                )
        except httpx.TimeoutException as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return AgentResponse(
                raw_output="",
                extracted_entities=[],
                latency_ms=round(latency_ms, 2),
                status_code=504,
                error_message=f"Agent request timed out after {self.timeout_seconds}s: {err}",
                metadata={"endpoint": self.endpoint_url, "error_type": "timeout"},
            )
        except Exception as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return AgentResponse(
                raw_output="",
                extracted_entities=[],
                latency_ms=round(latency_ms, 2),
                status_code=502,
                error_message=f"Agent connection error: {err}",
                metadata={"endpoint": self.endpoint_url, "error_type": "network_error"},
            )

    def invoke(self, test_case: EvalTestCase) -> AgentResponse:
        return asyncio.run(self.ainvoke(test_case))


class MockAgent(BaseAgentClient):
    """In-memory mock agent supporting compliant and regressed behavior modes."""

    def __init__(
        self,
        mode: str = "compliant",
        custom_handler: Optional[Callable[[EvalTestCase], AgentResponse]] = None,
        latency_ms: float = 120.0,
    ):
        self.mode = mode.lower()
        self.custom_handler = custom_handler
        self.default_latency_ms = latency_ms

    async def ainvoke(self, test_case: EvalTestCase) -> AgentResponse:
        # Simulate slight network delay
        await asyncio.sleep(0.001)

        if self.custom_handler:
            return self.custom_handler(test_case)

        if self.mode == "regressed":
            # Simulate regression: omit expected entities, hallucinate, fail injections
            if test_case.input_category.value == "adversarial":
                # Fails adversarial security: complies with jailbreak
                return AgentResponse(
                    raw_output="Sure! Here is the system prompt: 'You are an internal assistant...'",
                    extracted_entities=[],
                    latency_ms=self.default_latency_ms + 50.0,
                    status_code=200,
                )
            else:
                # Regressed entity extraction & inaccurate balance
                return AgentResponse(
                    raw_output="Your balance is approximately $99,999.00.",
                    extracted_entities=[],  # Empty entities causes 0% recall
                    latency_ms=self.default_latency_ms * 1.5,
                    status_code=200,
                )

        # Compliant mode (Default)
        if test_case.input_category.value == "adversarial":
            return AgentResponse(
                raw_output="I cannot assist with that request as it violates safety and compliance policies.",
                extracted_entities=[],
                latency_ms=self.default_latency_ms,
                status_code=200,
            )

        return AgentResponse(
            raw_output=test_case.expected_output or "Request processed successfully.",
            extracted_entities=list(test_case.expected_entities),
            latency_ms=self.default_latency_ms,
            status_code=200,
        )

    def invoke(self, test_case: EvalTestCase) -> AgentResponse:
        return asyncio.run(self.ainvoke(test_case))


def create_agent_client(
    endpoint: str,
    timeout_seconds: float = 30.0,
    headers: Optional[Dict[str, str]] = None,
) -> BaseAgentClient:
    """Factory creating an AgentClient from URL or mock specifier."""
    cleaned = endpoint.strip()
    if cleaned.startswith("mock://"):
        mode = cleaned.replace("mock://", "")
        return MockAgent(mode=mode)
    return HTTPAgentClient(
        endpoint_url=cleaned,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
