"""Result-set comparison logic for the evaluation harness [S5.3]."""

import datetime
import decimal
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

@dataclass
class ComparisonResult:
    """Result of comparing two query execution outputs."""
    exact_match: bool
    lenient_match: bool  # True if it matches under "superset columns" lenient mode
    reason: str


def _normalize_value(val: Any, strip_strings: bool = True) -> Any:
    """Normalize a single cell value for comparison."""
    if val is None:
        return None
        
    # Convert all numerics to float for equivalence (Decimal, int, float)
    if isinstance(val, (int, float, decimal.Decimal)):
        # We use a wrapper or we just return float. But math.isclose needs to be used later.
        # So we just return float here.
        return float(val)
        
    # Date/timestamp normalization: convert date to datetime at midnight, then to ISO string
    if isinstance(val, datetime.datetime):
        return val.isoformat()
    if isinstance(val, datetime.date):
        return datetime.datetime.combine(val, datetime.time.min).isoformat()
        
    # String normalization
    if isinstance(val, str):
        return val.strip() if strip_strings else val
        
    return val


def _values_are_close(v1: Any, v2: Any, rel_tol: float = 1e-5, abs_tol: float = 1e-8) -> bool:
    """Compare two normalized values, allowing float tolerance."""
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False
        
    if isinstance(v1, float) and isinstance(v2, float):
        if math.isnan(v1) and math.isnan(v2):
            return True
        if math.isinf(v1) and math.isinf(v2):
            return (v1 > 0) == (v2 > 0)
        return math.isclose(v1, v2, rel_tol=rel_tol, abs_tol=abs_tol)
        
    return v1 == v2


def _rows_match(row1: tuple[Any, ...], row2: tuple[Any, ...]) -> bool:
    """Compare two tuples of normalized values."""
    if len(row1) != len(row2):
        return False
    return all(_values_are_close(v1, v2) for v1, v2 in zip(row1, row2))


def compare_results(
    gold_rows: Sequence[Sequence[Any]],
    pred_rows: Sequence[Sequence[Any]],
    order_sensitive: bool = False,
    strip_strings: bool = True,
) -> ComparisonResult:
    """
    Compare two result sets.
    
    Args:
        gold_rows: List of tuples representing the gold SQL result.
        pred_rows: List of tuples representing the predicted SQL result.
        order_sensitive: True if row order matters (i.e. gold has ORDER BY).
        strip_strings: True to whitespace-trim strings before comparing.
        
    Returns:
        ComparisonResult with exact and lenient match booleans.
    """
    if not gold_rows and not pred_rows:
        return ComparisonResult(exact_match=True, lenient_match=True, reason="Both empty")

    # We assume gold_rows and pred_rows are sequences of sequences (like list of tuples).
    # If they are dicts, we extract their values to compare by position, not by name.
    def extract_row(r: Any) -> tuple[Any, ...]:
        if hasattr(r, "values"):
            return tuple(r.values())
        return tuple(r)

    gold = [extract_row(r) for r in gold_rows]
    pred = [extract_row(r) for r in pred_rows]
    
    # Normalize values
    gold_norm = [tuple(_normalize_value(v, strip_strings) for v in r) for r in gold]
    pred_norm = [tuple(_normalize_value(v, strip_strings) for v in r) for r in pred]
    
    gold_cols = len(gold_norm[0]) if gold_norm else 0
    pred_cols = len(pred_norm[0]) if pred_norm else 0
    
    if gold_cols == 0 and pred_cols == 0:
        return ComparisonResult(exact_match=True, lenient_match=True, reason="Both empty columns")
        
    lenient = False
    lenient_pred_norm = pred_norm
    
    if pred_cols > gold_cols and gold_cols > 0:
        # Lenient superset checking: prediction returned extra columns.
        # We truncate prediction columns to match gold columns.
        lenient = True
        lenient_pred_norm = [r[:gold_cols] for r in pred_norm]
    elif pred_cols != gold_cols:
        return ComparisonResult(
            exact_match=False, 
            lenient_match=False, 
            reason=f"Column count mismatch: gold={gold_cols}, pred={pred_cols}"
        )

    if len(gold_norm) != len(pred_norm):
        return ComparisonResult(
            exact_match=False,
            lenient_match=False,
            reason=f"Row count mismatch: gold={len(gold_norm)}, pred={len(pred_norm)}"
        )

    # Helper to check row lists
    def check_sets(g_list: list[tuple[Any, ...]], p_list: list[tuple[Any, ...]]) -> bool:
        if order_sensitive:
            return all(_rows_match(g, p) for g, p in zip(g_list, p_list))
        else:
            # Multiset comparison: we need to handle float tolerance, so we can't just use Counter
            # on the tuples if floats are slightly different.
            # We do a naive O(N^2) bipartite matching for small result sets, which is fine for eval.
            p_used = set()
            for g_row in g_list:
                found = False
                for i, p_row in enumerate(p_list):
                    if i not in p_used and _rows_match(g_row, p_row):
                        p_used.add(i)
                        found = True
                        break
                if not found:
                    return False
            return True

    exact_match = False
    if not lenient:
        exact_match = check_sets(gold_norm, pred_norm)
        lenient_match = exact_match
    else:
        lenient_match = check_sets(gold_norm, lenient_pred_norm)
        
    if exact_match:
        reason = "Exact match"
    elif lenient_match:
        reason = f"Lenient match (pred had {pred_cols} cols, gold had {gold_cols})"
    else:
        reason = "Data mismatch"
        if not order_sensitive and len(gold_norm) == len(pred_norm):
            # Check if it would match with order sensitive just in case? No.
            pass

    return ComparisonResult(exact_match=exact_match, lenient_match=lenient_match, reason=reason)
