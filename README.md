# Agentic Text-to-SQL Analytics Platform

[![CI](https://github.com/mannanj21/agentic-text2sql/actions/workflows/ci.yml/badge.svg)](https://github.com/mannanj21/agentic-text2sql/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/status-in%20development-orange)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Ask questions about your database in plain English. An agentic pipeline (LangGraph) turns the question into SQL, **validates it against a strict safety policy**, runs it **read-only** against the target database, and explains the result, with a full trace of every step.

Repository: <https://github.com/mannanj21/agentic-text2sql>

> **Project status (2026-09-29): Stages 0-3 complete, Stage 4 in progress (step S4.2).**
> The backend can already answer a question end-to-end on the demo databases (generate → validate → execute → answer) with persisted traces. Streaming, the repair loop, evaluation, retrieval, the frontend, and deployment hardening are still ahead. See the [Roadmap](#roadmap) for the exact state of every step.

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Security model](#security-model)
- [Progress: what is done](#progress-what-is-done)
- [Roadmap: what is left](#roadmap)
- [Repository layout](#repository-layout)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Testing](#testing)
- [Engineering workflow](#engineering-workflow)
- [Metrics](#metrics)
- [Known limitations](#known-limitations)
- [License](#license)

---

## What it does

**Working today (backend):**

- User accounts with argon2 password hashing and httpOnly cookie sessions.
- Connect your own PostgreSQL database. Credentials are encrypted at rest (Fernet), the host is checked against SSRF rules, and the DB role is inspected to make sure it is **not** write-capable.
- Automatic schema introspection (tables, columns, PKs/FKs, indexes, row estimates) with conservative sensitive-column defaults, plus editable descriptions and a glossary.
- Conversations API: ask a question, get back the SQL, the answer, and a persisted run trace (steps, latency, tokens, cost).
- A multi-layer SQL validator (AST allowlist, function policy, schema and sensitive-column policy, `EXPLAIN` check) that is the only way to produce an executable statement.
- Two demo databases (e-commerce and Pagila) with read-only and writer roles for safety testing.

**Planned:** streaming answers (SSE), self-repair loop, evaluation harness with baseline/ablations, schema retrieval with embeddings, intent routing and follow-ups, chart selection, Next.js UI, rate limiting, 2-replica nginx deployment, load testing.

## Architecture

```
                 ┌──────────────┐        ┌───────────────────────────────┐
  Browser  ───►  │  FastAPI     │  ───►  │  LangGraph pipeline           │
  (Stage 7)      │  (auth,      │        │  generate → validate →        │
                 │   API, SSE)  │        │  execute → answer             │
                 └──────┬───────┘        └───────┬───────────────┬───────┘
                        │                        │               │
                 ┌──────▼───────┐         ┌──────▼──────┐  ┌─────▼──────────────┐
                 │   App DB     │         │  LLM client │  │ tools/execution.py │
                 │ PostgreSQL + │         │ Gemini /    │  │ read-only, pinned  │
                 │ pgvector     │         │ Ollama /    │  │ IP, timeouts,      │
                 │ (users, runs,│         │ Fake        │  │ accepts ONLY       │
                 │  schema meta,│         └─────────────┘  │ ValidatedSQL       │
                 │  checkpoints)│                          └─────┬──────────────┘
                 └──────────────┘                                │
                                                          ┌──────▼───────┐
                                                          │ Target DB(s) │
                                                          │ (read-only   │
                                                          │  role)       │
                                                          └──────────────┘
```

Key design rules (each enforced by tests):

1. `ValidatedSQL` is an opaque type only the validator can construct; the executor accepts nothing else.
2. Only `app/tools/execution.py` and `app/tools/introspection.py` may open connections to target databases.
3. Credentials are decrypted only in those modules and never appear in graph state, prompts, traces, logs, or API responses.
4. Every app-DB query on user-owned data requires `user_id`; other users' resources return 404.
5. Graph state carries only IDs and small serializable data (no credentials, no result rows).
6. The app database and the target databases are strictly separate.

## Security model

Defense in depth, three layers, with structural defenses carrying the load:

| Layer | Control | Status |
|---|---|---|
| 1. Validator | Single statement, AST allowlist, function denylist/allowlist, schema + sensitive-column policy, `EXPLAIN` check | Implemented (S4.1); corpus in progress (S4.2) |
| 2. Database role | Read-only role, safety check rejects superuser/writer roles, `BEGIN READ ONLY`, statement/lock timeouts | Implemented (S2.4, S3.3) |
| 3. Infrastructure | SSRF guard with DNS-pinned connections, encrypted credentials, redacted logging, per-user ownership | Implemented (S1-S2); rate limiting in Stage 8 |

Prompt-injection heuristics (planned in S4.4) are deliberately treated as weak; the validator and read-only role are what protect the data. Result rows are wrapped in untrusted-data delimiters before the answer prompt.

## Progress: what is done

### Stage 0: Environment, repo, CI skeleton (complete)

| Step | What was delivered | Commit |
|---|---|---|
| S0.1 | Environment audit (Windows 11, PowerShell, Python, uv, Node, Docker, Ollama, gh) | n/a |
| S0.2 | Git repo, `.gitignore`, `.gitattributes`, `.env.example`, MIT license, secret scanning (gitleaks) | `516e75f` |
| S0.3 | GitHub CLI installed, remote repository created | n/a |
| S0.4 | Project scaffold, `pyproject.toml`, Makefile + `scripts/make.py` (Windows), `AGENTS.md`, `PROGRESS.md` | `131f79b` |
| S0.5 | GitHub Actions CI (lint, type check, unit tests, secret scan), green | `9442cc5` |
| S0.6 | Docker Compose app database (pgvector), smoke test | `f5af33f` |

### Stage 1: Backend foundation, auth, seed databases (complete)

| Step | What was delivered | Commit |
|---|---|---|
| S1.1 | FastAPI app factory, settings, `/health`, structured JSON logging with secret redaction | `2e18632` |
| S1.2 | Async SQLAlchemy layer, Alembic migrations | n/a |
| S1.3 | Register/login/logout with argon2 and httpOnly sessions | n/a |
| S1.4 | Ownership pattern, two-user authz test harness, route-auth guard | n/a |
| S1.5 | E-commerce and pinned Pagila (`pagila-v3.1.0`) demo DBs, read-only/writer roles, integration coverage | `3c0ee57` |

### Stage 2: Connections, security primitives, introspection (complete)

| Step | What was delivered | Commit |
|---|---|---|
| S2.1 | Fernet credential cipher with versioned key prefix, startup key validation | `56c6eab` |
| S2.2 | PostgreSQL dialect contract (introspection, read-only session settings, `EXPLAIN`, safety checks) | `fbd541e` |
| S2.3 | SSRF guard: validates all DNS answers, pins connections to validated IPs via libpq `hostaddr` | `6f74dba` |
| S2.4 | Structured role safety report; rejects writer and superuser roles | `8ed225d` |
| S2.5 | Authenticated connection CRUD (SSRF, encryption, safety report, ownership tests) | `5eafe83` |
| S2.6 | Metadata sync with schema filtering, PKs/FKs, indexes, row estimates, sensitive-column defaults | `987b19c` |
| S2.7 | Schema metadata editing and glossary CRUD, edits survive re-sync | `47509df` |

### Stage 3: LLM layer, tracing, execution, minimal graph (complete)

| Step | What was delivered | Commit |
|---|---|---|
| S3.1 | Gemini/Ollama structured-output client, response cache, retries, usage/cost tracking, `FakeLLM`, opt-in real-LLM smoke test | `db00f91` |
| S3.2 | Persisted run lifecycle: node steps, SQL attempts, usage aggregation, errors, cancellation | pending hash |
| S3.3 | Read-only executor: pinned connections, truncation, SQLSTATE error classification, real-Postgres tests | pending hash |
| S3.4 | SQLGlot single-statement `SELECT`/`WITH` validator returning opaque `ValidatedSQL` | pending hash |
| S3.5 | Versioned prompts (`generate_v1`, `answer_v1`), result summary builder, injection-isolation tests | pending hash |
| S3.6 | Minimal LangGraph pipeline (generate → validate → execute → answer), Conversations API with tracing | pending hash |

### Stage 4: Safety, repair, SSE (in progress)

| Step | Status | Notes |
|---|---|---|
| S4.1 | Done | Full async validator: structural, function, schema, and sensitive-column checks plus read-only `EXPLAIN` validation |
| **S4.2** | **In progress** | 38-case validator corpus, representative DB-boundary proof, and generated security report are done. **Remaining:** fuzz-lite property tests and the complete database-boundary matrix |

> Some commits are marked "pending" in `PROGRESS.md` because hashes were not yet recorded; they will be filled in at the Stage 4 checkpoint.

## Roadmap

**Legend:** ✅ done · 🚧 in progress · ⬜ to do

### Stage 4: Safety, repair, SSE (`stage/4-safety-repair-sse`)

- ✅ S4.1 Full SQL validator
- 🚧 S4.2 Security corpus and DB-boundary tests (fuzz-lite + full matrix remaining)
- ⬜ S4.3 No-unvalidated-execution enforcement (import-boundary test, static `ValidatedSQL` check, runtime `TypeError` on plain `str`, malicious-generation agent test)
- ⬜ S4.4 Deterministic guardrail node (length, control characters, weak injection heuristics)
- ⬜ S4.5 Repair loop with one shared budget (`MAX_REPAIR_ATTEMPTS`, default 3) across validation, execution, and verification failures
- ⬜ S4.6 SSE streaming endpoint that persists the run even if the client disconnects

### Stage 5: Evaluation harness and baseline

- ⬜ S5.1 Dataset format and validator
- ⬜ S5.2 Hand-written dataset (~55-60 questions, dev/test split, frozen as `eval-dataset-v1`)
- ⬜ S5.3 Result-set comparison (results, never SQL strings)
- ⬜ S5.4 Metrics and runner CLI
- ⬜ S5.5 Pre-tuning baseline on dev, plus a single frozen snapshot on the held-out test split

### Stage 6: Retrieval, routing, verification, charts, ablations

- ⬜ S6.1 Embeddings (BGE-M3 via Ollama, pgvector)
- ⬜ S6.2 Metadata enrichment (LLM-generated descriptions with token caps)
- ⬜ S6.3 Schema retrieval with one-hop FK expansion
- ⬜ S6.4 Contextualize and route (`DATABASE_QUERY`, `SCHEMA_QUESTION`, `CLARIFICATION_REQUIRED`, `UNSUPPORTED_REQUEST`)
- ⬜ S6.5 Deterministic result verification
- ⬜ S6.6 Chart selection
- ⬜ S6.7 Optional planner (feature flag)
- ⬜ S6.8 Ablations: planner, retrieval vs full schema, repair budget 0/1/3, generated descriptions

### Stage 7: Frontend (Next.js + TypeScript + Tailwind + Recharts)

- ⬜ S7.1 Scaffold and typed API client
- ⬜ S7.2 Connections UI
- ⬜ S7.3 Chat with streaming
- ⬜ S7.4 Trace view and history
- ⬜ S7.5 Schema and glossary editor
- ⬜ S7.6 Playwright E2E with deterministic fake LLM

### Stage 8: Hardening and deployment

- ⬜ S8.1 Postgres-backed per-user rate limiting
- ⬜ S8.2 Auto-generated authorization matrix
- ⬜ S8.3 Prompt-injection tests with a worst-case, injection-obeying fake LLM
- ⬜ S8.4 nginx with 2 API replicas, unbuffered SSE
- ⬜ S8.5 Load test (Locust/k6), measured numbers only
- ⬜ S8.6 Complete CI (integration, security, authz, frontend, e2e, audits)

### Stage 9: Docs and release

- ⬜ S9.1 Final README (screenshots, quickstart, config table)
- ⬜ S9.2 `docs/design.md`
- ⬜ S9.3 `docs/security.md`
- ⬜ S9.4 Definition-of-Done audit script
- ⬜ S9.5 Final evaluation on held-out test split
- ⬜ S9.6 Clean-clone verification, history secret scan, `v1.0.0` release
- ⬜ S9.7 Resume bullets, every number cited to a committed report

### Optional stretch (only after Stages 0-9)

MySQL dialect, LLM-based result check, error-driven re-retrieval, column-masking UI, eval dashboard.

## Repository layout

```
.
├── AGENTS.md  PROGRESS.md  IMPLEMENTATION_PLAN.md  README.md  LICENSE  Makefile
├── .env.example  .gitignore  .gitattributes  .pre-commit-config.yaml
├── docker-compose.yml  docker-compose.test.yml  nginx/            (nginx in Stage 8)
├── .github/workflows/ci.yml
├── backend/
│   ├── pyproject.toml  alembic.ini  Dockerfile
│   ├── app/{api,agent,tools,database,guardrails,retrieval,persistence,llm}/
│   └── tests/{unit,agent,integration,security,authz}/
├── evaluation/          # datasets, configs, runner, metrics, reports (Stage 5)
├── frontend/            # Next.js app (Stage 7)
├── seeds/{ecommerce,pagila,roles}/
├── loadtest/            # Stage 8
├── scripts/             # env check, key generation, make.py for Windows
└── docs/                # SPEC.md, design.md, decisions/, eval/, security.md, ...
```

Some directories (`retrieval/`, `evaluation/`, `frontend/`, `loadtest/`, `nginx/`) exist only as scaffolding until their stage begins.

## Getting started

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker Desktop, Git. Ollama and Node.js are only needed from Stages 6 and 7.

Development so far has been on native Windows with PowerShell. `make` is not installed there, so use the equivalent `scripts/make.py`. On Linux/macOS/WSL2, plain `make` works.

```bash
git clone https://github.com/mannanj21/agentic-text2sql.git
cd agentic-text2sql

cp .env.example .env            # PowerShell: Copy-Item .env.example .env
python scripts/gen_key.py       # generate ENCRYPTION_KEY, paste it into .env

make setup                      # PowerShell: python scripts/make.py setup
make up                         # start app DB and demo databases
make migrate                    # apply Alembic migrations
```

To run real LLM calls, set `LLM_PROVIDER=gemini` and `LLM_API_KEY=...` in your local, git-ignored `.env`. To run without a key, use `LLM_PROVIDER=fake`. Never commit `.env`.

> The UI, one-command full-stack startup, and a demo walkthrough arrive in Stages 7-9. Exact commands above should be re-verified during S9.6 (clean-clone verification).

## Configuration

Key environment variables (all documented with placeholders in `.env.example`):

| Variable | Purpose |
|---|---|
| `APP_ENV`, `DATABASE_URL` | Runtime mode and app database |
| `ENCRYPTION_KEY`, `SESSION_SECRET` | Credential encryption and sessions |
| `ALLOW_PRIVATE_HOSTS` | Allow private target hosts (needed for the Docker demo; logs a warning) |
| `LLM_PROVIDER` (`gemini`/`ollama`/`fake`), `LLM_API_KEY`, `FAST_MODEL`, `STRONG_MODEL`, `OLLAMA_BASE_URL` | LLM configuration |
| `LLM_CACHE_MODE` (`off`/`record`/`replay`) | Response cache, used to conserve free-tier quota |
| `MAX_REPAIR_ATTEMPTS`, `MAX_RESULT_ROWS`, `STATEMENT_TIMEOUT_MS`, `LOCK_TIMEOUT_MS`, `RESULT_PREVIEW_ROWS` | Pipeline and execution limits |
| `FUNCTION_ALLOWLIST_MODE` | Strict function allowlist in the validator |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_TABLES` | Retrieval (Stage 6) |
| `PLANNER_ENABLED`, `HISTORY_TURNS`, `ENRICHMENT_TOKEN_CAP` | Agent features (Stage 6) |
| `RATE_LIMIT_PER_MIN` | Rate limiting (Stage 8) |
| `EVAL_AS_OF_DATE` | Fixed "today" for reproducible evaluation |

## Testing

Test gates:

| Gate | Command | Runs |
|---|---|---|
| Quick | `make check` | ruff lint/format, type check, unit tests (no Docker) |
| Full | `make test-all` | Quick + agent tests (fake LLM) + integration tests (real Postgres via Compose) |
| Stack | `make smoke` | Compose up from the current tree, hit `/health`, run a scripted demo question with `LLM_PROVIDER=fake` |
| Frontend (Stage 7+) | `make fe-check`, `make e2e` | eslint, tsc, vitest, build, Playwright |

Test suites live under `backend/tests/`: `unit`, `agent`, `integration`, `security`, `authz`. Tests that need a real LLM are marked `@pytest.mark.llm` and are excluded by default; everything else uses `FakeLLM`. Failure scenarios (bad input, wrong owner, timeouts, exhausted budgets) are required tests, not extras.

## Engineering workflow

- One branch per stage (`stage/<N>-<slug>`); `main` stays green. Never commit directly to `main`.
- Conventional Commits with the step ID, e.g. `feat(validator): ... [S4.1]`. Commit and push after every completed step.
- Each stage exit: full test gate, green CI, pull request, merge commit, and a `stage-N-complete` tag.
- Secrets are blocked by a gitleaks pre-commit hook and a CI job.
- Progress is tracked in [`PROGRESS.md`](PROGRESS.md); the detailed plan is in [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

## Metrics

No accuracy, latency, cost, or load-test numbers have been measured yet, so none are published here. Numbers will be added only after the evaluation harness (Stage 5), ablations (Stage 6), and load test (Stage 8) produce committed reports. The held-out test split will be run only twice: once for the pre-tuning baseline (S5.5) and once for the final result (S9.5).

## Known limitations

- PostgreSQL only (behind a `Dialect` interface; MySQL is a stretch goal).
- No frontend yet; the platform is currently API-only.
- Streaming (SSE), the repair loop, and the guardrail node are not implemented yet, so query failures currently return a controlled error rather than retrying.
- Prompt-injection heuristics will be weak by design; protection comes from the validator, the read-only role, and the absence of any write tool.
- `docs/SPEC.md` is currently empty in the repository; requirements are taken from `IMPLEMENTATION_PLAN.md` until it is populated.
- Full schema is sent to the LLM until retrieval lands in Stage 6, which limits scalability to large schemas.

## License

MIT. See [LICENSE](LICENSE). Pagila demo data is vendored from the `pagila-v3.1.0` release; see `seeds/pagila/README.md` for source and license.
