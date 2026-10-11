"""Tests for the actual contents of the evaluation datasets [S5.2]."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from evaluation.validate_dataset import load_all_datasets

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"


@pytest.fixture(scope="module")
def all_cases():
    return load_all_datasets(DATASETS_DIR)


def test_split_proportions(all_cases):
    """Ensure the split proportions are roughly correct (20-30% test)."""
    assert len(all_cases) >= 50, "Expected at least 50 cases in total"
    
    dev_count = sum(1 for c in all_cases if c.split == "dev")
    test_count = sum(1 for c in all_cases if c.split == "test")
    
    total = dev_count + test_count
    test_pct = test_count / total
    
    assert 0.15 <= test_pct <= 0.40, f"Test split ratio {test_pct:.2f} is outside expected range (15%-40%)"


def test_no_test_ids_in_prompts(all_cases):
    """Ensure no test-split IDs are leaked into prompts or few-shot examples."""
    test_ids = {c.id for c in all_cases if c.split == "test"}
    assert test_ids, "Should have at least some test cases"
    
    # Search all .py files in backend/app for these IDs
    # (In a real scenario, we might just grep, but here we do a simple scan)
    
    python_files = list(BACKEND_DIR.rglob("*.py"))
    leaks = []
    
    for py_file in python_files:
        if "tests" in py_file.parts:
            continue
            
        try:
            content = py_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
            
        for test_id in test_ids:
            # Look for the exact ID string (e.g. "ec-003")
            if re.search(r'\b' + re.escape(test_id) + r'\b', content):
                leaks.append(f"Found test ID {test_id!r} in {py_file.name}")
                
    assert not leaks, "Test set IDs leaked into backend code:\n" + "\n".join(leaks)
