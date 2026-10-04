# Pre-M5 hardening verification

Reject NUL in telemetry text/string attributes before storage; allow-listed keys also
reject NUL. Unicode and all scalar/size rules remain supported. Six invalid-location
regressions spy on storage, assert sanitized 422, check health and accept a subsequent
valid span. Unicode round-trips through PostgreSQL. No dependency added.

The integration marker now includes ingestion, queries and schema. README supplies the
database for the complete suite and marked workflow. Overflow uses 102 distinct
trace/span identities and proves the oldest two remain while the newest 100 are dropped.
Concurrent conflicting duplicates preserve the writer receiving 201. Chunked payloads
at 65536 bytes are accepted and 65537 bytes rejected. A late ERROR inserted between
list queries cannot invalidate the repeatable-read result.

Actual commands/results:
- native pytest test_exporter.py -q -p no:cacheprovider: 12 passed, 0.25s.
- temporary in-memory drop-oldest mutation: expected regression failure (1 failed,
  0.08s); harness verified this failure and restored the original method. No file mutation.
- docker compose config --quiet; docker compose up --build -d --wait: PASS, six healthy.
- Docker focused exporter/ingestion/query suite with test DB: 74 passed, 7.36s.
- Docker full PostgreSQL suite: 182 passed, zero skips, 18.13s.
- corrected documented pytest -m integration with test DB: 63 passed, 119 deselected,
  zero skips, 7.49s. Native collect-only confirms 63/182 selected (0.79s).
- Ruff check backend scripts and format --check: PASS, 43 files. Docker Ruff: PASS,
  41 files. Formatting/import corrections applied before final verification.
- Compose check_gate_c.py: PASS; check_foundation.py: all four backend health checks PASS.
- git diff --check and repository identity/privacy checks before commit: PASS.

Existing Starlette TestClient deprecation warning retained; no dependency change.
Best-effort telemetry remains nondurable. Existing public data is preserved; database
tests create/drop isolated schemas. Gate C remains PASS. No blockers.

Understand: invalid input should never masquerade as database loss; markers select real
verification; distinct identities distinguish overflow policies; concurrent duplicates
have one authoritative winner; list filtering/reconstruction must share one snapshot.
