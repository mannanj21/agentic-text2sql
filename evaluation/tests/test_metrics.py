"""Unit tests for metrics computation [S5.4]."""

from evaluation.metrics import EvalResult, compute_metrics


def test_empty_results():
    report = compute_metrics([])
    assert report.total == 0
    assert report.success_rate == 0.0


def test_execution_accuracy():
    results = [
        EvalResult(
            case_id="1", split="dev", difficulty="easy", category="agg",
            expected_intent="ANSWER", success=True, accuracy=True, lenient_accuracy=True,
            expected_tables={"t1"}, used_tables={"t1"},
            retries=0, tokens=100, cost=0.01, latency_llm=1.0, latency_db=0.1, latency_total=1.1,
            error=None, reason="Exact match"
        ),
        EvalResult(
            case_id="2", split="dev", difficulty="easy", category="agg",
            expected_intent="ANSWER", success=True, accuracy=False, lenient_accuracy=False,
            expected_tables={"t1"}, used_tables={"t1"},
            retries=0, tokens=100, cost=0.01, latency_llm=1.0, latency_db=0.1, latency_total=1.1,
            error=None, reason="Mismatch"
        ),
    ]
    report = compute_metrics(results)
    assert report.total == 2
    assert report.execution_accuracy == 0.5
    assert report.routing_accuracy == 0.0  # no non-answer intents


def test_schema_precision_recall():
    results = [
        EvalResult(
            case_id="1", split="dev", difficulty="easy", category="agg",
            expected_intent="ANSWER", success=True, accuracy=True, lenient_accuracy=True,
            expected_tables={"t1", "t2"}, used_tables={"t1", "t3"},
            retries=0, tokens=0, cost=0, latency_llm=0, latency_db=0, latency_total=0,
            error=None, reason=""
        ),
    ]
    report = compute_metrics(results)
    # Expected: t1, t2. Used: t1, t3.
    # TP=1 (t1). FP=1 (t3). FN=1 (t2).
    # Precision = 1 / (1 + 1) = 0.5
    # Recall = 1 / (1 + 1) = 0.5
    assert report.schema_precision == 0.5
    assert report.schema_recall == 0.5


def test_self_correction_rate():
    results = [
        # Retried and succeeded
        EvalResult(
            case_id="1", split="dev", difficulty="easy", category="agg",
            expected_intent="ANSWER", success=True, accuracy=True, lenient_accuracy=True,
            expected_tables=set(), used_tables=set(),
            retries=2, tokens=0, cost=0, latency_llm=0, latency_db=0, latency_total=0,
            error=None, reason=""
        ),
        # Retried and failed
        EvalResult(
            case_id="2", split="dev", difficulty="easy", category="agg",
            expected_intent="ANSWER", success=True, accuracy=False, lenient_accuracy=False,
            expected_tables=set(), used_tables=set(),
            retries=3, tokens=0, cost=0, latency_llm=0, latency_db=0, latency_total=0,
            error=None, reason=""
        ),
        # No retries
        EvalResult(
            case_id="3", split="dev", difficulty="easy", category="agg",
            expected_intent="ANSWER", success=True, accuracy=True, lenient_accuracy=True,
            expected_tables=set(), used_tables=set(),
            retries=0, tokens=0, cost=0, latency_llm=0, latency_db=0, latency_total=0,
            error=None, reason=""
        ),
    ]
    report = compute_metrics(results)
    # Retries = 2 cases. 1 succeeded.
    assert report.self_correction_rate == 0.5
    assert report.avg_retries == (2 + 3 + 0) / 3


def test_latencies():
    results = []
    for i in range(100):
        results.append(
            EvalResult(
                case_id=str(i), split="dev", difficulty="easy", category="agg",
                expected_intent="ANSWER", success=True, accuracy=True, lenient_accuracy=True,
                expected_tables=set(), used_tables=set(),
                retries=0, tokens=0, cost=0, latency_llm=0, latency_db=0, latency_total=i,
                error=None, reason=""
            )
        )
    report = compute_metrics(results)
    # 0..99
    # p50 = idx int((100-1)*0.5) = int(49.5) = 49
    # p95 = idx int((100-1)*0.95) = int(94.05) = 94
    assert report.latency_p50 == 49.0
    assert report.latency_p95 == 94.0
