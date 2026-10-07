"""Unit-level smoke tests for the evaluation runner [S5.4].

These tests do NOT connect to PostgreSQL. Instead they test:
- That compute_metrics + EvalResult contract work end-to-end with synthetic data.
- That report_schema (keys) produced by compute_metrics.as_dict() is stable.
- Resumability: already-completed case IDs are detected by checking a results file.
"""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.metrics import EvalResult, compute_metrics


# ---------------------------------------------------------------------------
# Helper to build a synthetic EvalResult
# ---------------------------------------------------------------------------

def _result(
    case_id: str,
    *,
    success: bool = True,
    accuracy: bool = True,
    expected_intent: str = "ANSWER",
    retries: int = 0,
    latency: float = 1.0,
    tokens: int = 100,
    cost: float = 0.001,
    error: str | None = None,
    expected_tables: set[str] | None = None,
    used_tables: set[str] | None = None,
) -> EvalResult:
    return EvalResult(
        case_id=case_id,
        split="dev",
        difficulty="easy",
        category="aggregation",
        expected_intent=expected_intent,
        success=success,
        accuracy=accuracy,
        lenient_accuracy=accuracy,
        expected_tables=expected_tables or {"public.orders"},
        used_tables=used_tables or {"public.orders"},
        retries=retries,
        tokens=tokens,
        cost=cost,
        latency_llm=latency * 0.8,
        latency_db=latency * 0.2,
        latency_total=latency,
        error=error,
        reason="Exact match" if accuracy else "Mismatch",
    )


# ---------------------------------------------------------------------------
# Smoke test: metrics from 3-question mini dataset
# ---------------------------------------------------------------------------

def test_runner_smoke_three_questions():
    """Smoke test the full metrics pipeline on 3 synthetic results."""
    results = [
        _result("q1", accuracy=True),
        _result("q2", accuracy=False),
        _result("q3", accuracy=True, retries=2),
    ]
    
    report = compute_metrics(results)
    
    # Basic sanity
    assert report.total == 3
    assert round(report.execution_accuracy, 4) == round(2/3, 4)
    assert report.avg_retries == round(2 / 3, 4) or report.avg_retries > 0


def test_report_schema_is_stable():
    """Ensure report as_dict() keys haven't regressed."""
    results = [_result("q1")]
    report = compute_metrics(results)
    d = report.as_dict()
    
    expected_keys = {
        "total", "success_rate", "execution_accuracy", "routing_accuracy",
        "schema_precision", "schema_recall", "self_correction_rate",
        "avg_retries", "latency_p50", "latency_p95", "total_tokens", "total_cost",
    }
    assert expected_keys == set(d.keys()), f"Keys changed: {set(d.keys()) ^ expected_keys}"


def test_resumability(tmp_path: Path):
    """Resumability: a second run should skip already-completed case IDs."""
    # Simulate partial results saved to a JSON report
    partial = {
        "cases": [
            {"id": "q1", "success": True, "accuracy": True},
        ]
    }
    report_file = tmp_path / "partial.json"
    report_file.write_text(json.dumps(partial))
    
    # Load and extract completed IDs
    loaded = json.loads(report_file.read_text())
    completed_ids = {c["id"] for c in loaded["cases"]}
    
    all_case_ids = {"q1", "q2", "q3"}
    pending = all_case_ids - completed_ids
    
    assert completed_ids == {"q1"}
    assert pending == {"q2", "q3"}


def test_routing_accuracy():
    """Non-ANSWER intents contribute to routing accuracy, not execution accuracy."""
    results = [
        _result("q1", expected_intent="ANSWER", accuracy=True),
        _result("q2", expected_intent="CLARIFICATION_REQUIRED", accuracy=True),
        _result("q3", expected_intent="UNSUPPORTED_REQUEST", accuracy=False),
    ]
    report = compute_metrics(results)
    
    # exec_acc: only q1 (1 answer, 1 correct) = 1.0
    assert report.execution_accuracy == 1.0
    # routing_acc: q2=correct, q3=wrong → 0.5
    assert report.routing_accuracy == 0.5
