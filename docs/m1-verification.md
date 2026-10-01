# M1 — Tracing Core

Verified on 2026-10-02 (Asia/Kolkata). Gate A: PASS.

Implemented secure nonzero IDs, the W3C version-00 traceparent subset, immutable
SpanContext, bounded completed telemetry, ContextVar set/reset, root/child lifecycle,
monotonic microsecond durations, UTC timestamps, sanitized errors, and an INTERNAL
span context manager. Completion callbacks receive finished data explicitly and run
at most once. No HTTP integration or collector/export queue is implemented in M1.

## Commands and results

- Local `python -m pytest -c backend/pyproject.toml backend/tests/unit/test_tracing_core.py`:
  53 passed, both before and after correcting the import order.
- Local `ruff format backend/microtrace_sdk backend/tests/unit/test_tracing_core.py`:
  formatted two files.
- Initial `ruff check backend scripts`: one import-order failure.
  `ruff check --fix backend/tests/unit/test_tracing_core.py` fixed it.
- Final local `ruff check backend scripts` and `ruff format --check backend scripts`:
  PASS; 23 Python files formatted.
- `docker compose config --quiet`: PASS.
- `docker compose up --build -d --wait`: PASS; all six containers healthy.
- `docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest'`:
  59 passed, no skips. This includes all 53 tracing-core tests and all six M0 tests,
  including the real PostgreSQL schema check.
- `docker compose exec -T trace-backend ruff check .` and
  `docker compose exec -T trace-backend ruff format --check .`: PASS (22 files).
- `Get-Content -Raw scripts/check_foundation.py | docker compose exec -T trace-backend python -`:
  all four HTTP health endpoints PASS.
- `docker compose ps`: all six containers healthy.

## Gate A evidence

The parametrized core suite covers both ID formats with 5,000 unique samples each,
all-zero regeneration, valid header roundtrips/flag preservation, missing/malformed/
unsupported/nonhex/zero headers, all three kinds and invalid kinds, root/child parents,
remote parents, UTC/monotonic timing, finish once, error paths, attribute allow-list/
types/count/size limits, nested restoration, explicit independent roots, callback
failure isolation, and cancellation.

The async isolation test deliberately overlaps 25 requests using a barrier and yields
inside nested spans. Each task asserts its own active child, correct root parent and
trace ID, root restoration, and empty context on exit. All root trace/span IDs differ.

## What to understand

- A trace ID groups a request; each operation gets a separate span ID.
- A parent ID points to the operation that started the child.
- traceparent carries trace identity, caller span identity and flags.
- ContextVar tokens restore the previous span across nesting and isolate async tasks.
- UTC timestamps locate an operation; monotonic time measures its duration.
- Finishing snapshots bounded data once. Raw exception messages are discarded.

## Limits

Only the version-00 context subset is supported. Flags are propagated without sampling.
The allow-list currently contains six controlled attribute keys. There is no HTTP
instrumentation, exporter queue or persistence yet. The existing M0 Starlette
TestClient deprecation warning remains; all tests pass with the approved HTTPX stack.

Git privacy/content checks and the final commit/push results appear in the completion report.
