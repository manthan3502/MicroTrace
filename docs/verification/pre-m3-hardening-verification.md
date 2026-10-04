# Pre-M3 hardening verification

Completed attributes use a copied MappingProxyType; scalar-only validation is unchanged.
Serialization returns an ordinary detached JSON object. Tests reject insertion/replacement
and show that retained input dictionaries and serialized copies cannot change the snapshot.
Gate B now checks raw downstream traceparent headers and active SERVER flags for 00/01/ab/ff.
Actual task.cancel() tests cover suspended inbound/outbound operations and context restoration.
No dependencies or architecture changes.

Commands/results:
- Native python -m pytest -c backend/pyproject.toml backend/tests/unit/test_tracing_core.py
  backend/tests/unit/test_http_instrumentation.py backend/tests/integration/test_propagation.py -q:
  78 passed in 13.97s; one sandbox cache-permission warning.
- In-memory diagnostic forcing outbound flags to 01: 3 expected failures (00/ab/ff),
  1 pass (01); diagnostic assertion PASS. No source modification by this probe.
- Initial ruff check --fix backend scripts: import fix and five line-length findings;
  ruff format backend scripts resolved the formatting. Final lint/format check PASS (31 files).
- Docker initially unresolved in sandbox; direct installed CLI with approved host access works.
- docker compose config --quiet: PASS.
- docker compose up --build -d --wait: PASS.
- docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest -p no:cacheprovider':
  84 passed, no skips, 14.71s. One existing Starlette TestClient deprecation warning.
- docker compose exec -T trace-backend ruff check .: PASS.
- docker compose exec -T trace-backend ruff format --check .: PASS (30 files).
- Get-Content -Raw scripts/check_foundation.py | docker compose exec -T trace-backend python -:
  four health endpoints PASS.
- docker compose ps: all six services healthy.

Gate A and Gate B regression PASS. Git privacy/identity, commit, push and tree results
are recorded in the completion report. M3 begins only after this hardening checkpoint.
