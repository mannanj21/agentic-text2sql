# Evaluation Report: DEV

**Date:** 20261011_125513  
**Commit:** ef5feec  
**Model:** openai/gpt-oss-20b  

## Metrics

| Metric | Value |
|--------|-------|
| Total Cases | 42 |
| Success Rate | 19.0% |
| Execution Accuracy | 18.8% |
| Self-Correction Rate | 0.0% |
| Avg Retries | 0.90 |
| Latency p50 | 0.92s |
| Latency p95 | 5.03s |
| Total Tokens | 84736 |
| Total Cost | $0.0000 |

## Case Details

| ID | Acc | Retries | Latency | Tokens | Reason |
|---|---|---|---|---|---|
| ec-001 | ✅ | 1 | 1.7s | 3086 | Exact match |
| ec-002 | ✅ | 1 | 0.9s | 2888 | Exact match |
| ec-004 | ✅ | 1 | 1.7s | 3099 | Exact match |
| ec-005 | ✅ | 1 | 0.7s | 2732 | Exact match |
| ec-006 | ❌ | 1 | 2.0s | 3375 | Lenient match (pred had 4 cols, gold had 3) |
| ec-007 | ❌ | 1 | 1.3s | 3311 | Data mismatch |
| ec-008 | ❌ | 1 | 1.0s | 3389 | Data mismatch |
| ec-009 | ❌ | 1 | 1.8s | 3784 | Data mismatch |
| ec-011 | ❌ | 1 | 1.7s | 3737 | Data mismatch |
| ec-012 | ❌ | 1 | 3.2s | 4819 | Column count mismatch: gold=4, pred=3 |
| ec-013 | ❌ | 1 | 3.9s | 409 | Column count mismatch: gold=2, pred=0 |
| ec-014 | ❌ | 2 | 5.3s | 2603 | Column count mismatch: gold=2, pred=0 |
| ec-015 | ❌ | 1 | 5.0s | 2497 | Data mismatch |
| ec-016 | ❌ | 2 | 4.9s | 2457 | Column count mismatch: gold=1, pred=0 |
| ec-017 | ✅ | 1 | 5.3s | 2660 | Exact match |
| ec-020 | ❌ | 1 | 7.4s | 3176 | Data mismatch |
| ec-022 | ❌ | 0 | 0.0s | 432 | Column count mismatch: gold=1, pred=0 |
| ec-023 | ❌ | 1 | 2.8s | 3866 | Column count mismatch: gold=0, pred=3 |
| ec-025 | ✅ | 0 | 0.0s | 431 | Intent matched |
| ec-026 | ✅ | 0 | 0.0s | 441 | Intent matched |
| ec-027 | ❌ | 1 | 0.3s | 4853 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| ec-028 | ✅ | 0 | 0.0s | 349 | Intent matched |
| ec-029 | ❌ | 0 | 0.0s | 0 | Expected UNSUPPORTED_REQUEST; got none |
| ec-030 | ❌ | 1 | 0.1s | 3453 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| ec-031 | ✅ | 0 | 0.0s | 537 | Intent matched |
| ec-033 | ✅ | 0 | 0.0s | 455 | Intent matched |
| ec-037 | ✅ | 1 | 1.1s | 3813 | Exact match |
| ec-038 | ❌ | 1 | 1.8s | 3642 | Data mismatch |
| ec-039 | ❌ | 1 | 1.4s | 3525 | Column count mismatch: gold=0, pred=2 |
| ec-040 | ❌ | 4 | 3.4s | 5692 | Column count mismatch: gold=1, pred=0 |
| pg-003 | ❌ | 1 | 2.8s | 469 | Column count mismatch: gold=1, pred=0 |
| pg-004 | ❌ | 1 | 0.4s | 355 | Column count mismatch: gold=1, pred=0 |
| pg-006 | ❌ | 1 | 0.4s | 379 | Column count mismatch: gold=3, pred=0 |
| pg-007 | ❌ | 1 | 0.5s | 476 | Column count mismatch: gold=2, pred=0 |
| pg-008 | ❌ | 1 | 0.5s | 368 | Column count mismatch: gold=4, pred=0 |
| pg-009 | ❌ | 1 | 0.4s | 558 | Column count mismatch: gold=2, pred=0 |
| pg-010 | ❌ | 1 | 1.7s | 407 | Column count mismatch: gold=2, pred=0 |
| pg-012 | ✅ | 0 | 0.0s | 597 | Intent matched |
| pg-013 | ❌ | 1 | 0.4s | 373 | Column count mismatch: gold=2, pred=0 |
| pg-016 | ❌ | 0 | 0.0s | 421 | Column count mismatch: gold=2, pred=0 |
| pg-017 | ❌ | 1 | 0.4s | 365 | Expected CLARIFICATION_REQUIRED; got DATABASE_QUERY |
| pg-018 | ❌ | 1 | 0.4s | 457 | Column count mismatch: gold=3, pred=0 |