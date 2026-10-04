# M4 — Query and reconstruction verification

Implemented GET /api/v1/traces, /api/v1/traces/{trace_id}, /api/v1/services.
SQL applies whole-trace service/status/min-duration AND filters before limit/offset.
Candidate selection and summary reconstruction share a PostgreSQL repeatable-read
snapshot so late spans cannot produce inconsistent filtering within one list response.
Summaries are derived; no traces table or schema migration was added.

Reconstruction builds a span-ID map, sorts siblings by start time then span ID, walks
iteratively in pre-order, preserves orphan subtree depth, and visits each span once.
Missing/multiple roots, missing parents and cycles mark incomplete independently of
OK/ERROR. One root supplies monotonic duration; otherwise use the available wall window.
Offsets are nonnegative and UTC timestamps remain unchanged. Deep chains do not depend
on Python recursion limits. Query database errors return sanitized 503 responses.

Commands actually run:
- ruff format backend scripts; ruff check --fix backend scripts: initial lambda-assignment
  lint issue corrected to a def, and import formatting fixed. Final checks PASS.
- Native test_reconstruction.py: 24 passed in 0.25s.
- Native test_reconstruction.py + test_queries.py: 24 passed, 24 DB-dependent skips
  in 1.34s. Skips were not used as DB/gate evidence.
- docker compose config --quiet: PASS.
- docker compose up --build -d --wait: PASS, all six services healthy.
- docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest -p no:cacheprovider':
  172 passed, no skips, 37.15s. Includes every M0/M1/M2/hardening/M3 regression.
- docker compose exec -T trace-backend ruff check .: PASS.
- docker compose exec -T trace-backend ruff format --check .: PASS (41 files).
- Local ruff check --fix scripts/check_gate_c.py fixed one import-order issue;
  ruff format --check backend scripts PASS (43 files).
- Get-Content -Raw scripts/check_gate_c.py | docker compose exec -T trace-backend python -:
  Gate C PASS against deployed services and PostgreSQL.
- Get-Content -Raw scripts/check_foundation.py | docker compose exec -T trace-backend python -:
  all four health endpoints PASS.
- docker compose ps: all six healthy.

Gate C evidence:
- real Order -> Payment -> Notification -> default bounded exporter -> HTTP collector ->
  PostgreSQL -> HTTP query -> exact eight-span hierarchy; both downstream SERVER parent
  IDs equal their Order CLIENT span IDs.
- duplicate posts return 200 duplicate and preserve original rows; concurrent duplicates
  create exactly one row.
- child-before-parent accepted and initially orphaned; adding parent clears incompleteness.
- permanent missing parents/subtrees are visible and safe.
- random span arrival yields identical detail (unit permutations, DB/API traces and actual
  Compose HTTP replay).
- correct root/fallback duration, status aggregation, counts/services, newest-first,
  individual/combined filters before paging, bounds, not-found and safe skew offsets.
- self/multi-node cycles and a disconnected cycle cannot loop; 2,000-span chains work.
- schema inspection: spans plus Alembic metadata only; no parent FK or traces table.
- inherited M3 exporter tests prove default capacity/worker/timeouts, immediate queue-full
  drops, no retries, context-free payload delivery, controlled warnings and bounded drain.
- real services remain successful with collector unavailable; all eight spans are dropped.

Tests use disposable PostgreSQL schemas and preserve existing public telemetry.
The Compose Gate C command removes only its own synthetic contract traces and retains
its real order trace. Gate A/B regressions PASS; Gate C PASS.

Understand:
- arrival order cannot establish a tree; parent IDs do.
- incomplete describes missing/corrupt telemetry, not business status.
- root monotonic duration and wall-clock positioning are separate concepts.
- summaries are derived from current spans; SQL filters evaluate whole traces before paging.

Limits: best-effort, nondurable export; portfolio-scale offset pagination and per-trace
reconstruction; no auth/retention/sampling. Existing Starlette TestClient warning remains.
React remains the M0 shell. Slow/error scenarios still return 501 until M5.
Stopped after M4; M5 was not started. Git privacy/identity, commit/push and clean-tree
results are reported at the completion boundary. No blockers.
