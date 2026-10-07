"""Dataset loader, schema validator, and split assigner for the evaluation harness.

Usage
-----
    python -m evaluation.validate_dataset [--dataset datasets/ecommerce.yaml] [--all]
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator, model_validator

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

VALID_DBS = {"ecommerce", "pagila"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_CATEGORIES = {
    "aggregation",
    "join",
    "filter",
    "time",
    "grouping",
    "subquery",
    "schema_question",
    "followup",
    "ambiguous",
    "unsupported",
    "adversarial",
}
VALID_INTENTS = {
    "ANSWER",
    "CLARIFICATION_REQUIRED",
    "UNSUPPORTED_REQUEST",
    "SCHEMA_QUESTION",
}

# Deterministic split assignment: sha256(id + salt) → "test" if last hex nibble < 4
_SPLIT_SALT = "eval-v1-salt-42"
_TEST_SPLIT_THRESHOLD = 0x4  # ~25 % → ~20 test / ~55 dev for 55-60 questions


def _assign_split(item_id: str) -> str:
    """Deterministically assign 'dev' or 'test' based on the item ID."""
    digest = hashlib.sha256(f"{item_id}{_SPLIT_SALT}".encode()).hexdigest()
    return "test" if int(digest[-1], 16) < _TEST_SPLIT_THRESHOLD else "dev"


class DatasetCase(BaseModel):
    """A single evaluation case."""

    id: str
    db: str
    question: str
    gold_sql: str
    difficulty: str
    category: str
    expected_intent: str
    expected_tables: list[str]
    order_sensitive: bool = False
    followup_of: str | None = None
    notes: str | None = None
    split: str  # "dev" | "test" — validated against deterministic assignment

    @field_validator("db")
    @classmethod
    def validate_db(cls, v: str) -> str:
        if v not in VALID_DBS:
            msg = f"db must be one of {VALID_DBS}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        if v not in VALID_DIFFICULTIES:
            msg = f"difficulty must be one of {VALID_DIFFICULTIES}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            msg = f"category must be one of {VALID_CATEGORIES}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("expected_intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        if v not in VALID_INTENTS:
            msg = f"expected_intent must be one of {VALID_INTENTS}, got {v!r}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_split(self) -> DatasetCase:
        expected = _assign_split(self.id)
        if self.split != expected:
            msg = (
                f"Case {self.id!r}: declared split={self.split!r} but "
                f"deterministic assignment says {expected!r}. "
                "Do not change the split field manually."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def followup_implies_category(self) -> DatasetCase:
        if self.followup_of and self.category != "followup":
            msg = (
                f"Case {self.id!r}: followup_of is set but category is "
                f"{self.category!r}. Set category='followup'."
            )
            raise ValueError(msg)
        return self


class DatasetFile(BaseModel):
    """Top-level wrapper — a YAML file is a mapping with a 'cases' list."""

    cases: list[DatasetCase]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_dataset(path: Path) -> list[DatasetCase]:
    """Parse and validate a dataset YAML file. Raises ValueError on any error."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "cases" not in raw:
        msg = f"{path}: expected top-level dict with 'cases' key"
        raise ValueError(msg)
    ds = DatasetFile.model_validate(raw)
    return ds.cases


def load_all_datasets(datasets_dir: Path) -> list[DatasetCase]:
    """Load all *.yaml files in the datasets directory."""
    all_cases: list[DatasetCase] = []
    for yaml_file in sorted(datasets_dir.glob("*.yaml")):
        all_cases.extend(load_dataset(yaml_file))
    return all_cases


# ---------------------------------------------------------------------------
# Uniqueness and consistency checks
# ---------------------------------------------------------------------------


def check_uniqueness(cases: list[DatasetCase]) -> list[str]:
    """Return a list of error messages for duplicate IDs."""
    errors: list[str] = []
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            errors.append(f"Duplicate ID: {case.id!r}")
        seen.add(case.id)
    return errors


def check_followup_parents(cases: list[DatasetCase]) -> list[str]:
    """Return errors if a followup_of reference points to a non-existent ID."""
    all_ids = {c.id for c in cases}
    errors: list[str] = []
    for case in cases:
        if case.followup_of and case.followup_of not in all_ids:
            errors.append(
                f"Case {case.id!r}: followup_of={case.followup_of!r} not found"
            )
    return errors


def compute_split_stats(cases: list[DatasetCase]) -> dict[str, Any]:
    """Return a summary dict: counts by split, category, difficulty."""
    dev = [c for c in cases if c.split == "dev"]
    test = [c for c in cases if c.split == "test"]
    by_cat: dict[str, int] = {}
    by_diff: dict[str, int] = {}
    for c in cases:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
        by_diff[c.difficulty] = by_diff.get(c.difficulty, 0) + 1
    return {
        "total": len(cases),
        "dev": len(dev),
        "test": len(test),
        "by_category": by_cat,
        "by_difficulty": by_diff,
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _run_validation(datasets_dir: Path) -> bool:
    """Validate all datasets. Returns True if all pass."""
    print(f"Loading datasets from {datasets_dir} ...")
    try:
        cases = load_all_datasets(datasets_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return False

    errors: list[str] = []
    errors.extend(check_uniqueness(cases))
    errors.extend(check_followup_parents(cases))

    stats = compute_split_stats(cases)
    print(f"\nTotal cases : {stats['total']}")
    print(f"  dev       : {stats['dev']}")
    print(f"  test      : {stats['test']}")
    print(f"  by category: {stats['by_category']}")
    print(f"  by difficulty: {stats['by_difficulty']}")

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return False

    print("\nOK: all dataset cases are valid.")
    return True


if __name__ == "__main__":
    datasets_dir = Path(__file__).resolve().parent / "datasets"
    success = _run_validation(datasets_dir)
    sys.exit(0 if success else 1)
