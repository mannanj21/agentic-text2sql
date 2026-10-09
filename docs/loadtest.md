# Load Testing

`loadtest/locustfile.py` provides the platform-mode baseline. It intentionally
uses ordinary authenticated reads and no LLM calls, so API/DB pool/nginx
behaviour can be measured without spending provider quota.

Run it against the local two-replica stack after creating a normal test user:

```powershell
$env:LOADTEST_EMAIL = "loadtest@example.com"
$env:LOADTEST_PASSWORD = "a-strong-password"
cd loadtest
..\backend\.venv\Scripts\locust.exe -f locustfile.py --host http://localhost:8000
```

Use the Locust web UI to choose a small user count and duration, then save its
CSV/HTML output. Commit only measured environment details and metrics to this
document; do not invent a throughput or latency number. A short real-LLM run
is deferred until its quota and target credentials are explicitly available.

## Measured platform-mode baseline

On 2026-10-10, the local Docker stack (nginx plus two API replicas and the
local Postgres app database) was exercised with Locust 2.46.7 for 10 seconds:
two users ramped at one user/second, issuing health and authenticated read
requests. The run completed 31 requests with zero failures (3.26 requests/s),
13 ms average latency, 88 ms p95, and 89 ms p99. This is a tiny smoke baseline,
not a capacity claim; it did not issue real LLM-backed queries.

With `docker-compose.loadtest.yml` enabling the deterministic fake provider at
50 ms simulated LLM latency, a one-user 10-second query-lifecycle run completed
17 requests with zero failures. It included two SSE query requests (499 ms
average, 650 ms maximum); aggregate average latency was 75 ms and request rate
was 1.83 requests/s. This remains a smoke baseline, not a capacity claim.

A second deterministic mixed run used five users for 20 seconds. It completed
157 requests with zero failures, including seven SSE query requests; SSE query
p95 was 380 ms. The scenario included login, demo-connection and conversation
creation, read endpoints, and fake-provider query streaming.

## Measured real-provider smoke

On 2026-10-10, a quota-bounded real-Gemini smoke run used the configured
`backend/.env` provider with the base local Docker stack (nginx, two API
replicas, app Postgres, and the ecommerce demo database). Locust 2.46.7 ran one
user for 20 seconds, ramping at one user/second, on Windows 11. Hardware details
were not collected because the host denied the read-only system-information
query; this is therefore a functional latency sample, not a capacity claim.

The run completed 25 requests with zero failures (1.50 requests/s). It included
one full real-LLM SSE query at 3,799 ms (and therefore p95 3,800 ms for that
single request). Aggregate average latency was 166 ms; aggregate p95 was 110 ms
because most requests were inexpensive authenticated reads. Database-pool
saturation was not measured. The primary observed bottleneck was provider and
agent-chain latency, so future scale work should prioritize a queue for long
queries, per-tenant limits, retrieval caching, and pool instrumentation before
raising concurrency.
