"""Phase 1 Acceptance Test: Golden Datasets & Cryptographic Integrity Verification.

Terminal command:
    pytest tests/unit/test_phase1_datasets.py -v
"""

from pathlib import Path
import pytest

from bdiplus_eval.core.schemas import (
    DomainSegment,
    EvalTestCase,
    InputCategory,
    PriorityTier,
)
from bdiplus_eval.datasets.loader import (
    compute_file_sha256,
    load_checksum_manifest,
    load_dataset_file,
    load_datasets_from_directory,
    verify_dataset_integrity,
)


def test_checksum_manifest_integrity():
    """Verify that every file registered in checksums.sha256 matches on disk."""
    manifest_path = Path("data/checksums.sha256")
    assert manifest_path.is_file(), "Manifest file data/checksums.sha256 must exist"

    manifest = load_checksum_manifest(manifest_path)
    expected_files = {
        "expected_cases.json",
        "degraded_cases.json",
        "segment_cases.json",
        "adversarial_cases.json",
    }
    assert set(manifest.keys()) == expected_files, (
        f"Manifest must contain exactly all 4 golden datasets: {expected_files}"
    )

    for fname, expected_hash in manifest.items():
        fpath = Path("data/golden") / fname
        assert fpath.is_file(), f"Dataset file {fpath} does not exist"
        actual_hash = compute_file_sha256(fpath)
        assert actual_hash.lower() == expected_hash.lower(), (
            f"Checksum mismatch for {fname}: expected {expected_hash}, got {actual_hash}"
        )
        assert verify_dataset_integrity(fpath, manifest_path=manifest_path) is True


def test_expected_dataset_content():
    """Verify expected_cases.json has at least 50 valid cases."""
    cases = load_dataset_file("data/golden/expected_cases.json", verify_checksum=True)
    assert len(cases) >= 50, f"Expected at least 50 expected cases, got {len(cases)}"
    for c in cases:
        assert isinstance(c, EvalTestCase)
        assert c.input_category == InputCategory.EXPECTED
        assert len(c.input_prompt) > 0
        assert len(c.expected_entities) > 0
        assert c.domain_segment in (
            DomainSegment.RETAIL_BANKING,
            DomainSegment.INSURANCE_ENTERPRISE,
        )


def test_degraded_dataset_content():
    """Verify degraded_cases.json has at least 30 valid cases."""
    cases = load_dataset_file("data/golden/degraded_cases.json", verify_checksum=True)
    assert len(cases) >= 30, f"Expected at least 30 degraded cases, got {len(cases)}"
    for c in cases:
        assert isinstance(c, EvalTestCase)
        assert c.input_category == InputCategory.DEGRADED
        assert len(c.input_prompt) > 0
        assert "degraded_type" in c.metadata


def test_segment_dataset_content():
    """Verify segment_cases.json has at least 40 valid cases."""
    cases = load_dataset_file("data/golden/segment_cases.json", verify_checksum=True)
    assert len(cases) >= 40, f"Expected at least 40 segment cases, got {len(cases)}"
    for c in cases:
        assert isinstance(c, EvalTestCase)
        assert c.input_category == InputCategory.SEGMENT_SPECIFIC
        assert len(c.input_prompt) > 0
        assert len(c.allowed_topics) > 0


def test_adversarial_dataset_content():
    """Verify adversarial_cases.json has at least 30 P0 cases."""
    cases = load_dataset_file("data/golden/adversarial_cases.json", verify_checksum=True)
    assert len(cases) >= 30, f"Expected at least 30 adversarial cases, got {len(cases)}"
    for c in cases:
        assert isinstance(c, EvalTestCase)
        assert c.input_category == InputCategory.ADVERSARIAL
        assert c.priority == PriorityTier.P0, (
            f"Adversarial case {c.test_case_id} must have priority P0"
        )
        assert c.injection_type is not None, (
            f"Adversarial case {c.test_case_id} must specify injection_type"
        )


def test_aggregate_suite_and_unique_ids():
    """Verify full suite aggregate loading and global ID uniqueness."""
    all_cases = load_datasets_from_directory(
        "data/golden",
        verify_checksums=True,
        manifest_path="data/checksums.sha256",
    )
    assert len(all_cases) >= 150, f"Expected >= 150 total cases, got {len(all_cases)}"

    # Check ID uniqueness
    all_ids = [c.test_case_id for c in all_cases]
    assert len(all_ids) == len(set(all_ids)), "Duplicate test_case_id detected across datasets"
