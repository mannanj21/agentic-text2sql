# ADR 0009: Full schema context for v1

## Decision

Set `RETRIEVAL_MIN_TABLES=999`, so the current v1 demo schemas use full-schema
context by default.

## Evidence

On the committed 42-case rate-safe development evaluation, full-schema context
improved execution accuracy from 37.5% to 46.9% and schema recall from 65.6%
to 93.8%. See `docs/ablations.md`.

## Consequence

Vector retrieval remains implemented for larger-schema experiments. Revisit
this threshold when evaluating databases larger than the v1 corpus.
