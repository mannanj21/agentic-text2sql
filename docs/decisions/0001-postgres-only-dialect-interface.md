# ADR-0001: Postgres-Only with Dialect Interface

## Status

Accepted

## Context

The platform needs to connect to user databases to run SQL queries. Supporting multiple database engines (MySQL, SQL Server, etc.) adds significant complexity to the SQL validator, introspection, safety checks, and testing matrix.

However, we want to keep the door open for future dialect support without rewriting core modules.

## Decision

- Ship with **Postgres support only**. All SQL validation, introspection, and execution target the Postgres dialect.
- Define a `Dialect` protocol/interface in `app/database/dialect.py` that abstracts dialect-specific operations: introspection queries, timeout/session settings, EXPLAIN building, sqlglot dialect name, and safety-check queries.
- Implement `PostgresDialect` as the sole concrete implementation.
- Future dialects (e.g., MySQL) would implement the same protocol without changing core agent/validator logic.

## Consequences

- **Easier:** Focused testing, smaller attack surface, simpler validator rules, faster development.
- **Harder:** Users with MySQL databases cannot use the platform without contributing a dialect implementation.
- **Mitigated by:** The Dialect interface ensures adding MySQL later is an additive change, not a rewrite.
