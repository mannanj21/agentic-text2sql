# Development Ablations

All runs use the 42-case development split, Groq `openai/gpt-oss-20b`, one
worker, and a rate-safe provider pace. Every report below recorded zero HTTP
429 responses. Token cost is reported as `$0.00` because provider pricing is
not configured in the client; it is not a claim of zero provider cost.

| Comparison | Accuracy | Success | p95 latency | Tokens | Decision |
|---|---:|---:|---:|---:|---|
| Default: planner off, retrieval, repair 3 | 37.5% | 64.3% | 1.09 s | 86,604 | Baseline |
| Planner on | 21.9% | 19.1% | 1.93 s | 94,959 | Drop planner; keep disabled |
| Full schema | 46.9% | 83.3% | 2.97 s | 118,594 | Keep full schema for v1 corpus |
| Repair 0 | 31.2% | 64.3% | 0.37 s | 75,584 | Do not use |
| Repair 1 | 37.5% | 64.3% | 0.37 s | 86,604 | Keep one attempt |
| Raw names only | 37.5% | 64.3% | 0.37 s | 86,604 | Keep descriptions; no measured gain |

Evidence reports: `evaluation/reports/20261011_131941_d965318_default_dev.md`,
`20261011_134052_c2fadf3_planner-on_dev.md`,
`20261011_140244_2cf9b3f_retrieval-full-schema_dev.md`,
`20261011_143458_8cff440_repair-0_dev.md`,
`20261011_143939_2d33c79_repair-1_dev.md`, and
`20261011_150048_8318cf1_raw-schema-names_dev.md`.

The later comparisons reuse the safe response cache, so their latency is not a
production-latency claim. The dataset is small; decisions are limited to this
v1 corpus and should be revisited for substantially larger schemas.
