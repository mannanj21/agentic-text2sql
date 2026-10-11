# ADR 0008: Planner disabled by default

## Decision

Keep `PLANNER_ENABLED=false`.

## Evidence

On the committed 42-case rate-safe development evaluation, planner-on reduced
execution accuracy from 37.5% to 21.9% while increasing token use from 86,604
to 94,959. See `docs/ablations.md`.

## Consequence

The planner remains available as an experiment, not a production default.
