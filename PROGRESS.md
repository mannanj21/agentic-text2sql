# PROGRESS

## Current
- Stage: 4 (Safety, Repair, SSE) | Step: S4.2 | Status: IN PROGRESS
- Branch: stage/4-safety-repair-sse
- Last commit: pending S4.2 checkpoint
- Active model: Codex (GPT-5)
- Next action: Finish S4.2 with fuzz-lite coverage and the complete database-boundary matrix.

## Step Checklist
| Step | Status | Commit | Notes |
|---|---|---|---|
| S0.1 | DONE | — | Env audit done; gh, Docker installed later |
| S0.2 | DONE | 516e75f | git init, .gitignore, .gitattributes, .env.example, LICENSE, README created |
| S0.3 | DONE | — | gh CLI installed, GitHub remote created |
| S0.4 | DONE | 131f79b | Scaffold, pyproject.toml, Makefile, AGENTS.md, PROGRESS.md created |
| S0.5 | DONE | 9442cc5 | CI configured and passed |
| S0.6 | DONE | f5af33f | Docker Compose for app-db created, smoke test passed |
| S1.1 | DONE | 2e18632 | FastAPI app, config, logging |
| S1.2 | DONE | — | App DB layer and Alembic |
| S1.3 | DONE | — | Auth: register/login/logout |
| S1.4 | DONE | — | Ownership pattern and authz harness |
| S1.5 | DONE | 3c0ee57 | Ecommerce and pinned Pagila demo databases, roles, integration coverage |
| S2.1 | DONE | 56c6eab | Fernet credential cipher with versioned key prefix, startup validation, and DB ciphertext coverage |
| S2.2 | DONE | fbd541e | PostgreSQL dialect contract for introspection, read-only session settings, EXPLAIN, and safety checks |
| S2.3 | DONE | 6f74dba | Validates all DNS answers and pins target connections to validated IPs via libpq hostaddr |
| S2.4 | DONE | 8ed225d | Structured role safety report; real PostgreSQL checks reject writer and superuser roles |
| S2.5 | DONE | 5eafe83 | Authenticated connection CRUD with SSRF, pinned target connect, encryption, safety reports, and ownership coverage |
| S2.6 | DONE | 987b19c | Target metadata sync with schema filtering, indexes, PKs/FKs, row estimates, conservative sensitive defaults, and failure status |
| S2.7 | DONE | 47509df | Authenticated schema metadata editing and glossary CRUD with re-sync persistence coverage |
| S3.1 | DONE | db00f91 | Gemini/Ollama structured client, safe cache, retries, usage/cost tracking, FakeLLM, and opt-in real smoke test; Quick + Full passed |
| S3.2 | DONE | pending | Persisted run lifecycle, node steps, SQL attempts, usage aggregation, errors, and cancellation; Full passed |
| S3.3 | DONE | pending | Read-only target executor with pinned connections, truncation, SQLSTATE error classification, and real-Postgres coverage; Full passed |
| S3.4 | DONE | pending | SQLGlot PostgreSQL single-statement SELECT/WITH validator returning opaque ValidatedSQL; Full passed |
| S3.5 | DONE | pending | Versioned prompts (generate_v1, answer_v1), result summary builder, generate/answer nodes, injection-isolation tests; Quick passed |
| S3.6 | DONE | pending | Minimal LangGraph pipeline (generate→validate→execute→answer), Conversations API with RunRecorder tracing, AgentState as TypedDict; Full and Stack passed |
| S4.1 | DONE | pending | Full async SQL validator: structural/function/schema/sensitive-column checks and read-only EXPLAIN validation; Full passed |
| S4.2 | IN PROGRESS | pending | 38-case validator corpus, representative DB-boundary proof, and generated security report; fuzz-lite/full DB matrix remain |
| S4.3 | DONE | 99e3f6e | No-unvalidated-execution enforcement (import boundary, static check, agent safety) |
| S4.4 | DONE | 0f1632b | Deterministic pre-LLM guardrail node |
| S4.5 | DONE | cbf2fa0 | Shared-budget LLM repair loop with duplicate avoidance and recursion limit |
| S4.6 | DONE | pending | SSE streaming endpoint: node_started/finished/sql_generated/attempt_failed/final events; background task decoupled from response; non-streaming JSON fallback; disconnect persistence; RunStep tracing |
| S5.1 | DONE | pending | Dataset format, Pydantic loader, deterministic split assignment, uniqueness/followup checks, CLI validator |
| S5.2 | DONE | pending | Write the dataset (60 cases across ecommerce/pagila, stratified deterministic splits, docs generated) |
| S5.3 | DONE | pending | Result-set comparison logic: multiset/ordered comparison, positional mapping, float tolerance, superset columns |
| S5.4 | DONE | pending | Metrics module (execution/routing accuracy, schema P/R, self-correction, latency p50/p95, tokens/cost); runner logic; CLI; 38 eval tests |
| S5.5 | DONE | pending | Baseline reports created (docs/eval/baseline-dev.md + baseline-test.md); live metrics pending API key + ecommerce DB |
| S6.1 | DONE | pending | Embeddings |
| S6.2 | DONE | pending | Metadata enrichment |
| S6.3 | IN PROGRESS | pending | Schema retrieval |
| S6.4 | TODO | — | Contextualize + route |
| S6.5 | TODO | — | Deterministic verification |
| S6.6 | TODO | — | Chart selection |
| S6.7 | TODO | — | Planner |
| S6.8 | TODO | — | Ablations |
| S7.1 | TODO | — | Frontend scaffold |
| S7.2 | TODO | — | Connections UI |
| S7.3 | TODO | — | Chat with streaming |
| S7.4 | TODO | — | Trace view and history |
| S7.5 | TODO | — | Schema/glossary editor |
| S7.6 | TODO | — | E2E tests |
| S8.1 | TODO | — | Rate limiting |
| S8.2 | TODO | — | Authorization matrix |
| S8.3 | TODO | — | Prompt-injection tests |
| S8.4 | TODO | — | nginx and 2 replicas |
| S8.5 | TODO | — | Load test |
| S8.6 | TODO | — | Complete CI |
| S9.1 | TODO | — | README |
| S9.2 | TODO | — | design.md |
| S9.3 | TODO | — | security.md |
| S9.4 | TODO | — | DoD audit |
| S9.5 | TODO | — | Final eval |
| S9.6 | TODO | — | Clean-clone verification |
| S9.7 | TODO | — | Resume bullets |

## Decisions Log
- 2026-09-29 The LLM wrapper calls documented Gemini and Ollama HTTP APIs through the existing `httpx` dependency, avoiding an additional provider SDK surface; Gemini 2.5 Flash/Pro defaults remain because Google documents free-tier access and structured JSON support.
- 2026-09-29 Pagila is vendored from the pinned `pagila-v3.1.0` release, rather than the moving default branch, because current upstream requires PostgreSQL 18+ while the local demo uses PostgreSQL 16.
- 2026-09-28 Native Windows with PowerShell instead of WSL2 because human prefers direct Windows development. PowerShell make.py equivalent provided. All scripts use cross-platform Python.
- 2026-09-28 `docs/SPEC.md` exists but is empty; proceeding with implementation plan detail which embeds enough spec info. Will populate SPEC.md if human provides content.
- 2026-09-28 Pre-commit hooks configured with gitleaks, ruff, and standard hygiene hooks. Installation deferred until first commit (S0.2).

## Environment
- OS: Windows 11 (NT 10.0.26200.0), PowerShell 5.1
- Git: 2.55.0.windows.4
- Python: 3.14.7
- uv: 0.12.19
- Node.js: 24.19.0
- npm: 11.17.0
- Ollama: 0.34.4
- gh: authenticated as mannanj21
- Docker: installed
- make: MISSING (using scripts/make.py instead)
- psql: MISSING (optional)

## Known Issues / Blockers
- None. Historical entries below are resolved.
- gh CLI not installed — blocks S0.3 (GitHub remote creation). Will guide human to install when we reach that step.
- Docker Desktop not installed — blocks S0.6 (Docker Compose). Will guide human to install when we reach that step.

## Measured Numbers
(none yet)
