# M7 — Full QA and CI

## Recovery and scope

Recovery inspected `git status`, `git diff`, `git diff --cached` and
`git log --oneline -10`. HEAD was the approved M6 commit
`aac3eaccd9bca5f6b4ba2519a07a709ef5757dbf`, matching origin/main. Both diffs were
empty because the three partial M7 files were untracked: `.github/workflows/ci.yml`,
`scripts/check_repository.py` and `scripts/check_system.py`. All were preserved and
completed. No reset, stash, clean or checkout-over operation was used. No unrelated
file changes existed. Repository-local and all historical commit emails were the
approved GitHub noreply. Global identity was not changed.

M7 adds only verification scripts, CI and developer verification notes. Product code,
APIs, exporter strategy, persistence schema, scenarios and the two UI screens remain
the approved implementation. M8 deployment is not started.

## Commands actually executed locally

Docker commands used the existing Docker Desktop executable when PATH required it.
This table uses `docker` for readability. Docker Linux containers, Python 3.12 and
Node 24 were used; native backend tools also checked scripts outside the Docker image.

| Command | Observed result |
| --- | --- |
| `docker compose config --quiet` | PASS |
| `docker compose up --build -d --wait --wait-timeout 180` | Five application images built; all six containers healthy |
| `docker compose exec -T trace-backend alembic upgrade head` | PASS, existing migration preserved |
| `docker compose exec -T trace-backend alembic current` | `0001 (head)` |
| `docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest'` | **190 passed, zero skipped**, 44.70 s |
| Same environment, `pytest -m integration` | **71 passed, 119 deselected, zero skipped**, 30.00 s |
| `docker compose exec -T trace-backend ruff check .` | PASS |
| `docker compose exec -T trace-backend ruff format --check .` | PASS, 42 files |
| Native `ruff check backend scripts` | PASS |
| Native `ruff format --check backend scripts` | PASS, 48 files |
| `docker compose exec -T frontend npm test` | **32 passed**, three files, 1.73 s |
| `docker compose exec -T frontend npm run lint` | PASS |
| `docker compose exec -T frontend npm run typecheck` | PASS |
| `docker compose exec -T frontend npm run build` | PASS, 35 modules, 1.28 s; JS 235.78 kB / gzip 73.74 kB |
| `docker compose exec -T trace-backend python - < scripts/check_foundation.py` | Four real backend health endpoints PASS |
| Same stdin invocation for `scripts/check_gate_c.py` | Gate C PASS against real service/export/collector/PostgreSQL/query path |
| `python scripts/check_scenarios.py` | Healthy, slow and error PASS |
| `python scripts/check_system.py --docker <existing-cli>` | Collector outage, collector restart, DB outage, DB restart, persistence and stored/log privacy PASS |
| `docker compose ps` after reliability checks | All six containers healthy |
| `git check-ignore .env .cache/ci_probe.py` | Both private/local files ignored |
| `python scripts/check_repository.py` | Tracked content, historical blobs, historical filenames and commit identity scan; run before commit and after push |
| `git diff --check` / `git diff --cached --check` | Whitespace validation before commit |

POSIX stdin redirection is shown above. In PowerShell use
`Get-Content -Raw scripts/check_gate_c.py | docker compose exec -T trace-backend python -`
(similarly for foundation). The execution harness checked subprocess exit codes.

One existing Starlette TestClient deprecation warning appeared in each backend run.
It does not hide a failure or skip, and dependency changes were intentionally avoided.
The initial format check flagged the two unfinished verification scripts; Ruff
formatted them and subsequent checks passed. No product defect required a repair.

## Required behavior verified

- Concurrent real HTTP propagation: 25 overlapping requests / 200 distinct spans,
  including continued, malformed and missing incoming context; no trace/parent crossover.
- Concurrent real persisted scenarios: 18 overlapping mixed requests with independent
  identities, correct parents and request-scoped error/delay behavior.
- Core nested async context, exception and actual task cancellation regressions pass.
- Randomized PostgreSQL ingestion: five seeded orders yield identical reconstruction;
  the real Compose Gate C smoke adds three shuffled orders. Child-before-parent,
  missing-parent subtrees and cycles are safe.
- Duplicate ingestion: one stored row; eight concurrent conflicting submissions yield
  one stored winner and seven duplicates without overwrite. Real eight-span duplicates
  return duplicate and preserve exact detail. Query snapshot and request-size regressions pass.
- The exporter tests cover distinct-identity drop-newest, bounded queues/timeouts/drain,
  no retries and collector-down behavior. Slow-collector/saturated-queue tests keep
  normal business traffic successful.
- The new repeatable system check sends three successful normal requests while the
  trace backend is stopped, restores it in a `finally` block and compares the complete
  previously stored trace exactly.
- PostgreSQL is stopped without removing its volume. Health/list/services return
  sanitized 503 errors while Order succeeds. PostgreSQL is restored in `finally`;
  the same named volume and exact stored trace survive.

Real scenario traces from this M7 run:

| Scenario | Trace ID | Business / telemetry result |
| --- | --- | --- |
| healthy / normal | `da85016815edd79a6af1431c90bf4d19` | 200, eight OK spans, exact CLIENT → SERVER parents |
| slow_payment | `a544606ecf409fc0dc71f66121e45ea6` | 200, eight OK spans, at least 295 ms inside process-payment; duration propagates outward |
| payment_error | `c4d91e55508c28c4fa8c5f61a5dd17c0` | 502, five spans, four ERROR spans, Notification absent |
| restart/privacy probe | `8ce13e8ffc693a90a901b1464fc45a07` | Eight spans; exact detail preserved across collector and PostgreSQL restarts |

## Privacy and prohibited-scope audit

The repository scanner rejects personal-email patterns, common private-key/token
patterns, personal absolute paths, tracked or historical private env files and private
artifacts. It checks every historical author/committer email against
`156163069+manthan3502@users.noreply.github.com`. Match values are never printed.
Staged changes are scanned before commit; existing GitHub authorization is used only
privately for push and reading hosted Actions results.

The system check supplies unique fake Authorization, Cookie and item-body canaries.
None appear in real stored span JSON, raw PostgreSQL rows or container logs. Approved
attribute keys are enforced. The actual database password is read only in memory and
does not appear in any persisted span or collected log. These are focused regression
and repository audits, not a claim to detect every possible secret or personal datum.

Case-insensitive source/dependency/Compose searches reviewed unauthorized components.
Matches in tests, scope documentation and the UI's manual Retry button are expected;
the button is not exporter retry infrastructure. The lockfile's `opentelemetry-api`
is a mandatory transitive dependency of pinned FastAPI 0.142.2. Installed framework
metadata and runtime checks show no OpenTelemetry SDK, no exporter and inactive native
telemetry in all four apps. MicroTrace never imports it or replaces custom tracing.
No dependency removal or framework redesign was needed.

Exactly six approved Compose services and one PostgreSQL named volume were verified.
Only React/react-dom are frontend runtime dependencies. There is no Kafka, Redis,
ClickHouse, AI/LLM, anomaly detector, auth system, sampling or retry infrastructure.
The schema and Gate C assert only `spans` plus Alembic metadata; no persisted traces
table or parent FK exists. No new product features or extra UI pages were added.

## Hosted CI

`.github/workflows/ci.yml` runs on main pushes, pull requests and manual dispatch,
with read-only contents permission and bounded job timeouts:

- Backend: Python 3.12, hash-locked install, PostgreSQL 16 health/migration, Ruff,
  full-history repository privacy, unmarked tests and all database integration tests.
- Frontend: Node 24, `npm ci`, lint, Vitest, TypeScript and production build.
- Compose E2E: six-container build/health, migration, foundation, Gate C, all three
  scenarios and repeatable collector/database outage, persistence and privacy checks.
  Cleanup runs even if a step fails. CI credentials are public disposable test values.

Local acceptance is recorded above. The actual hosted run is inspected after the
verified milestone commit is pushed; its run URL, job conclusions and any repair
are supplied in the M7 completion report. YAML validation alone is not a hosted PASS.

## What to understand and limits

- Unit tests isolate tracing/reconstruction; integration tests use real HTTP and/or
  migrated PostgreSQL; Compose E2E proves the actual multi-container path.
- Identity and parent assertions prove isolation and correctness rather than merely
  counting spans. Arrival order cannot define the trace tree.
- Idempotency retains the first successful payload under concurrent conflicts.
- Collector/DB outages lose best-effort telemetry; business traffic keeps running.
  Persistence protects spans already stored, not spans dropped before storage.
- The queue remains bounded and non-durable; no retries, retention, auth or sampling.
- This is a compact educational tracing platform. Local/hosted QA does not constitute
  cloud deployment or Gate E. M8 remains NOT STARTED.
