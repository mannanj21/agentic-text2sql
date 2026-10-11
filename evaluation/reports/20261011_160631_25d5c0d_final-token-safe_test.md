# Evaluation Report: TEST

**Date:** 20261011_160631  
**Commit:** 25d5c0d  
**Model:** openai/gpt-oss-20b  

## Metrics

| Metric | Value |
|--------|-------|
| Total Cases | 18 |
| Success Rate | 27.8% |
| Execution Accuracy | 50.0% |
| Self-Correction Rate | 0.0% |
| Avg Retries | 0.17 |
| Latency p50 | 79.49s |
| Latency p95 | 81.50s |
| Total Tokens | 21313 |
| Total Cost | $0.0000 |

## Case Details

| ID | Acc | Retries | Latency | Tokens | Reason |
|---|---|---|---|---|---|
| ec-003 | ✅ | 0 | 0.1s | 2429 | Exact match |
| ec-010 | ❌ | 0 | 0.1s | 2833 | Column count mismatch: gold=0, pred=3 |
| ec-018 | ❌ | 0 | 0.1s | 3983 | Column count mismatch: gold=0, pred=4 |
| ec-019 | ✅ | 2 | 0.1s | 3073 | Both empty |
| ec-021 | ✅ | 0 | 0.9s | 2201 | Exact match |
| ec-024 | ✅ | 0 | 0.0s | 523 | Intent matched |
| ec-032 | ❌ | 1 | 160.3s | 2896 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| ec-034 | ✅ | 0 | 81.5s | 0 | Both empty |
| ec-035 | ✅ | 0 | 80.0s | 0 | Both empty |
| ec-036 | ✅ | 0 | 80.2s | 425 | Both empty |
| pg-001 | ❌ | 0 | 39.8s | 756 | Column count mismatch: gold=1, pred=0 |
| pg-002 | ❌ | 0 | 80.4s | 395 | Column count mismatch: gold=1, pred=0 |
| pg-005 | ❌ | 0 | 79.5s | 504 | Column count mismatch: gold=3, pred=0 |
| pg-011 | ❌ | 0 | 80.1s | 0 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| pg-014 | ✅ | 0 | 39.7s | 389 | Both empty |
| pg-015 | ❌ | 0 | 80.1s | 0 | Column count mismatch: gold=4, pred=0 |
| pg-019 | ❌ | 0 | 79.8s | 410 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| pg-020 | ❌ | 0 | 80.0s | 496 | Column count mismatch: gold=2, pred=0 |