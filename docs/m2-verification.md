# M2 — Distributed Propagation

Verified on 2026-10-02 (Asia/Kolkata). Gate B: PASS. Gate A regression: PASS.
Stopped after M2; M3 was not started.

## Implemented behavior

Pure ASGI middleware creates SERVER spans around demo requests, parses version-00
traceparent, excludes health endpoints, records route templates/status and restores
context. Each demo process owns one lifespan-managed HTTPX AsyncClient; the Order
process reuses its client for both downstream calls. Shutdown closes the clients.

The outbound wrapper makes a CLIENT span current, overwrites caller traceparent with
that CLIENT's context, records status/errors, finishes once and restores the caller.
The normal flow creates eight spans across Order, Payment and Notification. Notification
is called only after successful Payment. Local work creates INTERNAL children.

Factories accept an optional finished-span callback for tests. Runtime defaults discard
completed spans. Tests retain bounded data only in memory, never in telemetry files or
extra API endpoints. No exporter, ingestion, query or database-write feature was added.

## Commands actually run

- Local `ruff format backend scripts`: initially formatted three files, then one after
  later test additions. `ruff check backend scripts` initially passed; after adding a
  server-error test an import-order issue was found and fixed with `ruff check --fix
  backend scripts`. Final lint and `ruff format --check backend scripts` PASS (31 files).
- Local `python -m pytest -c backend/pyproject.toml backend/tests/integration/test_propagation.py
  backend/tests/unit/test_http_instrumentation.py -vv`: an early 16-case run returned
  partial output and was not used as final gate evidence. A subsequent complete run
  passed all 19 cases present then. Two additional flow cases are covered in the final
  container suite below.
- `docker compose config --quiet`: PASS.
- `docker compose up --build -d --wait`: PASS; all six containers healthy.
- `docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest'`:
  **80 passed, no skips** (13.44 seconds):
  - 53 tracing-core cases (Gate A regression);
  - 15 real HTTP propagation/flow cases (Gate B);
  - 6 HTTP instrumentation/error cases;
  - 5 health tests and 1 real PostgreSQL schema test (M0 regressions).
- `docker compose exec -T trace-backend ruff check .`: PASS.
- `docker compose exec -T trace-backend ruff format --check .`: PASS; 30 files.
- `Get-Content -Raw scripts/check_foundation.py | docker compose exec -T trace-backend python -`:
  all four deployed HTTP health endpoints PASS.
- `Invoke-RestMethod -Uri 'http://localhost:8001/orders' -Method Post -ContentType
  'application/json' -Body '{"item":"demo-item","scenario":"normal"}'`: actual Compose
  business request succeeded with status `completed` and a valid trace ID.
- `docker compose ps`: all six deployed containers healthy.

## Gate B machine evidence

`test_propagation.py` runs the actual service factories through three Uvicorn servers
with real loopback TCP and HTTPX, including their lifespans. Finished spans are captured
through the injected in-memory hook. Each canonical trace must contain exactly:

```text
Order SERVER
├── validate-order INTERNAL
├── Payment CLIENT
│   └── Payment SERVER
│       └── process-payment INTERNAL
└── Notification CLIENT
    └── Notification SERVER
        └── send-notification INTERNAL
```

The helper machine-asserts all eight operations, kinds, shared trace ID, unique span IDs,
status/timing and every parent edge. Both cross-service SERVER-to-CLIENT parent
equalities are explicit assertions. It indexes spans by operation, independent of
completion arrival order; this is test verification, not a production reconstruction API.

The concurrent test sends 25 real overlapping HTTP requests with mixed valid, malformed
and missing contexts. It verifies 25 distinct trace IDs and 200 unique span IDs,
every parent edge, caller-supplied upstream parents, per-order attribute consistency,
and actual time overlap. Gate A additionally barriers 25 tasks to directly assert
current-span isolation and restoration during nested awaits.

Other tests prove sequential independence, lifecycle client reuse/closure, valid context
continuation, malformed/all-zero/duplicate header handling, caller-header overwrite,
health exclusion, route-template naming, no body/auth/cookie capture, ignored unused
normal delay, and absent Notification after a controlled downstream Payment failure.
The controlled failing endpoint is a test double, not a production fault scenario.
Unit tests also cover downstream 5xx, timeout and connection errors, server 500/exception
completion, sanitized error data and ContextVar cleanup.

## What to understand

- CLIENT measures the caller's HTTP operation; SERVER measures the downstream handler.
- The injected parent ID is the CLIENT's span ID, so the downstream SERVER is its child.
- INTERNAL spans inherit the active local span automatically.
- The wrapper temporarily activates CLIENT context, then restores the Order SERVER.
- AsyncClient reuse shares connection pools; it never stores a request's tracing context.
- A returned trace ID is useful even before collector delivery exists, but is not queryable yet.

## Limits and blockers

No blockers. Normal flow is implemented; slow/error scenarios remain M5 and return 501
until then. Delivery, ingestion, persistence and queries remain M3/M4; the frontend is
still the M0 shell. Existing Starlette TestClient deprecation warning remains (one warning,
no failed tests). No dependencies or infrastructure were added during M1/M2.

Git author/committer privacy, staged-content scans, commit hashes, push verification and
clean working-tree status are reported at the milestone boundary.
