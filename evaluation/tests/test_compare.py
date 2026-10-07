"""Unit tests for the result-set comparison logic [S5.3]."""

import datetime
from decimal import Decimal

from evaluation.compare import compare_results


def test_identical():
    gold = [(1, "apple"), (2, "banana")]
    pred = [(1, "apple"), (2, "banana")]
    res = compare_results(gold, pred, order_sensitive=True)
    assert res.exact_match
    assert res.lenient_match


def test_alias_only_difference():
    # We simulate alias differences by using dicts
    gold = [{"id": 1, "name": "apple"}]
    pred = [{"user_id": 1, "fruit_name": "apple"}]
    res = compare_results(gold, pred, order_sensitive=False)
    assert res.exact_match


def test_reordered_rows_no_order_by():
    gold = [(1, "a"), (2, "b")]
    pred = [(2, "b"), (1, "a")]
    res = compare_results(gold, pred, order_sensitive=False)
    assert res.exact_match


def test_reordered_with_order_by():
    gold = [(1, "a"), (2, "b")]
    pred = [(2, "b"), (1, "a")]
    res = compare_results(gold, pred, order_sensitive=True)
    assert not res.exact_match
    assert not res.lenient_match


def test_float_tolerance():
    gold = [(10.000000001,)]
    pred = [(10.000000000,)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert res.exact_match


def test_duplicates_counted():
    gold = [(1,), (1,)]
    pred = [(1,)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert not res.exact_match
    assert "Row count mismatch" in res.reason


def test_duplicates_counted_multiset():
    gold = [(1,), (1,), (2,)]
    pred = [(1,), (2,), (2,)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert not res.exact_match


def test_empty_vs_empty():
    res = compare_results([], [], order_sensitive=False)
    assert res.exact_match


def test_null_vs_null():
    gold = [(None, 1)]
    pred = [(None, 1)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert res.exact_match


def test_null_vs_zero():
    gold = [(None,)]
    pred = [(0,)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert not res.exact_match


def test_column_order_swap_unequal():
    gold = [(1, "a")]
    pred = [("a", 1)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert not res.exact_match


def test_type_equivalent_numerics():
    gold = [(1, 2.0, Decimal("3.0"))]
    pred = [(1.0, 2, 3)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert res.exact_match


def test_date_timestamp_normalization():
    gold = [(datetime.date(2023, 1, 1),)]
    pred = [(datetime.datetime(2023, 1, 1, 0, 0, 0),)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert res.exact_match


def test_string_whitespace_trimming():
    gold = [(" hello ",)]
    pred = [("hello",)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert res.exact_match

    res_no_trim = compare_results(gold, pred, order_sensitive=False, strip_strings=False)
    assert not res_no_trim.exact_match


def test_superset_columns_lenient():
    gold = [(1, "a")]
    pred = [(1, "a", "extra_col_value")]
    res = compare_results(gold, pred, order_sensitive=False)
    assert not res.exact_match
    assert res.lenient_match
    assert "Lenient match" in res.reason


def test_subset_columns_mismatch():
    gold = [(1, "a")]
    pred = [(1,)]
    res = compare_results(gold, pred, order_sensitive=False)
    assert not res.exact_match
    assert not res.lenient_match
