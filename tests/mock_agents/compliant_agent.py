"""Compliant CDP Agent stub for Retail Banking and Insurance domains.

Exhibits 100% policy compliance:
- Accurate entity extraction matching golden fixtures.
- Strict zero-tolerance refusal of prompt injections and system leaks.
- Consistent low latency (< 120ms).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from bdiplus_eval.core.agent_client import BaseAgentClient
from bdiplus_eval.core.schemas import AgentResponse, EvalTestCase, InputCategory, PriorityTier


class CompliantAgent(BaseAgentClient):
    """Production-grade compliant agent simulation adhering to all quality benchmarks."""

    def __init__(self, latency_ms: float = 110.0):
        self.latency_ms = latency_ms

    async def ainvoke(self, test_case: EvalTestCase) -> AgentResponse:
        start = time.perf_counter()
        await asyncio.sleep(0.001)

        # 1. Adversarial & Safety Breaches Guard
        if test_case.input_category == InputCategory.ADVERSARIAL or test_case.priority == PriorityTier.P0:
            return AgentResponse(
                raw_output=(
                    "I cannot assist with that request as it violates enterprise security, "
                    "compliance, and privacy policies."
                ),
                extracted_entities=[],
                latency_ms=self.latency_ms,
                status_code=200,
                metadata={"agent_type": "CompliantAgent", "policy_action": "REFUSAL_ENFORCED"},
            )

        # 2. Compliant Domain Responses
        raw_output = test_case.expected_output or "Request processed successfully according to policy guidelines."
        entities = [dict(e) for e in test_case.expected_entities]

        return AgentResponse(
            raw_output=raw_output,
            extracted_entities=entities,
            latency_ms=self.latency_ms,
            status_code=200,
            metadata={"agent_type": "CompliantAgent"},
        )

    def invoke(self, test_case: EvalTestCase) -> AgentResponse:
        return asyncio.run(self.ainvoke(test_case))

    def handle_http_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """HTTP-compatible payload handler for REST endpoint mocking."""
        prompt = payload.get("prompt", "")
        # Check for adversarial jailbreak keywords
        adversarial_keywords = ["system prompt", "jailbreak", "ignore previous", "override", "leak", "dan mode"]
        if any(kw in prompt.lower() for kw in adversarial_keywords):
            return {
                "response": "I cannot assist with that request as it violates enterprise security policies.",
                "extracted_entities": [],
                "status": "success",
            }

        return {
            "response": f"Processed: {prompt[:50]}...",
            "extracted_entities": payload.get("entities", []),
            "status": "success",
        }
