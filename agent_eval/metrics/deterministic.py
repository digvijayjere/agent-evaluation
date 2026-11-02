"""Deterministic evaluation metrics for AI agent outputs.

Implements mathematically rigorous, deterministic calculations for:
- Exact Match (EM)
- Entity Extraction Precision, Recall, and F1 Score
- Pydantic JSON Schema Validation
- Latency percentiles (p50, p90, p95, p99) and summary statistics
"""

from __future__ import annotations

import json
import re
import string
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import numpy as np
from pydantic import BaseModel, ValidationError


def normalize_text(text: Optional[str]) -> str:
    """Normalize text by lowercasing, trimming, and collapsing whitespace."""
    if not text:
        return ""
    # Lowercase and strip whitespace
    cleaned = text.lower().strip()
    # Normalize multiple whitespace characters
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Remove terminal punctuation for comparison
    cleaned = cleaned.rstrip(string.punctuation)
    return cleaned


def calculate_exact_match(
    actual: Optional[str],
    expected: Optional[str],
    normalize: bool = True,
) -> float:
    """Compute binary Exact Match (EM) score (1.0 or 0.0)."""
    if actual is None and expected is None:
        return 1.0
    if actual is None or expected is None:
        return 0.0

    if normalize:
        return 1.0 if normalize_text(actual) == normalize_text(expected) else 0.0
    return 1.0 if actual.strip() == expected.strip() else 0.0


def _entity_key(entity: Dict[str, Any]) -> Tuple[str, str]:
    """Extract normalized (type, value) tuple for entity matching."""
    ent_type = str(entity.get("type", "")).lower().strip()
    ent_val = normalize_text(str(entity.get("value", "")))
    return (ent_type, ent_val)


def calculate_entity_metrics(
    actual_entities: List[Dict[str, Any]],
    expected_entities: List[Dict[str, Any]],
) -> Tuple[float, float, float]:
    """Calculate Precision, Recall, and F1 score for extracted entities.

    Returns:
        (precision, recall, f1) as float values bounded in [0.0, 1.0].
    """
    if not expected_entities and not actual_entities:
        return 1.0, 1.0, 1.0

    if not expected_entities and actual_entities:
        # False positives only
        return 0.0, 1.0, 0.0

    if expected_entities and not actual_entities:
        # False negatives only
        return 1.0, 0.0, 0.0

    expected_keys = [_entity_key(e) for e in expected_entities]
    actual_keys = [_entity_key(e) for e in actual_entities]

    # Count true positives using multiset matching to handle duplicate entity types
    matched_expected = list(expected_keys)
    true_positives = 0

    for act in actual_keys:
        if act in matched_expected:
            true_positives += 1
            matched_expected.remove(act)

    precision = true_positives / len(actual_keys) if actual_keys else 0.0
    recall = true_positives / len(expected_keys) if expected_keys else 0.0

    if precision + recall == 0.0:
        f1 = 0.0
    else:
        f1 = (2.0 * precision * recall) / (precision + recall)

    return round(precision, 4), round(recall, 4), round(f1, 4)


def validate_json_schema(
    payload: Union[str, Dict[str, Any]],
    schema: Type[BaseModel],
) -> bool:
    """Validate whether a JSON string or dict satisfies a Pydantic schema."""
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return False
    elif isinstance(payload, dict):
        parsed = payload
    else:
        return False

    try:
        schema.model_validate(parsed)
        return True
    except (ValidationError, TypeError):
        return False


def calculate_latency_stats(latencies_ms: List[float]) -> Dict[str, float]:
    """Compute comprehensive latency statistics from a list of durations in ms."""
    if not latencies_ms:
        return {
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "mean": 0.0,
            "min": 0.0,
            "max": 0.0,
        }

    arr = np.array(latencies_ms, dtype=np.float64)
    return {
        "p50": round(float(np.percentile(arr, 50)), 2),
        "p90": round(float(np.percentile(arr, 90)), 2),
        "p95": round(float(np.percentile(arr, 95)), 2),
        "p99": round(float(np.percentile(arr, 99)), 2),
        "mean": round(float(np.mean(arr)), 2),
        "min": round(float(np.min(arr)), 2),
        "max": round(float(np.max(arr)), 2),
    }
