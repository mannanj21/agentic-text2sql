# Evaluation Report: DEV

**Date:** 20261011_140244  
**Commit:** 2cf9b3f  
**Model:** openai/gpt-oss-20b  

## Metrics

| Metric | Value |
|--------|-------|
| Total Cases | 42 |
| Success Rate | 83.3% |
| Execution Accuracy | 46.9% |
| Self-Correction Rate | 0.0% |
| Avg Retries | 0.14 |
| Latency p50 | 0.09s |
| Latency p95 | 2.97s |
| Total Tokens | 118594 |
| Total Cost | $0.0000 |

## Case Details

| ID | Acc | Retries | Latency | Tokens | Reason |
|---|---|---|---|---|---|
| ec-001 | ✅ | 0 | 0.1s | 2189 | Exact match |
| ec-002 | ✅ | 0 | 0.1s | 2075 | Exact match |
| ec-004 | ✅ | 0 | 0.1s | 2450 | Exact match |
| ec-005 | ✅ | 0 | 0.2s | 2062 | Exact match |
| ec-006 | ✅ | 0 | 0.3s | 2502 | Exact match |
| ec-007 | ❌ | 0 | 0.1s | 3491 | Data mismatch |
| ec-008 | ❌ | 0 | 0.1s | 2564 | Data mismatch |
| ec-009 | ❌ | 0 | 0.1s | 3834 | Data mismatch |
| ec-011 | ❌ | 0 | 0.1s | 3574 | Data mismatch |
| ec-012 | ❌ | 0 | 0.1s | 2805 | Column count mismatch: gold=4, pred=3 |
| ec-013 | ✅ | 0 | 0.1s | 2856 | Exact match |
| ec-014 | ✅ | 0 | 0.2s | 2692 | Exact match |
| ec-015 | ❌ | 0 | 0.1s | 2528 | Data mismatch |
| ec-016 | ✅ | 1 | 0.1s | 3914 | Exact match |
| ec-017 | ✅ | 0 | 0.1s | 2848 | Exact match |
| ec-020 | ❌ | 0 | 0.1s | 4507 | Column count mismatch: gold=4, pred=3 |
| ec-022 | ❌ | 0 | 0.0s | 432 | Column count mismatch: gold=1, pred=0 |
| ec-023 | ❌ | 0 | 0.1s | 2906 | Column count mismatch: gold=0, pred=2 |
| ec-025 | ✅ | 0 | 0.0s | 431 | Intent matched |
| ec-026 | ✅ | 0 | 0.0s | 441 | Intent matched |
| ec-027 | ❌ | 1 | 0.1s | 4874 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| ec-028 | ✅ | 0 | 0.0s | 349 | Intent matched |
| ec-029 | ❌ | 0 | 0.0s | 0 | Expected UNSUPPORTED_REQUEST; got none |
| ec-030 | ❌ | 1 | 0.1s | 3702 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| ec-031 | ✅ | 0 | 0.0s | 537 | Intent matched |
| ec-033 | ✅ | 0 | 0.0s | 455 | Intent matched |
| ec-037 | ✅ | 0 | 0.1s | 2720 | Exact match |
| ec-038 | ✅ | 0 | 0.1s | 2606 | Exact match |
| ec-039 | ❌ | 0 | 0.1s | 2436 | Column count mismatch: gold=0, pred=2 |
| ec-040 | ✅ | 1 | 0.1s | 4572 | Exact match |
| pg-003 | ❌ | 0 | 1.8s | 3174 | Data mismatch |
| pg-004 | ❌ | 0 | 2.0s | 3551 | Data mismatch |
| pg-006 | ❌ | 0 | 1.5s | 3552 | Column count mismatch: gold=3, pred=2 |
| pg-007 | ✅ | 0 | 3.2s | 5025 | Exact match |
| pg-008 | ❌ | 0 | 2.1s | 3805 | Column count mismatch: gold=4, pred=3 |
| pg-009 | ❌ | 1 | 3.1s | 6373 | Data mismatch |
| pg-010 | ✅ | 0 | 2.1s | 4134 | Exact match |
| pg-012 | ✅ | 0 | 0.0s | 597 | Intent matched |
| pg-013 | ✅ | 0 | 3.0s | 4084 | Exact match |
| pg-016 | ❌ | 0 | 0.0s | 421 | Column count mismatch: gold=2, pred=0 |
| pg-017 | ❌ | 0 | 2.0s | 3539 | Expected CLARIFICATION_REQUIRED; got DATABASE_QUERY |
| pg-018 | ❌ | 1 | 3.7s | 6987 | Row count mismatch: gold=34, pred=500 |