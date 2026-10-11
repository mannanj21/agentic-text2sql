# Resume Bullets

Use only after confirming the linked evidence still matches the release.

- Built a containerized, two-replica FastAPI/Next.js agentic analytics platform
  with encrypted database connections, SQL AST validation, SSE traces, and
  deterministic visualization.
- Implemented a 60-case PostgreSQL evaluation corpus with separated
  development and held-out splits; the held-out metric is intentionally not
  claimed because both documented provider runs were rate-limited
  ([final-test.md](eval/final-test.md)).
- Ran six rate-safe development ablations across 42 cases; full-schema context
  reached 46.9% execution accuracy in the committed development report
  ([ablations.md](ablations.md)).
- Verified security controls with a 38-case SQL validator corpus and database
  boundary tests ([security.md](security.md)).
- Load-tested two API replicas with a quota-bounded real-provider smoke:
  25 requests, zero failures, and a 3,799 ms real SSE query sample
  ([loadtest.md](loadtest.md)).
