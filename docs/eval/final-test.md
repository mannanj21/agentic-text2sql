# Final Held-Out Evaluation Attempt

## Status: invalid — do not report publicly

The one permitted S9.5 invocation of the frozen 18-case test split was run at
two cases per minute on the selected full-schema, one-repair configuration.
The Groq provider returned HTTP 429 for 13 cases. The resulting report is
therefore invalid for accuracy reporting and no headline metric is claimed.

Evidence: `evaluation/reports/20261011_151516_c280bee_default_test.md`.

No retry is performed automatically: the implementation plan limits the
held-out split to one final run. A future retry requires explicit human
approval after provider capacity is sufficient and the evaluator can pace LLM
calls by token budget, not only by case starts.

## Baseline to final comparison

| Metric | Frozen pre-tuning baseline | S9.5 attempt |
|---|---:|---:|
| Held-out cases | 18 | 18 |
| Public execution accuracy | Not measured | Not reportable (rate-limited) |

The frozen baseline manifest is in `docs/eval/baseline-test.md`; it contains no
live measurement and is not comparable to this invalid attempt.
