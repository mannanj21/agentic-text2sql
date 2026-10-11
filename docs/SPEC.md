# Agentic Text-to-SQL Analytics Platform: Project Specification (v2)

## 1. Definition

A full-stack agentic analytics platform that turns natural-language questions into validated SQL, retrieves only the relevant database context, repairs failed queries within a bounded budget, executes them safely against user-connected PostgreSQL databases, verifies results, and returns explainable tables and charts with a full execution trace and **measured** evaluation metrics.

**Purpose:** a resume/interview project (SDE / AI Engineer). Every feature must earn its place by improving at least one of: agent-engineering depth, software-engineering depth, reliability/security, measurable quality, or interview value.

**Timeline:** 4-6 weeks. **Scope rule:** if a feature isn't in Must or Should, it doesn't get built until those are done.

---

## 2. Scope

### Priorities

| Tier | Items |
|---|---|
| **Must** | Auth; Postgres connect + introspection; LangGraph workflow (contextualize/route → retrieve → generate → validate → execute → repair → answer); three-layer safety; `runs`/`run_steps` tracing; evaluation harness; Docker Compose; three-level tests; CI |
| **Should** | pgvector schema retrieval; SSE streaming; rule-based charts; planner ablation; deterministic result verification; 2-replica deployment + load test; connection safety check |
| **Could** | MySQL dialect; LLM-based result check; error-driven re-retrieval; column-masking UI; eval dashboard UI |

### Non-goals (explicitly out)

Voice, fine-tuning, Kubernetes, mobile app, cloud warehouses (Snowflake/BigQuery/Redshift/Databricks), MongoDB as a user data source, fine-grained RBAC, enterprise data catalog, human approval on every query, multi-agent "swarms" (no specialized agent per table).

### Dialect decision

**Postgres-only for v1**, behind a small `Dialect` interface (introspection, timeout mechanism, EXPLAIN, sqlglot dialect name). MySQL is a stretch goal. Supporting two dialects roughly doubles introspection, validation, timeout, and eval work for little added signal. "Designed for a second dialect" is an honest and defensible claim.

---

## 3. Architecture

Two kinds of databases, kept strictly separate:

- **App DB** (Postgres + pgvector): users, connections, schema metadata + embeddings, conversations, messages, runs, run steps, LangGraph checkpoints, rate-limit counters.
- **Target DBs**: the user's databases, accessed **read-only** through a dedicated execution module. Nothing else in the system touches them.

```
                 ┌────────────────────┐
                 │ Next.js + Tailwind │  chat · trace view · charts · history
                 └─────────┬──────────┘
                           │ REST + SSE
                  nginx (2 API replicas)
                           │
                 ┌─────────▼──────────┐
                 │      FastAPI       │  auth · rate limit · API
                 └─────────┬──────────┘
                           │
                 ┌─────────▼──────────────────────────────┐
                 │               LangGraph                │
                 │  guardrail (deterministic)             │
                 │     ↓                                  │
                 │  contextualize + route  (1 small LLM)  │
                 │     ↓                                  │
                 │  retrieve schema (pgvector + FK expand)│
                 │     ↓                                  │
                 │  [plan]  (feature flag)                │
                 │     ↓                                  │
                 │  generate SQL (structured output)      │
                 │     ↓                                  │
                 │  validate ──fail──┐                    │
                 │     ↓ pass        │                    │
                 │  execute ──error──┤                    │
                 │     ↓ ok          ▼                    │
                 │  verify ──fail──► repair (shared       │
                 │     ↓ pass        budget, max 3)       │
                 │  answer + chart spec                   │
                 └──────┬───────────────────────┬─────────┘
                        │                       │
                App DB (Postgres+pgvector)   Target DB(s)
                users · metadata · runs      read-only role
                checkpoints                  timeout · row cap
```

### Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind, Recharts |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy 2 (+ inspector), Alembic, psycopg3 (async) |
| Agent | LangGraph, LangChain (structured output), `langgraph-checkpoint-postgres` |
| SQL analysis | `sqlglot` |
| Vector search | pgvector in the app DB |
| LLM | Provider-agnostic `LLMClient` wrapper: one hosted provider, optional Ollama. Two tiers: `FAST_MODEL` (routing), `STRONG_MODEL` (generation/repair/answer). Token counts and cost recorded per step |
| Embeddings | One pinned model (BGE-M3 via Ollama fits your RAG experience). Record model + dimension; changing it requires re-embedding |
| Infra | Docker, Docker Compose, nginx, GitHub Actions |
| Observability | Own `runs`/`run_steps` tables (primary). Langfuse/LangSmith optional |

---

## 4. Functional Requirements

### A. Users, conversations, connections

**FR-1 Auth & ownership.** Email + password (argon2/bcrypt), session via httpOnly cookie or JWT. Every connection, conversation, and run belongs to a user. **Authorization tests are required**: user A must never read or use user B's connections, conversations, runs, or schema metadata.

**FR-2 Conversations.** Create, list, rename, delete, resume. Multi-turn context is built from the last N turns (question, final SQL, short answer summary; **never result rows**).

**FR-3 Follow-ups.** The contextualize step rewrites a follow-up ("compare that with last year") into a standalone question using prior turns. The **current date is injected into prompts** so "last quarter" resolves correctly.

**FR-4 Database connection.** User supplies host, port, database, username, password. The system:
- tests the connection and stores credentials **encrypted at rest** (Fernet/AES with the key from env; never in Git);
- decrypts them only inside the execution/introspection module. **Credentials never enter graph state, prompts, traces, or logs**; graph state carries only `connection_id`;
- runs a **connection safety check**: verify the role has no write privileges (e.g. `has_table_privilege` for INSERT/UPDATE/DELETE across tables, not superuser). If it can write, refuse by default and show how to create a read-only role (a documented SQL snippet is provided);
- applies **SSRF protection**: resolve the hostname, reject loopback/private/link-local/metadata-service IPs (e.g. 169.254.169.254), and connect to the *resolved* IP to prevent DNS rebinding. `ALLOW_PRIVATE_HOSTS=true` overrides this for the Docker demo.

The repo ships with pre-seeded demo databases so the product works without connecting anything.

### B. Schema knowledge

**FR-5 Introspection.** On connect (background task, status `introspecting → ready | failed`), discover tables, columns, types, primary keys, foreign keys, indexes, and approximate row counts (`pg_class.reltuples`). Store an internal schema representation in the app DB. Support re-sync.

**FR-6 Metadata enrichment (v1 = auto + optional edits).**
- LLM-generated table and column descriptions (background job, cost-capped; regenerable).
- User can edit descriptions and add **glossary terms** (`"sales" → SUM(order_items.quantity * unit_price)`, `"active customer" → ordered in last 90 days`). The glossary is the mechanism for fuzzy business terms.
- **Sample values are opt-in per connection** (they leave your system for a third-party LLM) and never collected for sensitive columns.
- **Sensitive-column denylist** (user-marked, plus name heuristics like `password`, `ssn`, `email`): excluded from prompts and samples **and blocked in the validator**.

**FR-7 Schema retrieval (the RAG component).**
1. Embed table-level and column-level descriptions (pgvector).
2. Retrieve top-k tables by similarity to the standalone question, and pull in glossary hits.
3. **FK expansion**: add tables one join away from retrieved tables so join paths stay intact.
4. Pass only that subset (DDL-style compact format) to the LLM.

Small schemas (under a configurable table count) may skip retrieval and send everything; this is also your ablation baseline.

### C. Agent workflow

**FR-8 Guardrail (deterministic, not an LLM call).** Max input length, basic injection heuristics, empty input. Heuristics are weak by nature; the *real* defenses are structural (see §6). Say so in the README.

**FR-9 Contextualize + route (one small-model call).** Outputs structured JSON:
- `intent`: `DATABASE_QUERY | SCHEMA_QUESTION | CLARIFICATION_REQUIRED | UNSUPPORTED_REQUEST`
- `standalone_question`
- `clarification` (question to ask the user, if needed)

`SCHEMA_QUESTION` is answered from stored metadata with no SQL. `CLARIFICATION_REQUIRED` returns a question to the user (e.g. an ambiguous term not in the glossary). Note: any error in routing is costly, so route accuracy is an eval metric.

**FR-10 Query planning (feature-flagged: `PLANNER_ENABLED`).** Produces a structured plan (tables, joins, filters, aggregation, group by, limit). It is a **hypothesis to test, not a given**: the planner adds an LLM call, and explicit planning doesn't reliably help strong models. You will run the ablation (§7) and keep or drop it on the data.

**FR-11 SQL generation.** Input: standalone question, retrieved schema, glossary hits, optional plan, dialect, current date. Output (Pydantic structured output): `{ "sql": ..., "tables_used": [...], "assumptions": [...] }`. Never parse free-form prose.

**FR-12 SQL validation** (all must pass before execution):
1. **Parse** with `sqlglot` (Postgres dialect). Exactly **one** statement.
2. **AST allowlist**: root is `SELECT` (with optional `WITH`). Walk the whole tree and reject any node that isn't allowed, so this catches data-modifying CTEs (`WITH x AS (DELETE … RETURNING *)`), `SELECT INTO`, `FOR UPDATE/SHARE`, `COPY`, and DDL/DML anywhere in the tree.
3. **Function policy**: reject dangerous functions (`pg_sleep`, `pg_read_file`, `pg_ls_dir`, `lo_*`, `dblink*`, `set_config`, `pg_terminate_backend`, etc.). An allowlist of functions is safer than a denylist if time permits.
4. **Table/column policy**: referenced tables must belong to the connection's allowed schemas; sensitive columns are blocked; `pg_catalog`/`information_schema` blocked unless explicitly allowed.
5. **Schema check via `EXPLAIN`** (no `ANALYZE`) inside a read-only transaction. The database itself reports unknown tables/columns and type errors, so there's no need to hand-build a column resolver.

> The validator is **defense in depth**. The real security boundary is the database role (§6). A "correct join" cannot be validated deterministically; join correctness is measured by the eval, not the validator.

**FR-13 Execution.** Only validated SQL runs, and only through the execution module:
- `BEGIN READ ONLY`; session settings `default_transaction_read_only = on`, `statement_timeout` (5-10 s), `lock_timeout`;
- fetch at most `MAX_RESULT_ROWS + 1` rows through a server-side cursor to detect truncation without rewriting the SQL; return a `truncated` flag;
- per-connection pool, LRU-capped per replica;
- errors are classified (`syntax`, `unknown_identifier`, `timeout`, `permission`, `other`) and fed to repair.

**FR-14 Result verification (deterministic first).** Checks: empty result, all-null columns, column count vs. the plan/expected shape, row count of 1 when a grouped result was expected, truncated output. Failure draws from the shared repair budget. An LLM-based check is a Could item.

**FR-15 Repair (single shared budget).** Validation failures, execution errors, and failed verification **all draw from one budget: `MAX_REPAIR_ATTEMPTS = 3`**. The repair node receives the failed SQL, the failure type and message, and the relevant schema. *(Could: on `unknown_identifier`, re-run retrieval with larger k.)* Every attempt (SQL, error, outcome) is stored in `run_attempts`. After the budget is exhausted, return a controlled failure with the last error and the attempts. No unbounded loops, and the graph has a hard recursion limit as a backstop.

**FR-16 Answer generation (one call).** Input to the LLM is a **summary, not raw rows**: column names, row count, per-column basic stats, and the first ~20 rows. This limits cost and privacy exposure, and reduces indirect prompt injection from cell contents. Result data is passed as delimited, explicitly untrusted content. Output: short answer text + assumptions. Currency and formatting come from the data, not from hard-coded symbols.

**FR-17 Visualization (rule-based, no LLM).** A pure function `choose_chart(columns, rows)` returns a spec `{type, x, y, title}` from result shape:

| Shape | Chart |
|---|---|
| date/time column + numeric | line |
| low-cardinality category + numeric | bar |
| single value | single_value |
| anything else | table |

Deterministic and unit-testable. The frontend renders the spec with Recharts. No pie charts.

### D. Observability & history

**FR-18 Tracing and history (one mechanism).** Every request creates a `run` with ordered `run_steps` (node name, start/end, latency, status, tool, tokens in/out, cost, error) and `run_attempts`. The UI trace view, query history, and observability are all queries over these tables. Store the SQL, result *metadata* (columns, row count, truncated), and an optional capped preview (default 50 rows, configurable off) so history can be reopened without re-running. Do not store sensitive data unnecessarily.

**FR-19 Streaming.** The query endpoint streams node events over SSE (`node_started`, `node_finished`, `sql_generated`, `attempt_failed`, `final`), so the UI shows progress live. Runs are persisted server-side even if the client disconnects. (Reconnect/resume is out of scope.)

**FR-20 Evaluation.** See §7. Mandatory.

---

## 5. Agent state and persistence

- **Graph state** (small, serializable): `run_id`, `conversation_id`, `connection_id`, `question`, `standalone_question`, `intent`, `retrieved_schema_ids`, `plan?`, `sql`, `attempts[]`, `repair_budget_remaining`, `result_meta`, `chart_spec`, `answer`. **No credentials, no result rows.**
- **LangGraph Postgres checkpointer** persists graph state per `thread_id = conversation_id`, so any replica can continue a conversation.
- **`messages` table** holds UI-facing conversation history.
- Be ready to justify having both: checkpoints are the agent's runtime state, and messages are the product's durable record.

---

## 6. Security model

Three layers plus platform hygiene. The database role is the boundary; everything above it is defense in depth.

| Layer | Controls |
|---|---|
| **Input** | Length limits; deterministic heuristics; user input and result data always delimited as untrusted; the agent has **no tool capable of writes** |
| **SQL** | Single statement; AST allowlist; function policy; table/column policy incl. sensitive columns; `EXPLAIN` check |
| **Database** | Read-only role (documented `CREATE ROLE … LOGIN`, `GRANT SELECT` on allowed schemas, `ALTER ROLE … SET default_transaction_read_only = on`, `SET statement_timeout`); read-only transaction; timeout; row cap; per-connection pools; connection safety check rejects roles with write privileges |
| **Platform** | Encrypted credentials; SSRF protection; no secrets in Git (`.env.example` only); parameterized queries for *the platform's own* SQL (this is the real meaning of "SQL injection" here); per-user rate limiting; authorization tests |

**Rate limiting:** a Postgres-backed fixed-window counter per user (works across replicas, keeps a single datastore). A single Redis container is the alternative; the trade-off is one more service. Decide in week 5 and document it. An in-memory limiter is wrong for a multi-replica deployment.

**Security test corpus (required):** multi-statement input; data-modifying CTEs; `SELECT INTO`; `FOR UPDATE`; `COPY`; `pg_sleep`; `pg_read_file`; `dblink`; `set_config`; comment/case tricks; catalog access; sensitive-column access; prompt-injection strings in the question and inside cell values. Each must be blocked or neutralized.

---

## 7. Evaluation (mandatory)

### Datasets
- **Two Postgres databases**: one seed you control (e-commerce: customers, orders, order_items, products, with realistic dates) and one established sample (Pagila or Northwind). Spider/BIRD are SQLite-based, so use them for *inspiration* rather than directly.
- **50-60 hand-written questions** with gold SQL, each tagged `{difficulty: easy|medium|hard, category: aggregation|join|time|grouping|filtering|followup|ambiguous|unsupported|adversarial}`.
- Include ~5 follow-up chains, ~5 ambiguous questions (expected: clarification), ~5 unsupported, and ~10 adversarial/safety cases.
- **Split into dev and held-out test sets** (e.g. 35/20). Tune on dev only; report numbers from the held-out set.

### Metrics (precise definitions)

| Metric | Definition |
|---|---|
| **Execution success** | Query ran without error |
| **Execution accuracy** | Result set matches the gold result set. **Compare results, never SQL strings.** Ignore aliases; compare row multisets (order-sensitive only if gold has `ORDER BY`); numeric tolerance for floats |
| **Schema selection** | Table-level precision and recall of `retrieved_schema` vs. tables in gold SQL |
| **Routing accuracy** | Intent matches expected intent |
| **Safety pass rate** | Adversarial cases blocked/neutralized |
| **Self-correction rate** | Share of first-attempt failures that succeeded within budget |
| **Avg retries / latency / cost** | Per run, plus p50/p95 latency, split into LLM, retrieval, and DB time |

### Ablations (each with a before/after table)
1. Planner on vs. off (accuracy, latency, cost)
2. Schema retrieval (top-k) vs. full schema
3. Repair budget 0 / 1 / 3
4. Auto-generated descriptions vs. raw names only
5. Small vs. strong model for generation *(optional)*

### Tooling
`python -m evaluation.run --split test --config configs/default.yaml` writes a markdown/JSON report. **Build this in week 2 and record a baseline before any tuning**; every later change is measured against it. An eval UI is optional. Only report numbers you actually measured.

---

## 8. Non-Functional Requirements

**NFR-1 Reliability.** Never execute unvalidated SQL. Never loop unbounded. Failures return controlled errors. One failed query never breaks the session or service.

**NFR-2 Performance.** Target: typical successful query < 5 s (excluding unusually slow LLM/DB). Budget on the happy path: contextualize (1 small call) + generate (1) + answer (1) = 3 LLM calls, or 4 with the planner. Track total, LLM, retrieval, and DB latency separately. No sub-second claims.

**NFR-3 Scalability.** API is stateless; state lives in Postgres. Deploy **2 API replicas behind nginx** (with `proxy_buffering off` for SSE) and run a **Locust/k6 load test** (concurrent users, mixed question types). Expect LLM latency and DB pool sizing to dominate, and document the findings and the next scaling steps (queue for long queries, per-tenant limits, caching schema retrieval). No Kubernetes.

**NFR-4 Security.** See §6.

**NFR-5 Observability.** Every run is traceable: run ID, conversation ID, node, tool, latency, status, SQL, retry count, error, tokens/cost. Structured logs with `run_id` on every line. Logs never contain credentials or raw result data.

**NFR-6 Maintainability.**
```
frontend/
backend/
  api/          # FastAPI routes, auth, rate limiting
  agent/        # graph, nodes, state, prompts
  tools/        # execution, introspection, chart selection
  database/     # app-DB models, migrations, dialect interface
  guardrails/   # input checks, SQL validator, policies
  retrieval/    # embeddings, schema retrieval
  persistence/  # runs, messages, checkpointer wiring
  llm/          # LLMClient wrapper, cost tracking
evaluation/     # datasets, runner, metrics, reports
docs/           # design doc, decisions
```

**NFR-7 Testability.**
- **Unit**: validator (with the malicious corpus), chart rules, result verification, result-set comparison, SSRF checks.
- **Agent/tool tests with a fake LLM**: routing paths, repair budget exhaustion, controlled failure, no-execute-on-invalid.
- **Integration**: real Postgres (CI service container), read-only role behavior, timeouts, row caps, authorization.
- **End-to-end eval**: §7.
- Test **failure scenarios**, not just successes. CI runs lint + unit + agent + integration tests, and a small eval smoke run (manual trigger if it needs a paid LLM).

**NFR-8 Reproducibility.** `docker compose up` gives the full stack: `.env.example`, seed databases with a read-only role pre-created, Alembic migrations, eval dataset, README with architecture, setup, and a security-model section.

---

## 9. Data model (app DB)

| Table | Key columns |
|---|---|
| `users` | id, email, password_hash |
| `connections` | id, user_id, name, host, port, database, username, encrypted_password, sample_values_enabled, status, last_synced_at |
| `schema_tables` | id, connection_id, schema, name, description, row_estimate, embedding |
| `schema_columns` | id, table_id, name, data_type, is_pk, is_sensitive, description, sample_values, embedding |
| `schema_relationships` | id, connection_id, from_column_id, to_column_id |
| `glossary_terms` | id, connection_id, term, definition |
| `conversations` | id, user_id, connection_id, title, created_at |
| `messages` | id, conversation_id, role, content, run_id, created_at |
| `runs` | id, conversation_id, user_id, question, standalone_question, intent, status, total_latency_ms, retry_count, final_sql, result_meta, result_preview, tokens, cost, error |
| `run_steps` | id, run_id, seq, node, started_at, latency_ms, status, tool, tokens_in, tokens_out, cost, error |
| `run_attempts` | id, run_id, attempt_no, sql, failure_type, error, outcome |
| `rate_limits` | user_id, window_start, count |

(LangGraph creates its own checkpoint tables.)

---

## 10. API sketch

| Method & path | Purpose |
|---|---|
| `POST /auth/register`, `/auth/login`, `/auth/logout` | Auth |
| `POST /connections`, `GET /connections`, `DELETE /connections/{id}` | Connect/test/list/remove |
| `POST /connections/{id}/sync` | Re-introspect + regenerate metadata |
| `GET/PATCH /connections/{id}/schema` | View/edit descriptions, sensitive flags |
| `GET/POST/DELETE /connections/{id}/glossary` | Glossary terms |
| `POST /conversations`, `GET /conversations`, `DELETE /conversations/{id}` | Conversations |
| `POST /conversations/{id}/query` | Ask a question; **SSE stream** of node events + final result |
| `GET /runs/{id}` | Full trace: steps, attempts, SQL, result metadata |
| `GET /history` | Query history |

---

## 11. Timeline (6 weeks, week 6 = buffer)

| Week | Focus | Exit criteria |
|---|---|---|
| 1 | Skeleton, Compose, auth, connect + introspect, seed DBs, minimal graph (generate → validate → execute → answer), `runs` tables | Ask a question on the demo DB and see a traced run |
| 2 | Full validator + read-only role + safety check; repair loop; SSE; **eval harness + baseline** | Baseline report exists |
| 3 | pgvector retrieval, metadata enrichment, glossary, contextualize/route, follow-ups, planner + ablations | Each change has a before/after number |
| 4 | Frontend: chat, streaming, trace view, charts, history, schema/glossary editor | End-to-end demo works |
| 5 | Security corpus, authz tests, rate limiting, CI, 2 replicas + load test, README + design doc | CI green; load test numbers recorded |
| 6 | Buffer / polish / stretch (MySQL or LLM verification) | Final held-out eval + resume bullets |

---

## 12. Interview cheat-sheet: decisions you must be able to defend

| Decision | Alternative | Evidence to bring |
|---|---|---|
| Read-only DB role as the boundary; validator as defense in depth | Rely on prompt/validator alone | Security corpus results |
| AST allowlist, not keyword blocklist | Regex/blocklist | Data-modifying-CTE and `pg_sleep` tests |
| `EXPLAIN` for schema checks | Custom column resolver | Simpler, uses the DB as the source of truth |
| Single shared repair budget | Separate retry loops | Repair-budget ablation |
| Optional planner, decided by ablation | Always plan | Accuracy/latency/cost table |
| pgvector + FK expansion | Full schema in prompt | Schema-selection recall, token cost |
| Summary (not rows) to answer LLM | Send all rows | Cost, privacy, injection surface |
| Rule-based chart selection | LLM picks chart | Deterministic tests |
| Checkpointer + messages table | One or the other | Stateless replicas, resumable threads |
| Postgres-only, dialect interface | Two dialects at once | Scope control |
| Own tracing tables | Only a third-party tool | One data model for trace, history, and metrics |

**Known limitations to state honestly:** no guarantee of semantic correctness; ambiguous questions can still mislead; SSE has no reconnect; LLM latency dominates; sample-value privacy relies on user opt-in; injection heuristics are weak (structural defenses carry the load).

---

## 13. Definition of done

- [ ] `docker compose up` runs everything from a clean clone; README documents setup, architecture, security model
- [ ] Demo DBs seeded; a read-only role is pre-created
- [ ] All Must and Should items implemented (or explicitly deferred in the README)
- [ ] No path exists that executes SQL without validation (test-enforced)
- [ ] Security corpus passes; authorization tests pass
- [ ] Eval: baseline + final numbers on the held-out set; ablation tables in `docs/`
- [ ] Load test results recorded (2 replicas)
- [ ] CI green (lint, unit, agent, integration)
- [ ] Design doc written (`docs/design.md`)
- [ ] Resume bullets use **only measured** numbers

---

## Appendix: changes from your original spec

| Original | Change | Reason |
|---|---|---|
| Postgres + MySQL | Postgres-only, dialect interface, MySQL as stretch | Halves dialect work |
| Blocklist of statement types | AST allowlist + function policy + read-only role | Blocklists miss data-modifying CTEs and dangerous functions |
| "Validate relationships" | `EXPLAIN` check; join correctness measured by eval | Not deterministically checkable |
| Planner always on | Feature flag + ablation | Unproven benefit; costs latency |
| Six-plus LLM calls | 3-4 (deterministic guardrail, merged route+contextualize, merged answer) | Fit the < 5 s target |
| Separate retry rules (FR-12/13) | One shared repair budget | One loop to explain and test |
| LLM result verification | Deterministic checks first | Reliability, testability |
| LLM/rules unspecified for charts | Rule-based chart selection | Deterministic |
| Up to 1,000 rows to the answer LLM | Summary + ~20 rows | Cost, privacy, injection |
| Sample values always collected | Opt-in, skip sensitive columns | Privacy |
| No follow-up mechanism | Contextualize step + date injection | Follow-ups otherwise fail |
| Vague metrics | Precise definitions + dev/held-out split | Credible numbers |
| App DB and target DBs blurred | Explicitly separated | Clearer architecture and security |
| Separate trace/history/observability | One `runs` + `run_steps` model | Less duplication |
| Specialized/fuzzy agents from playlist | Glossary + clarification path | One mechanism, not extra agents |
| 100-question eval + dashboard | 50-60 questions + CLI/report | Buildable in the timeline |
| Missing | SSE, SSRF protection, connection safety check, credential handling, multi-replica rate limiting, load test, LLM/embedding decisions, authz tests | Gaps found in review |