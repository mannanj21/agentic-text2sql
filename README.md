# Agentic Text-to-SQL Analytics Platform

[![CI](https://github.com/mannanj21/agentic-text2sql/actions/workflows/ci.yml/badge.svg)](https://github.com/mannanj21/agentic-text2sql/actions/workflows/ci.yml)

A full-stack analytics application that converts natural-language questions
into validated PostgreSQL queries, executes them through read-only target
connections, and returns an answer, table, chart, and persisted execution
trace.

## Architecture

```text
Next.js UI ── REST/SSE ── nginx ── FastAPI replicas ── LangGraph workflow
                                                    ├─ app Postgres + pgvector
                                                    └─ read-only target Postgres
```

The workflow is guardrail → contextualize/route → schema context → optional
plan → structured SQL generation → validation → read-only execution → result
verification/repair → answer/chart. Runs and step traces are persisted in the
app database; target credentials and result rows are never put in graph state.

## Features

- Session authentication, ownership checks, conversations, history, and traces.
- Encrypted target credentials, DNS/SSRF protection, read-only-role safety
  checks, schema sync, glossary, sensitive-column controls, and re-sync.
- SQLGlot structural validation, function/table policy, read-only execution,
  timeout, row cap, bounded repair, and deterministic chart selection.
- SSE progress UI, two nginx-backed API replicas, rate limiting, security
  corpus, authorization matrix, Playwright E2E, Docker demos, and CI.
- Reproducible development ablations in [docs/ablations.md](docs/ablations.md).

## Quick start

1. Copy `.env.example` to `backend/.env` and generate an encryption key with
   `python scripts/gen_key.py`. Set `LLM_PROVIDER=fake` for an offline demo, or
   configure a supported hosted provider and model.
2. Start the stack:

   ```powershell
   docker compose up -d --build --wait
   ```

3. Open `http://localhost:8000`, register, choose a seeded demo connection,
   and ask a question such as “How many customers are registered?”.

For a local Docker demo, set `ALLOW_PRIVATE_HOSTS=true`; leave it false in any
non-local deployment. Use `docker compose down` when finished.

## Configuration

| Setting | Purpose |
|---|---|
| `LLM_PROVIDER` | `fake`, `gemini`, `groq`, or `ollama` |
| `LLM_API_KEY` | Hosted-provider secret; never commit it |
| `FAST_MODEL`, `STRONG_MODEL` | Provider model IDs |
| `ENCRYPTION_KEY`, `SESSION_SECRET` | Required server secrets |
| `ALLOW_PRIVATE_HOSTS` | Local-demo-only SSRF override |
| `RETRIEVAL_MIN_TABLES` | Full-schema threshold; v1 default is 999 |
| `MAX_REPAIR_ATTEMPTS` | Bounded repair budget; v1 default is 1 |

See [.env.example](.env.example) for the complete list.

## Testing

On Windows, use the cross-platform script:

```powershell
python scripts/make.py check      # lint, format, types, unit tests
python scripts/make.py test-all   # quick + agent + integration + security
python scripts/make.py smoke      # Docker stack smoke test
python scripts/make.py fe-check   # frontend lint/type/unit/build
```

## Security model

Injection heuristics are intentionally weak and are not the security boundary.
Safety comes from three layers: deterministic SQL validation; a target
read-only role plus read-only transaction, timeout, and row cap; and platform
controls including encrypted credentials, SSRF checks, ownership enforcement,
and rate limiting. See [docs/security.md](docs/security.md).

## Known limitations

- PostgreSQL only; the Dialect interface is designed for future expansion.
- Evaluation uses a small hand-written corpus; final held-out metrics must be
  read with that limitation in mind.
- Full-schema context currently outperformed vector retrieval on the v1 corpus;
  revisit this choice for materially larger schemas.
- No fine-grained RBAC, cloud warehouses, MySQL, result-checking LLM, or
  dashboard UI in v1.

## Evidence

The development ablations keep the planner disabled, use full schema context
for v1, and retain one repair attempt. See [docs/ablations.md](docs/ablations.md),
[docs/loadtest.md](docs/loadtest.md), and [docs/security.md](docs/security.md).

## License

MIT — see [LICENSE](LICENSE).
