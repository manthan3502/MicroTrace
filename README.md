# MicroTrace

A compact distributed tracing platform built from first principles. This checkout contains
the **M4 query and reconstruction** milestone: custom tracing primitives and the normal
Order → Payment → Notification HTTP flow, PostgreSQL schema/migrations, and a minimal
React shell. Bounded export, collector ingestion, PostgreSQL persistence, trace queries
and safe reconstruction work. The dashboard remains a later milestone.

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
Slow/error scenario names are validated but return 501 until M5.

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
docker compose exec -T trace-backend pytest
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
