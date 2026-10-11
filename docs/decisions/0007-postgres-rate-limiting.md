# ADR-0007: Postgres-Backed Fixed-Window Rate Limiting

## Status

Accepted

## Context

The API runs on multiple replicas, so process-local counters would permit each
replica to admit a separate quota. Introducing Redis solely for counters would
add another production service and operational failure mode.

## Decision

Use the application Postgres database. Each counter is atomically incremented
with `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` and is keyed by user and
UTC minute. Query and costly connection operations use authenticated user IDs.
Login attempts use an HMAC-SHA256 digest of the normalized email so failed or
unknown login attempts are protected without storing raw email addresses in
the counter table. Rows older than two minutes are deleted during increments.

## Consequences

Postgres provides shared, durable counters and correct cross-replica atomicity
without a new service. The fixed window allows a small burst around minute
boundaries and adds a small write to the app database for protected requests.
Redis remains a future option if limiter write volume becomes material.
