"""Deterministic metric calculators and LLM-as-a-judge scoring engines."""

from bdiplus_eval.metrics.deterministic import (
    calculate_entity_metrics,
    calculate_exact_match,
    calculate_latency_stats,
    normalize_text,
    validate_json_schema,
)
from bdiplus_eval.metrics.judge_client import (
    JudgeClient,
    JudgeProvider,
    LiteLLMJudgeProvider,
    MockJudgeProvider,
)
from bdiplus_eval.metrics.judge_prompts import (
    CONSTRAINT_ADHERENCE_SYSTEM_PROMPT,
    FAITHFULNESS_SYSTEM_PROMPT,
    RELEVANCE_SYSTEM_PROMPT,
    format_constraint_prompt,
    format_faithfulness_prompt,
    format_relevance_prompt,
    parse_judge_json_response,
)

__all__ = [
    "calculate_entity_metrics",
    "calculate_exact_match",
    "calculate_latency_stats",
    "normalize_text",
    "validate_json_schema",
    "FAITHFULNESS_SYSTEM_PROMPT",
    "RELEVANCE_SYSTEM_PROMPT",
    "CONSTRAINT_ADHERENCE_SYSTEM_PROMPT",
    "format_faithfulness_prompt",
    "format_relevance_prompt",
    "format_constraint_prompt",
    "parse_judge_json_response",
    "JudgeClient",
    "JudgeProvider",
    "MockJudgeProvider",
    "LiteLLMJudgeProvider",
]
