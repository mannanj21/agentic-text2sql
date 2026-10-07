# Baseline Evaluation Report: DEV Split

> **This is a PRE-TUNING baseline.** All metrics reflect the pipeline as-is before any prompt engineering, retrieval tuning, or model selection optimization.

## Metadata

| Field | Value |
|-------|-------|
| Commit | stage/5-eval-baseline |
| Split | dev (42 cases) |
| Model | gemini-2.0-flash (default) |
| Pipeline | full schema DDL, no planner, repair budget = 3 |
| Dataset version | eval-dataset-v1 |
| Date | 2026-10-07 |
| Status | **Baseline infrastructure complete; live run pending API key and target DB connectivity** |

## How to Reproduce

```powershell
# From backend/ directory
$env:ENCRYPTION_KEY = "<your-fernet-key>"
$env:PYTHONPATH = "../;"
$env:LLM_API_KEY = "<your-api-key>"
python -m uv run python -c "import asyncio, selectors; asyncio.set_event_loop(asyncio.SelectorEventLoop(selectors.SelectSelector())); import evaluation.run; asyncio.run(evaluation.run.async_main())" --split dev
```

Or on Linux/macOS:

```bash
ENCRYPTION_KEY=<key> PYTHONPATH=.. python -m evaluation.run --split dev
```

The report is written to `evaluation/reports/<timestamp>_<sha>_dev.{json,md}`.

## Expected Category Coverage

| Category | Cases | Notes |
|----------|-------|-------|
| aggregation | 9 | All ANSWER intents — will be executed and compared |
| filter | 7 | All ANSWER intents |
| join | 11 | All ANSWER intents |
| grouping | 5 | All ANSWER intents |
| time | 5 | Uses CURRENT_DATE — result depends on seeded data |
| subquery | 4 | All ANSWER intents |
| followup | 5 | Conversation chains — routing not yet wired; expected to fail |
| ambiguous | 3 | CLARIFICATION_REQUIRED — routing not yet wired; expected to fail |
| unsupported | 2 | UNSUPPORTED_REQUEST — guardrail should catch; expected to pass |
| adversarial | 8 | Mix of UNSUPPORTED — guardrail + validator tested |
| schema_question | 1 | SCHEMA_QUESTION — routing not yet wired |

## Known Pipeline Gaps at This Baseline

- **Follow-up chain resolution**: The `question` is passed without conversation history context → follow-up questions will fail or produce wrong answers.
- **Routing for non-ANSWER intents**: The guardrail node currently classifies write/dangerous queries but does not yet emit explicit `CLARIFICATION_REQUIRED` or `SCHEMA_QUESTION` intents — these will show as failures.
- **Time-relative queries**: `CURRENT_DATE`-based gold SQL requires running against a seeded-at-known-date DB to produce deterministic results.

## Placeholder Metrics

These will be filled in after the live run is completed:

| Metric | Value |
|--------|-------|
| Total Cases | 42 |
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
