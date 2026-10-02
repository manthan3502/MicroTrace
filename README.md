# MicroTrace

A compact distributed tracing platform built from first principles. This checkout contains
the **M7 QA and CI** milestone: custom tracing primitives and the
Order → Payment → Notification HTTP flow, PostgreSQL schema/migrations, and the
React dashboard. Bounded export, collector ingestion, PostgreSQL persistence, trace queries
and safe reconstruction work. The dashboard uses real backend data.

## Local stack

Requirements: Docker with Linux containers and Docker Compose v2.

1. Copy `.env.example` to `.env`, choose a local-only password, and set the same
   URL-encoded password in `DATABASE_URL`. Keep `.env` private.
2. From the repository root:

```sh
docker compose config --quiet
docker compose up --build -d --wait
docker compose exec -T trace-backend alembic upgrade head
docker compose exec -T trace-backend alembic current
docker compose ps
```

Frontend: http://localhost:5173. Trace backend health: http://localhost:8000/health.
Order health: http://localhost:8001/health. Payment and Notification are internal.
PostgreSQL has no host port and stores data in the `postgres-data` named volume.
Migrations run explicitly; app startup never creates tables.

Trigger a normal request in PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:8001/orders -Method Post -ContentType application/json -Body '{"item":"demo-item","scenario":"normal"}'
```

The response contains the trace ID. Each demo process uses one bounded queue (default
256), one exporter worker, a 1-second delivery timeout, no retries and a bounded
2-second shutdown drain. Queue-full/delivery failures drop telemetry with controlled
warnings; business requests do not wait for delivery. The worker reuses the lifespan
HTTPX client and receives immutable completed data without reading request context.

POST /api/v1/spans accepts one validated JSON span (maximum 64 KiB), returns 201 stored
or 200 duplicate, and preserves the original on duplicates. There is still only the
spans table; a parent has no FK. Test hooks replace export only in instrumentation tests.
Scenarios are request-scoped: normal, slow_payment (100–3000 ms inside process-payment),
and deterministic payment_error. Payment error returns 502 from Order, records the
four affected spans as ERROR and skips Notification. No restart/configuration change.

```sh
python scripts/demo.py healthy
python scripts/demo.py slow
python scripts/demo.py error
```

Each command prints the business result, trace ID and dashboard URL. Use --order-url,
--dashboard-url or --slow-ms when needed. The expected error demo exits successfully.
Run `python scripts/check_scenarios.py` with the backend Python environment for real
healthy/slow/error Compose E2E verification.

Dashboard: `/traces` lists traces with URL-backed filters, manual Refresh and offset
pagination. `/traces/:traceId` shows the API-ordered waterfall and Span Details.
Select a span or its parent. SERVER bars are solid, CLIENT hollow and INTERNAL thin;
errors have text, stripes and tint. Incomplete and orphan telemetry remains visible.
Below 1100 px, the details panel stacks under the waterfall. No polling or extra pages.

Queries:

- GET /api/v1/traces: recent summaries; service, status and min_duration_ms filters
  combine with AND before pagination. Default limit 50, maximum 100, offset 0.
- GET /api/v1/traces/{trace_id}: parent-first ordered spans with depth, start offset,
  orphan IDs and an incomplete flag. Unknown traces return 404.
- GET /api/v1/services: sorted participating service names.

Summaries use one root's monotonic duration, or the available wall-clock window when
there is no single root. Any ERROR span makes the summary ERROR. Missing parents,
missing/multiple roots and cycles mark telemetry incomplete independently of status.
Trees come from IDs rather than arrival order; cycles return each available span once.
There is no persisted traces table, retention system, auth, sampling or retry infrastructure.

Gate C against the actual Compose pipeline:

```powershell
Get-Content -Raw scripts/check_gate_c.py | docker compose exec -T trace-backend python -
```

This generates a real order and verifies its eight stored spans, queries and parents.
It also tests duplicate, child-first, orphan, shuffled and cycle telemetry. It removes
only its synthetic contract-test traces and retains the real order trace. Exporter
bounds and collector-down behavior are verified by the backend regression suite.

## Verification

```sh
docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest'
docker compose exec -T trace-backend ruff check .
docker compose exec -T trace-backend ruff format --check .
docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest -m integration'
docker compose exec -T frontend npm test
docker compose exec -T frontend npm run lint
docker compose exec -T frontend npm run build
docker compose exec -T trace-backend python - < scripts/check_foundation.py
```

The final command uses stdin redirection in POSIX shells. In PowerShell use:

```powershell
Get-Content -Raw scripts/check_foundation.py | docker compose exec -T trace-backend python -
```

The schema test reads the migrated PostgreSQL schema. Ingestion/query tests create
isolated disposable schemas copied from the migrated public spans table and remove them
afterward. Existing public telemetry is preserved. Without MICROTRACE_TEST_DATABASE_URL,
DB tests explicitly skip; a skip does not verify the database.
The `integration` marker includes collector ingestion, query/reconstruction, schema,
and real HTTP delivery tests. Supply the test database for the full marked set.

Repeatable full-stack reliability and privacy checks (uses the backend Python environment):

```sh
python scripts/check_scenarios.py
python scripts/check_system.py
python scripts/check_repository.py
```

`check_system.py` generates a real eight-span order, checks request-body/header canaries
against PostgreSQL and logs, stops/restores the collector, and stops/restores PostgreSQL.
It checks business independence, sanitized database errors and exact trace persistence
with the same named volume. It preserves existing data and restores services in `finally`
blocks. It adds telemetry as expected; it never removes the database volume.
Use `--docker` with an absolute executable path when Docker is not on PATH.
The repository scan checks tracked content, historical blobs and author/committer emails;
it does not print matched private values.

[GitHub Actions](https://github.com/manthan3502/MicroTrace/actions/workflows/ci.yml)
has backend, frontend and Compose E2E jobs. Backend CI uses a migrated PostgreSQL 16
service and runs both the unmarked and integration test sets. Compose CI runs health,
Gate C, all three scenarios, collector/database outage, restart and privacy checks.
Workflow permissions are read-only, and all CI database credentials are disposable
public test values. Hosted execution must pass before M7 is declared complete.
See [M7 verification](docs/m7-verification.md) for local acceptance results.

For native development, use Python 3.12, `uv sync --locked --project backend`,
then `uv run --locked --project backend pytest -c backend/pyproject.toml backend/tests`
and `uv run --locked --project backend ruff check backend scripts`.
In `frontend`, use Node 22.12+ and `npm ci`, `npm test`, `npm run lint`, `npm run build`,
or `npm run dev`. The local Vite API proxy targets `localhost:8000` by default.

`backend/uv.lock`, `backend/requirements.lock`, and `frontend/package-lock.json`
record resolved dependencies. The backend Docker image includes the dev tools for M0 verification.

To stop the stack: `docker compose down` (preserves the database volume).

See [foundation notes](docs/foundation.md) for component roles and M0 boundaries.
See [M1 verification](docs/m1-verification.md) and [M2 verification](docs/m2-verification.md)
for gate evidence and learning notes.

See [hardening verification](docs/pre-m3-hardening-verification.md),
[M3 verification](docs/m3-verification.md), and [M4 verification](docs/m4-verification.md)
for exact regression results and Gate C evidence.
