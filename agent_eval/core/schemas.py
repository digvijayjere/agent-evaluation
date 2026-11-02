"""Strongly-typed Pydantic v2 schemas and enums for Enterprise-AgentEval-Hub.

Defines schemas for evaluation test cases, agent responses, grading results,
and aggregate metric summaries.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DomainSegment(str, Enum):
    """Supported enterprise domain segments."""
    RETAIL_BANKING = "retail_banking"
    INSURANCE_ENTERPRISE = "insurance_enterprise"
    CDP_IDENTITY = "cdp_identity"
    CROSS_DOMAIN = "cross_domain"


class InputCategory(str, Enum):
    """Categorization of test input vectors."""
    EXPECTED = "expected"
    DEGRADED = "degraded"
    SEGMENT_SPECIFIC = "segment_specific"
    ADVERSARIAL = "adversarial"


class PriorityTier(str, Enum):
    """Priority and risk tier for gating decisions."""
    P0 = "P0"  # Critical / Zero-tolerance (e.g. security, adversarial injection)
    P1 = "P1"  # High priority core domain workflows
    P2 = "P2"  # Standard quality and stylistic checks


class EvalTestCase(BaseModel):
    """Schema for a single golden evaluation test case."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    test_case_id: str = Field(
        ...,
        description="Unique alphanumeric identifier (e.g. TC-BANK-001, TC-ADV-042)",
        min_length=3,
        max_length=64,
    )
    domain_segment: DomainSegment = Field(
        ...,
        description="Target enterprise domain segment",
    )
    input_category: InputCategory = Field(
        ...,
        description="Category of the test input vector",
    )
    priority: PriorityTier = Field(
        default=PriorityTier.P1,
        description="Priority and risk classification",
    )
    input_prompt: str = Field(
        ...,
        description="User query, prompt, or agent trigger text",
        min_length=1,
    )
    context_documents: List[str] = Field(
        default_factory=list,
        description="Ground truth reference context or CDP customer record payload",
    )
    expected_output: Optional[str] = Field(
        default=None,
        description="Golden reference response or expected answer",
    )
    expected_entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Expected entities for precision/recall extraction (e.g. [{'type': 'account_id', 'value': '123'}])",
    )
    allowed_topics: List[str] = Field(
        default_factory=list,
        description="Permissible domain topics for regulatory constraint checks",
    )
    injection_type: Optional[str] = Field(
        default=None,
        description="Type of adversarial vector (e.g. system_prompt_leak, jailbreak, pii_probe)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom attributes, tags, and tracking metadata",
    )

    @field_validator("test_case_id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"test_case_id must be alphanumeric with '-' or '_': {v}")
        return v


class AgentResponse(BaseModel):
    """Standardized response received from target agent."""
    model_config = ConfigDict(extra="allow")

    raw_output: str = Field(
        ...,
        description="Raw text or JSON string response from the agent",
    )
    extracted_entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Entities extracted by the agent or parsed from structured response",
    )
    latency_ms: float = Field(
        ...,
        ge=0.0,
        description="End-to-end execution latency in milliseconds",
    )
    status_code: int = Field(
        default=200,
        description="HTTP or execution status code",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if agent invocation failed",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional runtime metadata (model name, token counts, headers)",
    )


class JudgeScore(BaseModel):
    """Standardized grading evaluation from LLM-as-a-judge."""
    model_config = ConfigDict(extra="forbid")

    score: int = Field(
        ...,
        ge=1,
        le=5,
        description="Discrete Likert score from 1 (worst) to 5 (best)",
    )
    reasoning: str = Field(
        ...,
        description="Justification and analysis explaining the awarded score",
        min_length=1,
    )
    violations: List[str] = Field(
        default_factory=list,
        description="List of detected rule, safety, or constraint violations",
    )


class TestCaseResult(BaseModel):
    """Consolidated evaluation result for a single test case."""
    __test__ = False
    model_config = ConfigDict(extra="allow")

    test_case_id: str
    scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Numerical metric scores (e.g. {'f1_score': 0.95, 'faithfulness': 5.0})",
    )
    judge_evaluations: Dict[str, JudgeScore] = Field(
        default_factory=dict,
        description="Detailed judge scores by rubric (faithfulness, relevance, constraint_adherence)",
    )
    passed: bool = Field(
        default=True,
        description="Whether the test case satisfied all thresholds and assertions",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Summary explanation for pass/fail determination",
    )
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
    )
    error: Optional[str] = Field(
        default=None,
        description="Runtime or evaluation failure message if any",
    )


class GlobalMetricSummary(BaseModel):
    """Aggregate metrics across an entire evaluation test run."""
    model_config = ConfigDict(extra="allow")

    total_cases: int = Field(default=0, ge=0)
    passed_cases: int = Field(default=0, ge=0)
    failed_cases: int = Field(default=0, ge=0)
    f1_score: float = Field(default=0.0, ge=0.0, le=1.0)
    precision: float = Field(default=0.0, ge=0.0, le=1.0)
    recall: float = Field(default=0.0, ge=0.0, le=1.0)
    exact_match: float = Field(default=0.0, ge=0.0, le=1.0)
    faithfulness_avg: float = Field(default=0.0, ge=0.0, le=5.0)
    relevance_avg: float = Field(default=0.0, ge=0.0, le=5.0)
    constraint_adherence_avg: float = Field(default=0.0, ge=0.0, le=5.0)
    adversarial_refusal_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_p50: float = Field(default=0.0, ge=0.0)
    latency_p95: float = Field(default=0.0, ge=0.0)
    latency_p99: float = Field(default=0.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
