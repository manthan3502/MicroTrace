# M5 scenarios and reliability

Exactly normal, slow_payment and payment_error, request-scoped and deterministic.
The slow sleep is inside Payment process-payment INTERNAL. The deliberate exception
is raised inside that span and converted to sanitized HTTP 500; Order returns controlled
502 without Notification. Existing inbound/outbound instrumentation records the four
affected spans as ERROR. No restart, global fault switches, new dependencies or fields.
scripts/demo.py uses standard-library HTTP and prints the result/trace/dashboard URL.
scripts/check_scenarios.py verifies real Compose telemetry for all three scenarios.

Actual verification:
- Ruff format/check: initial long lines corrected by formatter; final native lint
  and format --check PASS (46 files), Docker PASS (42 files).
- docker compose up --build -d --wait: PASS, all six healthy.
- complete PostgreSQL-backed Docker pytest -p no:cacheprovider: 190 passed, zero
  skips, 31.67s. Eight new M5 cases cover real persisted scenarios, 18 overlapping
  mixed requests, invalid scenario/delay and actual slow collector with capacity-one
  saturation: six orders succeed while all 48 spans drop. Inherited tests cover
  unavailable collector, bounded timeout/drain, no retries, warnings and DB failures.
- native scripts/check_scenarios.py against Compose: healthy/slow/error PASS, exact
  eight/eight/five-span telemetry, parents, nested slow timing and four ERROR spans.
- scripts/demo.py healthy, slow --slow-ms 300, error: PASS; HTTP 200/200/502,
  trace IDs and URLs printed, expected exit codes zero.
- actual PostgreSQL stop/restart via stdin probe: health, ingestion, list and service
  metadata return sanitized 503; a normal order succeeds. Existing trace is byte-value
  equivalent after named-volume-preserving restart and backend recovery.
  The first PowerShell probe converted UTC JSON timestamps and incorrectly tested
  ingestion with an invalid payload; database restored in finally. Rerun preserved
  original JSON and all checks passed. No meaningful data deleted.
- check_foundation.py: all four health checks PASS; docker compose ps: six healthy.
- identity/privacy and git diff --check: PASS before milestone commit.

Gate: N/A (Gate D follows M6). No blockers. Starlette warning remains. Telemetry is
best effort, not durable. UI is still the foundation shell until M6.

Understand: nested waiting propagates latency naturally; errors belong to each failed
operation; Notification is absent because the business flow stops; context/fault state
is per request; telemetry loss is independent of business success.
