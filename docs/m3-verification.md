# M3 verification

Bounded exporter: 256 capacity, one worker, 1-second timeout, zero retries,
put_nowait/drop-newest, warnings at most once per five seconds, two-second shutdown
budget. The worker starts with an empty Context and uses explicit immutable DTOs.
Collector: POST /api/v1/spans, strict JSON validation, UTC/timing/limits, 64-KiB
streaming body bound, 201 stored/200 duplicate, atomic ON CONFLICT DO NOTHING.
Synchronous parameterized SQLAlchemy writes run in a thread pool. Database errors
return sanitized 503. No new dependencies, migrations, traces table or infrastructure.

Commands actually run and results:
- ruff format backend scripts and ruff check --fix backend scripts: formatting/import
  fixes; initial Depends-default lint finding corrected to Annotated dependency.
  A misplaced Annotated import caused one Docker startup failure; fixed before acceptance.
- Native focused test_exporter.py + test_ingestion.py: 13 passed/26 skipped (2.08s), then
  13 passed/27 skipped after concurrent-duplicate coverage (2.22s). Database skips were
  expected without native test DB configuration and were not used as DB evidence.
- docker compose config --quiet: PASS.
- docker compose up --build -d --wait: final PASS, all six healthy.
- docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest -p no:cacheprovider':
  124 passed, zero skips, 24.33s. Includes all M0/M1/M2/hardening regressions.
- docker compose exec -T trace-backend ruff check .: PASS.
- docker compose exec -T trace-backend ruff format --check .: PASS, 36 files.
- Get-Content -Raw scripts/check_foundation.py | docker compose exec -T trace-backend python -:
  all four health endpoints PASS.
- Additional stdin Python Compose smoke: real normal order -> default exporter ->
  collector -> PostgreSQL; all eight persisted spans and both CLIENT/SERVER parents PASS.
- git diff --check and milestone privacy/identity checks: PASS before commit.

Evidence: 12 exporter cases (including exact payload/context, drops, no retries,
timeout and bounded shutdown), 28 ingestion/flow cases (21 invalid payloads,
duplicates including concurrent duplicates, orphan/child-first, database failure,
real service delivery and collector-down normal traffic). Tests create disposable
PostgreSQL schemas from the existing migrated spans table and drop them afterward;
existing public telemetry is preserved. The schema regression still asserts only
spans plus Alembic metadata, and no parent FK.

Gate A/B regression PASS. Gate C is evaluated after M4, not claimed here.
One existing Starlette TestClient warning remains. Delivery is best effort; queues
are not durable and telemetry can be lost. No queries/UI/fault scenarios yet.

Understand: delivery happens off the business path, bounded buffering permits explicit
loss, duplicates retain the original row, and children need no existing parent row.
Commit/push identity and final working-tree results are in the completion report.
