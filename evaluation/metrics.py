"""Metrics calculation for the evaluation harness [S5.4]."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any


@dataclass
class EvalResult:
    """The result of executing a single case."""
    case_id: str
    split: str
    difficulty: str
    category: str
    expected_intent: str
    
    # Outcomes
    success: bool  # True if it didn't error out entirely
    accuracy: bool # True if result exact matched gold, OR intent was correctly mapped
    lenient_accuracy: bool 
    
    # Schema selection
    expected_tables: set[str]
    used_tables: set[str]
    
    # Latency / Steps
    retries: int
    tokens: int
    cost: float
    
    # Node latencies in seconds
    latency_llm: float
    latency_db: float
    latency_total: float
    
    # Extra debug info
    error: str | None
    reason: str


@dataclass
class MetricsReport:
    """Aggregated metrics."""
    total: int
    success_rate: float
    execution_accuracy: float
    routing_accuracy: float
    schema_precision: float
    schema_recall: float
    self_correction_rate: float
    avg_retries: float
    latency_p50: float
    latency_p95: float
    total_tokens: int
    total_cost: float
    
    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "success_rate": round(self.success_rate, 4),
            "execution_accuracy": round(self.execution_accuracy, 4),
            "routing_accuracy": round(self.routing_accuracy, 4),
            "schema_precision": round(self.schema_precision, 4),
            "schema_recall": round(self.schema_recall, 4),
            "self_correction_rate": round(self.self_correction_rate, 4),
            "avg_retries": round(self.avg_retries, 2),
            "latency_p50": round(self.latency_p50, 2),
            "latency_p95": round(self.latency_p95, 2),
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
        }


def compute_metrics(results: list[EvalResult]) -> MetricsReport:
    """Compute aggregate metrics over a list of results."""
    if not results:
        return MetricsReport(
            total=0, success_rate=0.0, execution_accuracy=0.0, routing_accuracy=0.0,
            schema_precision=0.0, schema_recall=0.0, self_correction_rate=0.0,
            avg_retries=0.0, latency_p50=0.0, latency_p95=0.0, total_tokens=0, total_cost=0.0
        )
        
    total = len(results)
    
    # Success rate
    successes = sum(1 for r in results if r.success)
    success_rate = successes / total
    
    # Accuracy
    # Execution accuracy applies to ANSWER intents
    answer_results = [r for r in results if r.expected_intent == "ANSWER"]
    exec_acc = sum(1 for r in answer_results if r.accuracy) / len(answer_results) if answer_results else 0.0
    
    # Routing accuracy applies to non-ANSWER intents
    route_results = [r for r in results if r.expected_intent != "ANSWER"]
    route_acc = sum(1 for r in route_results if r.accuracy) / len(route_results) if route_results else 0.0
    
    # Schema precision/recall
    precisions = []
    recalls = []
    for r in results:
        if r.expected_tables:
            tp = len(r.expected_tables.intersection(r.used_tables))
            fp = len(r.used_tables - r.expected_tables)
            fn = len(r.expected_tables - r.used_tables)
            
            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            
            precisions.append(p)
            recalls.append(rec)
            
    schema_precision = sum(precisions) / len(precisions) if precisions else 0.0
    schema_recall = sum(recalls) / len(recalls) if recalls else 0.0
    
    # Self-correction rate (fraction of cases that had retries and eventually succeeded)
    retry_cases = [r for r in results if r.retries > 0]
    self_corr = sum(1 for r in retry_cases if r.success and r.accuracy) / len(retry_cases) if retry_cases else 0.0
    
    avg_retries = sum(r.retries for r in results) / total
    
    # Latencies
    latencies = sorted([r.latency_total for r in results])
    
    def percentile(data: list[float], p: float) -> float:
        if not data:
            return 0.0
        idx = int((len(data) - 1) * p)
        return data[idx]
        
    latency_p50 = percentile(latencies, 0.5)
    latency_p95 = percentile(latencies, 0.95)
    
    total_tokens = sum(r.tokens for r in results)
    total_cost = sum(r.cost for r in results)
    
    return MetricsReport(
        total=total,
        success_rate=success_rate,
        execution_accuracy=exec_acc,
        routing_accuracy=route_acc,
        schema_precision=schema_precision,
        schema_recall=schema_recall,
        self_correction_rate=self_corr,
        avg_retries=avg_retries,
        latency_p50=latency_p50,
        latency_p95=latency_p95,
        total_tokens=total_tokens,
        total_cost=total_cost,
    )
