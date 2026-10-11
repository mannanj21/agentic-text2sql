# Design

## Two database boundary

The app database stores users, encrypted connection records, schema metadata,
conversations, runs, traces, and LangGraph checkpoints. Target databases hold
user data and are reached only by `app.tools.introspection` and
`app.tools.execution`. Graph state contains IDs and compact metadata, never
credentials or raw result rows.

## Workflow and persistence

LangGraph coordinates guardrail, contextualization/routing, schema context,
optional planning, generation, validation, execution, verification/repair, and
answering. Checkpoints are runtime-resume state; `messages` are the durable UI
history. `runs`, `run_steps`, and attempts provide a single tracing model for
the API, UI, and diagnostics.

## Safety and reliability

`ValidatedSQL` is constructed only by the validator. The executor accepts that
opaque value, starts a read-only transaction, applies timeout/row limits, and
uses a server-side cursor. Validation is defense in depth: target credentials
belong to a read-only database role, while the validator blocks non-SELECT AST
nodes, unsafe functions, catalogs, unauthorized schemas, and sensitive
columns. See [security.md](security.md).

Repair has one shared, bounded budget for validation, execution, and
verification failure. This prevents unbounded loops and makes retries
observable.

## Retrieval and product decisions

The system supports embeddings, glossary hits, top-k retrieval, FK expansion,
and compact schema rendering. Development evidence showed full schema context
outperformed retrieval on the small v1 corpus, so the threshold defaults to
full schema. The optional planner is disabled because its ablation reduced
accuracy while increasing tokens. Details: [ablations.md](ablations.md),
[ADR 0008](decisions/0008-planner-disabled-by-default.md), and
[ADR 0009](decisions/0009-full-schema-default.md).

## Scope

v1 is PostgreSQL-only behind a small dialect boundary. This keeps
introspection, validation, timeouts, and evaluation rigorous; MySQL and cloud
warehouses are explicitly deferred. The load-test findings and scale limits
are recorded in [loadtest.md](loadtest.md).
