# Final Held-Out Evaluation Attempt

## Status: invalid — do not report publicly

The one permitted S9.5 invocation of the frozen 18-case test split was run at
two cases per minute on the selected full-schema, one-repair configuration.
The Groq provider returned HTTP 429 for 13 cases. The resulting report is
therefore invalid for accuracy reporting and no headline metric is claimed.

Evidence: `evaluation/reports/20261011_151516_c280bee_default_test.md`.

An explicitly approved replacement run added 40-second per-provider-call
pacing, but it still received HTTP 429 for 11 cases. This indicates that the
provider's available rolling token allowance (or individual full-schema prompt
size) is insufficient; pacing alone is not enough. No further retry is made.
A future run requires a provider/model with sufficient token capacity or an
explicitly approved change to the held-out evaluation configuration.

## Baseline to final comparison

| Metric | Frozen pre-tuning baseline | S9.5 attempt |
|---|---:|---:|
| Held-out cases | 18 | 18 |
| Public execution accuracy | Not measured | Not reportable (rate-limited) |

The frozen baseline manifest is in `docs/eval/baseline-test.md`; it contains no
live measurement and is not comparable to this invalid attempt.
