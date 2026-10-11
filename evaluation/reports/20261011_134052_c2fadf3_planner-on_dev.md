# Evaluation Report: DEV

**Date:** 20261011_134052  
**Commit:** c2fadf3  
**Model:** openai/gpt-oss-20b  

## Metrics

| Metric | Value |
|--------|-------|
| Total Cases | 42 |
| Success Rate | 19.0% |
| Execution Accuracy | 21.9% |
| Self-Correction Rate | 0.0% |
| Avg Retries | 0.95 |
| Latency p50 | 0.09s |
| Latency p95 | 1.93s |
| Total Tokens | 94959 |
| Total Cost | $0.0000 |

## Case Details

| ID | Acc | Retries | Latency | Tokens | Reason |
|---|---|---|---|---|---|
| ec-001 | ✅ | 1 | 0.1s | 3086 | Exact match |
| ec-002 | ✅ | 1 | 0.1s | 2888 | Exact match |
| ec-004 | ✅ | 1 | 0.1s | 3099 | Exact match |
| ec-005 | ✅ | 1 | 0.1s | 2732 | Exact match |
| ec-006 | ❌ | 1 | 0.1s | 3375 | Lenient match (pred had 4 cols, gold had 3) |
| ec-007 | ❌ | 1 | 0.1s | 3311 | Data mismatch |
| ec-008 | ❌ | 1 | 0.1s | 3389 | Data mismatch |
| ec-009 | ❌ | 1 | 0.1s | 3784 | Data mismatch |
| ec-011 | ❌ | 1 | 0.1s | 3737 | Data mismatch |
| ec-012 | ❌ | 1 | 0.1s | 4819 | Column count mismatch: gold=4, pred=3 |
| ec-013 | ✅ | 1 | 1.9s | 3754 | Exact match |
| ec-014 | ❌ | 4 | 4.1s | 5622 | Column count mismatch: gold=2, pred=0 |
| ec-015 | ❌ | 1 | 0.1s | 3373 | Data mismatch |
| ec-016 | ❌ | 2 | 3.0s | 2457 | Column count mismatch: gold=1, pred=0 |
| ec-017 | ✅ | 1 | 0.8s | 3497 | Exact match |
| ec-020 | ❌ | 1 | 1.9s | 5322 | Data mismatch |
| ec-022 | ❌ | 0 | 0.0s | 432 | Column count mismatch: gold=1, pred=0 |
| ec-023 | ❌ | 1 | 0.1s | 3866 | Column count mismatch: gold=0, pred=3 |
| ec-025 | ✅ | 0 | 0.0s | 431 | Intent matched |
| ec-026 | ✅ | 0 | 0.0s | 441 | Intent matched |
| ec-027 | ❌ | 1 | 0.1s | 4853 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| ec-028 | ✅ | 0 | 0.0s | 349 | Intent matched |
| ec-029 | ❌ | 0 | 0.0s | 0 | Expected UNSUPPORTED_REQUEST; got none |
| ec-030 | ❌ | 1 | 0.1s | 3453 | Expected UNSUPPORTED_REQUEST; got DATABASE_QUERY |
| ec-031 | ✅ | 0 | 0.0s | 537 | Intent matched |
| ec-033 | ✅ | 0 | 0.0s | 455 | Intent matched |
| ec-037 | ✅ | 1 | 0.1s | 3813 | Exact match |
| ec-038 | ❌ | 1 | 0.1s | 3642 | Data mismatch |
| ec-039 | ❌ | 1 | 0.1s | 3525 | Column count mismatch: gold=0, pred=2 |
| ec-040 | ❌ | 4 | 0.1s | 5692 | Column count mismatch: gold=1, pred=0 |
| pg-003 | ❌ | 1 | 2.3s | 469 | Column count mismatch: gold=1, pred=0 |
| pg-004 | ❌ | 1 | 0.4s | 355 | Column count mismatch: gold=1, pred=0 |
| pg-006 | ❌ | 1 | 0.4s | 379 | Column count mismatch: gold=3, pred=0 |
| pg-007 | ❌ | 1 | 0.4s | 476 | Column count mismatch: gold=2, pred=0 |
| pg-008 | ❌ | 1 | 0.4s | 368 | Column count mismatch: gold=4, pred=0 |
| pg-009 | ❌ | 1 | 0.4s | 558 | Column count mismatch: gold=2, pred=0 |
| pg-010 | ❌ | 1 | 0.4s | 407 | Column count mismatch: gold=2, pred=0 |
| pg-012 | ✅ | 0 | 0.0s | 597 | Intent matched |
| pg-013 | ❌ | 1 | 0.4s | 373 | Column count mismatch: gold=2, pred=0 |
| pg-016 | ❌ | 0 | 0.0s | 421 | Column count mismatch: gold=2, pred=0 |
| pg-017 | ❌ | 1 | 0.3s | 365 | Expected CLARIFICATION_REQUIRED; got DATABASE_QUERY |
| pg-018 | ❌ | 1 | 0.4s | 457 | Column count mismatch: gold=3, pred=0 |