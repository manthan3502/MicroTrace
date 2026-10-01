# MicroTrace

A compact distributed tracing platform built from first principles. This checkout contains
the **M2 distributed propagation** milestone: custom tracing primitives and the normal
Order → Payment → Notification HTTP flow, PostgreSQL schema/migrations, and a minimal
React shell. Collector delivery, persisted telemetry and the dashboard are later milestones.

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

The response contains the trace ID. In M2, completed spans are discarded by default;
the tests inject a bounded in-memory completion hook. No collector endpoint or span
export queue exists yet. Slow/error scenario names are validated but return 501 until M5.

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

The schema test reads the migrated PostgreSQL schema; without
`MICROTRACE_TEST_DATABASE_URL` it explicitly skips. A skip does not verify the database.

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
