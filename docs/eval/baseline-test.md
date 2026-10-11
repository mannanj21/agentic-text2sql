# Baseline Evaluation Report: TEST Split

> **FROZEN BASELINE SNAPSHOT** — This file documents the test-split baseline taken before any tuning.
> Do NOT re-run against the test split except at the S9.5 final evaluation.

## Metadata

| Field | Value |
|-------|-------|
| Commit | stage/5-eval-baseline |
| Split | test (18 cases) |
| Model | gemini-2.0-flash (default) |
| Pipeline | full schema DDL, no planner, repair budget = 3 |
| Dataset version | eval-dataset-v1 |
| Date | 2026-10-07 |
| Status | **Frozen; live run pending. Do NOT modify test split or re-run until S9.5.** |

## Warning

> [!CAUTION]
> The test split is **frozen**. After this baseline is recorded, changes to the test-split IDs or gold SQL are forbidden. Development and tuning must use the dev split only. The test split is only used at S9.5 for the final held-out evaluation.

## Test Split Cases (18)

| ID | DB | Category | Difficulty |
|----|----|----------|------------|
| ec-003 | ecommerce | aggregation | easy |
| ec-010 | ecommerce | join | medium |
| ec-018 | ecommerce | time | hard |
| ec-019 | ecommerce | subquery | hard |
| ec-021 | ecommerce | followup | easy |
| ec-024 | ecommerce | ambiguous | easy |
| ec-032 | ecommerce | adversarial | easy |
| ec-034 | ecommerce | time | hard |
| ec-035 | ecommerce | subquery | hard |
| ec-036 | ecommerce | join | medium |
| pg-001 | pagila | aggregation | easy |
| pg-002 | pagila | aggregation | easy |
| pg-005 | pagila | filter | easy |
| pg-011 | pagila | adversarial | easy |
| pg-014 | pagila | join | hard |
| pg-015 | pagila | followup | medium |
| pg-019 | pagila | adversarial | easy |
| pg-020 | pagila | join | hard |

## Placeholder Metrics

| Metric | Value |
|--------|-------|
| Total Cases | 18 |
| Success Rate | — |
| Execution Accuracy | — |
| Routing Accuracy | — |
| Schema Precision | — |
| Schema Recall | — |
| Self-Correction Rate | — |
| Avg Retries | — |
| Latency p50 | — |
| Latency p95 | — |
| Total Tokens | — |
| Total Cost | — |
