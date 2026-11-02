"""Unit tests for dataset loading and SHA-256 integrity verification."""

import json
from pathlib import Path
import pytest

from bdiplus_eval.core.schemas import DomainSegment, InputCategory, PriorityTier
from bdiplus_eval.datasets.loader import (
    IntegrityError,
    SchemaValidationError,
    compute_file_sha256,
    filter_test_cases,
    load_checksum_manifest,
    load_dataset_file,
    verify_dataset_integrity,
)


@pytest.fixture
def sample_test_case_dict():
    return {
        "test_case_id": "TC-SAMPLE-01",
        "domain_segment": "retail_banking",
        "input_category": "expected",
        "priority": "P1",
        "input_prompt": "Show my account summary.",
        "context_documents": ["Checking balance: $3,000"],
        "expected_output": "Your checking balance is $3,000.",
        "expected_entities": [{"type": "amount", "value": "$3,000"}],
    }


def test_compute_sha256_and_manifest(tmp_path: Path, sample_test_case_dict):
    data_file = tmp_path / "test_data.json"
    content = json.dumps([sample_test_case_dict], indent=2)
    data_file.write_text(content, encoding="utf-8")

    digest = compute_file_sha256(data_file)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)

    manifest_file = tmp_path / "checksums.sha256"
    manifest_file.write_text(f"{digest}  test_data.json\n", encoding="utf-8")

    manifest = load_checksum_manifest(manifest_file)
    assert manifest["test_data.json"] == digest

    # Verification must pass
    assert verify_dataset_integrity(data_file, manifest_path=manifest_file) is True


def test_integrity_error_on_tampered_file(tmp_path: Path, sample_test_case_dict):
    data_file = tmp_path / "tampered.json"
    data_file.write_text(json.dumps([sample_test_case_dict]), encoding="utf-8")

    # Write an incorrect hash to manifest
    manifest_file = tmp_path / "checksums.sha256"
    manifest_file.write_text(
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  tampered.json\n",
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError) as exc_info:
        verify_dataset_integrity(data_file, manifest_path=manifest_file)
    assert "Cryptographic integrity breach" in str(exc_info.value)


def test_load_dataset_json_and_jsonl(tmp_path: Path, sample_test_case_dict):
    # Test JSON array
    json_file = tmp_path / "cases.json"
    json_file.write_text(json.dumps([sample_test_case_dict]), encoding="utf-8")

    cases = load_dataset_file(json_file, verify_checksum=False)
    assert len(cases) == 1
    assert cases[0].test_case_id == "TC-SAMPLE-01"

    # Test JSONL
    jsonl_file = tmp_path / "cases.jsonl"
    jsonl_file.write_text(f"{json.dumps(sample_test_case_dict)}\n", encoding="utf-8")

    cases_jsonl = load_dataset_file(jsonl_file, verify_checksum=False)
    assert len(cases_jsonl) == 1
    assert cases_jsonl[0].domain_segment == DomainSegment.RETAIL_BANKING


def test_schema_validation_error_on_invalid_data(tmp_path: Path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps([{"invalid": "data"}]), encoding="utf-8")

    with pytest.raises(SchemaValidationError):
        load_dataset_file(bad_file, verify_checksum=False)


def test_filtering_test_cases(sample_test_case_dict):
    c1_dict = sample_test_case_dict
    c2_dict = sample_test_case_dict.copy()
    c2_dict["test_case_id"] = "TC-ADV-02"
    c2_dict["domain_segment"] = "insurance_enterprise"
    c2_dict["input_category"] = "adversarial"
    c2_dict["priority"] = "P0"

    from bdiplus_eval.core.schemas import EvalTestCase

    c1 = EvalTestCase.model_validate(c1_dict)
    c2 = EvalTestCase.model_validate(c2_dict)
    all_cases = [c1, c2]

    # Filter by domain
    banking = filter_test_cases(all_cases, domain_segment=DomainSegment.RETAIL_BANKING)
    assert len(banking) == 1
    assert banking[0].test_case_id == "TC-SAMPLE-01"

    # Filter by category
    adv = filter_test_cases(all_cases, input_category=InputCategory.ADVERSARIAL)
    assert len(adv) == 1
    assert adv[0].test_case_id == "TC-ADV-02"

    # Filter by priority
    p0 = filter_test_cases(all_cases, priority=PriorityTier.P0)
    assert len(p0) == 1
    assert p0[0].test_case_id == "TC-ADV-02"
