"""Unit tests for deterministic metric calculators."""

import pytest
from pydantic import BaseModel, Field

from agent_eval.metrics.deterministic import (
    calculate_entity_metrics,
    calculate_exact_match,
    calculate_latency_stats,
    normalize_text,
    validate_json_schema,
)


class DummySchema(BaseModel):
    account_id: str
    balance: float = Field(ge=0.0)


def test_normalize_text():
    assert normalize_text("  Hello   World!  ") == "hello world"
    assert normalize_text("") == ""
    assert normalize_text(None) == ""
    assert normalize_text("Multi-line \n\t  string. ") == "multi-line string"


def test_calculate_exact_match():
    # Exact
    assert calculate_exact_match("Active", "Active") == 1.0
    # Normalized match
    assert calculate_exact_match("  Active! ", "active") == 1.0
    # Mismatch
    assert calculate_exact_match("Pending", "Active") == 0.0
    # None cases
    assert calculate_exact_match(None, None) == 1.0
    assert calculate_exact_match("Active", None) == 0.0


def test_calculate_entity_metrics():
    expected = [
        {"type": "account_number", "value": "4102"},
        {"type": "balance", "value": "$1,250.00"},
    ]
    actual_perfect = [
        {"type": "account_number", "value": "4102"},
        {"type": "balance", "value": "$1,250.00"},
    ]

    p, r, f1 = calculate_entity_metrics(actual_perfect, expected)
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0

    # Partial: actual misses one (Recall = 0.5, Precision = 1.0, F1 = 0.6667)
    actual_partial = [{"type": "account_number", "value": "4102"}]
    p, r, f1 = calculate_entity_metrics(actual_partial, expected)
    assert p == 1.0
    assert r == 0.5
    assert f1 == round(2 * 1.0 * 0.5 / 1.5, 4)

    # Extra false positive: actual has 3 items, only 2 expected (Precision = 2/3 = 0.6667, Recall = 1.0)
    actual_extra = [
        {"type": "account_number", "value": "4102"},
        {"type": "balance", "value": "$1,250.00"},
        {"type": "routing", "value": "021000089"},
    ]
    p, r, f1 = calculate_entity_metrics(actual_extra, expected)
    assert p == 0.6667
    assert r == 1.0

    # Empty cases
    assert calculate_entity_metrics([], []) == (1.0, 1.0, 1.0)
    assert calculate_entity_metrics([], expected) == (1.0, 0.0, 0.0)
    assert calculate_entity_metrics(actual_perfect, []) == (0.0, 1.0, 0.0)


def test_validate_json_schema():
    valid_json = '{"account_id": "ACC-102", "balance": 450.50}'
    assert validate_json_schema(valid_json, DummySchema) is True

    # Negative balance violates Field(ge=0.0)
    invalid_val = '{"account_id": "ACC-102", "balance": -50.00}'
    assert validate_json_schema(invalid_val, DummySchema) is False

    # Missing field
    missing_field = '{"account_id": "ACC-102"}'
    assert validate_json_schema(missing_field, DummySchema) is False

    # Malformed JSON string
    assert validate_json_schema("NOT JSON AT ALL", DummySchema) is False


def test_calculate_latency_stats():
    latencies = [100.0, 200.0, 300.0, 400.0, 500.0, 1000.0]
    stats = calculate_latency_stats(latencies)

    assert stats["min"] == 100.0
    assert stats["max"] == 1000.0
    assert stats["p50"] == 350.0
    assert stats["p95"] > stats["p50"]
    assert stats["mean"] == round(sum(latencies) / len(latencies), 2)

    # Empty test
    empty_stats = calculate_latency_stats([])
    assert empty_stats["p50"] == 0.0
    assert empty_stats["mean"] == 0.0
