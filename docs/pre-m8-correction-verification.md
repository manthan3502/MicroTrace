# Pre-M8 corrections

This pass fixes only the three final-audit defects. M8 is not started.

- Service identity uses an own-property check. Known identities stay unchanged;
  constructor, toString, __proto__ and custom-service use the safe fallback.
  Collector-valid names remain unrestricted.
- The service query dependency reuses the collector's reject_nul validator and
  returns sanitized 422 Invalid service filter before database access.
  Tests prohibit connection attempts for three NUL inputs and verify persisted
  Unicode service filtering, normal health and subsequent valid requests.
- Axis-only margin and timeline-only border were removed. Zero-width tick anchors,
  gridlines and bars share the same coordinate bounds. Gridlines use the displayed
  ticks instead of a fixed quarter-width pattern. Timing formulas, root-duration
  semantics, kind shapes and minimum-width behavior are unchanged.

## Local verification actually run

Commands below abbreviate the existing Docker Desktop executable as docker.

| Command/check | Result |
| --- | --- |
| Backend query tests with `-k "nul_service or unicode_service"` and the PostgreSQL test URL | 4 passed, 25 deselected, 1 warning; 1.82 s |
| Frontend focused Vitest name filter for new regressions | 14 passed, 32 intentionally excluded; 1.34 s |
| Complete PostgreSQL-backed `pytest -p no:cacheprovider` | 194 passed, no skips, 1 warning; 44.95 s |
| Same environment, `pytest -p no:cacheprovider -m integration` | 75 passed, 119 deselected, no skips, 1 warning; 31.60 s |
| `docker compose exec -T frontend npm test` | 46 passed, three files; 1.42 s |
| Frontend npm run lint / typecheck / build | PASS; production Vite build 1.36 s |
| Native Ruff check backend scripts / format --check backend scripts | PASS; 48 formatted files |
| Compose config / up --build -d --wait --wait-timeout 180 | PASS; all six containers healthy |
| check_foundation.py via container stdin | Four real backend health endpoints PASS |
| check_gate_c.py via container stdin | Real pipeline, exact parents, duplicates, filters, child-first, orphans, shuffled arrival and cycles PASS |
| check_scenarios.py | Healthy eight spans, slow eight spans, error five spans PASS |
| Direct GET with service=bad%00name followed by GET /health | Sanitized 422, then health 200 |
| check_system.py with the existing Docker executable | Collector/database outages, exact restart persistence, request canaries and stored/log secret exclusion PASS |

The initial Ruff check required formatting one new test signature; it was formatted
and the final lint/format checks passed. The existing Starlette TestClient warning
remains unchanged.

## Real browser Gate D

Fresh real scenario traces through services, exporter, collector, PostgreSQL and API:

- Healthy: c0bab34d64cbf1067915964c2f82f67a.
- Slow: d37ce1520c1e44ef90fecf04675a3e61.
- Error: a7e7fe4147808ad4beb66ea7711411af.

Browser axis and every timeline measured 325.200012 pixels wide with identical
origins. Tick anchors and row gridlines aligned. Bar positions/widths were compared
with independently fetched persisted offsets/durations; maximum discrepancy was
0.01227 pixels, below a 0.1-pixel tolerance, across all three scenarios.

Slow process-payment was 300547 us inside a 343480 us root. Its long thin INTERNAL
bar and enclosing Payment SERVER/Order CLIENT bars aligned with the 100/200/300 ms
ruler and gridlines. Selection and parent details remained functional.

A clearly labelled four-span synthetic collector fixture exercised all three
prototype-colliding names plus custom-service in the actual list, waterfall and
details. One missing-parent span also verified incomplete/orphan rendering and
non-quarter 250/500/750 ms gridlines on a 920 ms scale. Its measured discrepancy
was below 0.01 pixels. Browser console warnings/errors were absent. Only these
four synthetic spans were removed after QA; existing traces were preserved.

Gate C and Gate D are renewed locally. Screenshots are local ignored evidence.
The completion report records repository/privacy checks, exact commit identity,
push and actual hosted CI result after the commit is created.
