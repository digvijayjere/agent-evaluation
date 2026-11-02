"""Dataset loading, validation, and cryptographic integrity checking.

Provides robust loaders for JSON/JSONL evaluation suites and verifies
SHA-256 signatures to guarantee immutability of golden datasets.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydantic import ValidationError

from agent_eval.core.schemas import (
    DomainSegment,
    EvalTestCase,
    InputCategory,
    PriorityTier,
)


class DatasetError(Exception):
    """Base exception for dataset-related errors."""


class IntegrityError(DatasetError):
    """Raised when a dataset file fails SHA-256 cryptographic verification."""


class SchemaValidationError(DatasetError):
    """Raised when dataset records fail Pydantic model validation."""


def compute_file_sha256(file_path: Union[str, Path]) -> str:
    """Compute the SHA-256 hex digest of a file in 64KB blocks."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_checksum_manifest(manifest_path: Union[str, Path]) -> Dict[str, str]:
    """Parse standard sha256 checksum manifest file.

    Format expected per line: '<hash>  <filename>' or '<hash> <filename>'
    Lines starting with '#' or blank lines are ignored.
    """
    path = Path(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"Checksum manifest not found: {path}")

    manifest: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#"):
                continue
            parts = cleaned.split()
            if len(parts) >= 2:
                file_hash = parts[0]
                # Normalize filename / path
                filename = parts[-1].replace("\\", "/").split("/")[-1]
                manifest[filename] = file_hash.lower()
    return manifest


def verify_dataset_integrity(
    file_path: Union[str, Path],
    manifest_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Verify SHA-256 checksum of a dataset file against manifest."""
    path = Path(file_path)
    if manifest_path is None:
        # Default fallback location
        manifest_path = path.parent.parent / "checksums.sha256"

    manifest_file = Path(manifest_path)
    if not manifest_file.exists():
        # Manifest not yet generated or optional
        return True

    manifest = load_checksum_manifest(manifest_file)
    expected_hash = manifest.get(path.name)
    if expected_hash is None:
        # File not registered in manifest
        return True

    actual_hash = compute_file_sha256(path)
    if actual_hash.lower() != expected_hash.lower():
        raise IntegrityError(
            f"Cryptographic integrity breach for '{path.name}'. "
            f"Expected SHA-256: {expected_hash}, Actual: {actual_hash}"
        )
    return True


def load_dataset_file(
    file_path: Union[str, Path],
    verify_checksum: bool = True,
    manifest_path: Optional[Union[str, Path]] = None,
) -> List[EvalTestCase]:
    """Load and validate an evaluation dataset from a JSON or JSONL file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    if verify_checksum:
        verify_dataset_integrity(path, manifest_path=manifest_path)

    cases: List[EvalTestCase] = []
    raw_content = path.read_text(encoding="utf-8").strip()

    if not raw_content:
        return cases

    # Support JSON array format
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as err:
            raise SchemaValidationError(f"Malformed JSON in {path.name}: {err}") from err

        if not isinstance(data, list):
            raise SchemaValidationError(f"Expected JSON array in {path.name}, got {type(data)}")

        for idx, item in enumerate(data):
            try:
                cases.append(EvalTestCase.model_validate(item))
            except ValidationError as err:
                raise SchemaValidationError(
                    f"Validation error in {path.name} at index {idx}: {err}"
                ) from err

    # Support JSONL (JSON Lines) format
    elif path.suffix.lower() in (".jsonl", ".txt"):
        for line_num, line in enumerate(raw_content.splitlines(), start=1):
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            try:
                item = json.loads(line_str)
            except json.JSONDecodeError as err:
                raise SchemaValidationError(
                    f"Malformed JSON line at {path.name}:{line_num}: {err}"
                ) from err
            try:
                cases.append(EvalTestCase.model_validate(item))
            except ValidationError as err:
                raise SchemaValidationError(
                    f"Validation error at {path.name}:{line_num}: {err}"
                ) from err
    else:
        raise DatasetError(f"Unsupported dataset file extension: {path.suffix}")

    return cases


def filter_test_cases(
    cases: List[EvalTestCase],
    domain_segment: Optional[Union[DomainSegment, str]] = None,
    input_category: Optional[Union[InputCategory, str]] = None,
    priority: Optional[Union[PriorityTier, str]] = None,
) -> List[EvalTestCase]:
    """Filter list of test cases by domain, category, or priority."""
    filtered = cases
    if domain_segment is not None:
        seg_val = domain_segment.value if isinstance(domain_segment, DomainSegment) else str(domain_segment)
        filtered = [c for c in filtered if c.domain_segment.value == seg_val]

    if input_category is not None:
        cat_val = input_category.value if isinstance(input_category, InputCategory) else str(input_category)
        filtered = [c for c in filtered if c.input_category.value == cat_val]

    if priority is not None:
        prio_val = priority.value if isinstance(priority, PriorityTier) else str(priority)
        filtered = [c for c in filtered if c.priority.value == prio_val]

    return filtered


def load_datasets_from_directory(
    directory: Union[str, Path] = "data/golden",
    domain_segment: Optional[Union[DomainSegment, str]] = None,
    input_category: Optional[Union[InputCategory, str]] = None,
    priority: Optional[Union[PriorityTier, str]] = None,
    verify_checksums: bool = True,
    manifest_path: Optional[Union[str, Path]] = None,
) -> List[EvalTestCase]:
    """Load all JSON/JSONL datasets from a directory with filtering."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Datasets directory not found: {dir_path}")

    all_cases: List[EvalTestCase] = []
    # Sort files for deterministic loading order
    files = sorted(list(dir_path.glob("*.json")) + list(dir_path.glob("*.jsonl")))

    for f in files:
        file_cases = load_dataset_file(
            f,
            verify_checksum=verify_checksums,
            manifest_path=manifest_path,
        )
        all_cases.extend(file_cases)

    return filter_test_cases(
        all_cases,
        domain_segment=domain_segment,
        input_category=input_category,
        priority=priority,
    )
