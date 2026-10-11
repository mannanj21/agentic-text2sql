"""Unit tests for evaluation/validate_dataset.py [S5.1]."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers to make YAML content with correct deterministic splits
# ---------------------------------------------------------------------------

# ec-001 → dev, ec-003 → test (verified via the script)

GOOD_CASE_DEV = textwrap.dedent("""\
    cases:
      - id: ec-001
        db: ecommerce
        question: "How many customers are there?"
        gold_sql: "SELECT count(*) FROM public.customers"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: ["public.customers"]
        order_sensitive: false
        followup_of: null
        notes: null
        split: dev
""")

GOOD_CASE_TEST = textwrap.dedent("""\
    cases:
      - id: ec-003
        db: ecommerce
        question: "What is the total revenue?"
        gold_sql: "SELECT sum(amount) FROM public.orders"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: ["public.orders"]
        order_sensitive: false
        followup_of: null
        notes: null
        split: test
""")

GOOD_MULTI = textwrap.dedent("""\
    cases:
      - id: ec-001
        db: ecommerce
        question: "How many customers are there?"
        gold_sql: "SELECT count(*) FROM public.customers"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: ["public.customers"]
        order_sensitive: false
        followup_of: null
        notes: null
        split: dev
      - id: ec-003
        db: ecommerce
        question: "What is the total revenue?"
        gold_sql: "SELECT sum(amount) FROM public.orders"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: ["public.orders"]
        order_sensitive: false
        followup_of: null
        notes: null
        split: test
""")

BAD_SPLIT = textwrap.dedent("""\
    cases:
      - id: ec-001
        db: ecommerce
        question: "How many customers?"
        gold_sql: "SELECT count(*) FROM public.customers"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: ["public.customers"]
        order_sensitive: false
        followup_of: null
        notes: null
        split: test
""")  # ec-001 should be dev, not test

BAD_DB = textwrap.dedent("""\
    cases:
      - id: ec-001
        db: oracle
        question: "How many?"
        gold_sql: "SELECT count(*) FROM t"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: []
        order_sensitive: false
        followup_of: null
        notes: null
        split: dev
""")

BAD_FOLLOWUP_CATEGORY = textwrap.dedent("""\
    cases:
      - id: ec-002
        db: ecommerce
        question: "What about last year?"
        gold_sql: "SELECT count(*) FROM public.orders"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: []
        order_sensitive: false
        followup_of: ec-001
        notes: null
        split: dev
""")  # followup_of set but category is not 'followup'

BAD_FOLLOWUP_MISSING_PARENT = textwrap.dedent("""\
    cases:
      - id: ec-002
        db: ecommerce
        question: "What about last year?"
        gold_sql: "SELECT count(*) FROM public.orders"
        difficulty: easy
        category: followup
        expected_intent: ANSWER
        expected_tables: []
        order_sensitive: false
        followup_of: ec-nonexistent
        notes: null
        split: dev
""")

BAD_DUPLICATE_IDS = textwrap.dedent("""\
    cases:
      - id: ec-001
        db: ecommerce
        question: "How many customers are there?"
        gold_sql: "SELECT count(*) FROM public.customers"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: ["public.customers"]
        order_sensitive: false
        followup_of: null
        notes: null
        split: dev
      - id: ec-001
        db: ecommerce
        question: "Another question with same id"
        gold_sql: "SELECT 1"
        difficulty: easy
        category: aggregation
        expected_intent: ANSWER
        expected_tables: []
        order_sensitive: false
        followup_of: null
        notes: null
        split: dev
""")

NO_CASES_KEY = "metadata: {}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_yaml(tmp_path: Path):
    """Factory that writes YAML content to a temp file."""
    def _write(content: str) -> Path:
        p = tmp_path / "cases.yaml"
        p.write_text(content, encoding="utf-8")
        return p
    return _write


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_valid_single_dev(tmp_yaml):
    from evaluation.validate_dataset import load_dataset
    cases = load_dataset(tmp_yaml(GOOD_CASE_DEV))
    assert len(cases) == 1
    assert cases[0].id == "ec-001"
    assert cases[0].split == "dev"
    assert cases[0].difficulty == "easy"


def test_load_valid_single_test(tmp_yaml):
    from evaluation.validate_dataset import load_dataset
    cases = load_dataset(tmp_yaml(GOOD_CASE_TEST))
    assert len(cases) == 1
    assert cases[0].split == "test"


def test_load_valid_multi(tmp_yaml):
    from evaluation.validate_dataset import load_dataset
    cases = load_dataset(tmp_yaml(GOOD_MULTI))
    assert len(cases) == 2
    splits = {c.id: c.split for c in cases}
    assert splits["ec-001"] == "dev"
    assert splits["ec-003"] == "test"


def test_wrong_split_raises(tmp_yaml):
    from evaluation.validate_dataset import load_dataset
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="deterministic"):
        load_dataset(tmp_yaml(BAD_SPLIT))


def test_invalid_db_raises(tmp_yaml):
    from evaluation.validate_dataset import load_dataset
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="db must be one of"):
        load_dataset(tmp_yaml(BAD_DB))


def test_followup_without_category_raises(tmp_yaml):
    from evaluation.validate_dataset import load_dataset
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="category='followup'"):
        load_dataset(tmp_yaml(BAD_FOLLOWUP_CATEGORY))


def test_missing_cases_key_raises(tmp_yaml):
    from evaluation.validate_dataset import load_dataset
    with pytest.raises(ValueError, match="'cases'"):
        load_dataset(tmp_yaml(NO_CASES_KEY))


def test_duplicate_ids_flagged(tmp_yaml):
    from evaluation.validate_dataset import check_uniqueness, load_dataset
    from pydantic import ValidationError
    # Duplicate IDs at parse time won't fail validation (Pydantic just parses a list)
    # So we check the post-load uniqueness function
    # First we need to allow invalid split so we skip split validation for duplicates test
    # Load what we can and check uniqueness
    cases = load_dataset(tmp_yaml(BAD_DUPLICATE_IDS))
    errors = check_uniqueness(cases)
    assert any("Duplicate ID" in e and "ec-001" in e for e in errors)


def test_followup_missing_parent_flagged(tmp_yaml):
    from evaluation.validate_dataset import check_followup_parents, load_dataset
    cases = load_dataset(tmp_yaml(BAD_FOLLOWUP_MISSING_PARENT))
    errors = check_followup_parents(cases)
    assert any("ec-nonexistent" in e for e in errors)


def test_split_stats(tmp_yaml):
    from evaluation.validate_dataset import compute_split_stats, load_dataset
    cases = load_dataset(tmp_yaml(GOOD_MULTI))
    stats = compute_split_stats(cases)
    assert stats["total"] == 2
    assert stats["dev"] == 1
    assert stats["test"] == 1
    assert stats["by_category"]["aggregation"] == 2
    assert stats["by_difficulty"]["easy"] == 2


def test_assign_split_deterministic():
    from evaluation.validate_dataset import _assign_split
    # Same ID always gives same result
    assert _assign_split("ec-001") == "dev"
    assert _assign_split("ec-003") == "test"
    # Calling twice gives same result
    assert _assign_split("ec-001") == _assign_split("ec-001")
