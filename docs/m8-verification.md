# M8 deployment verification

Actual Ubuntu 24.04 EC2 deployment verified on **2026-10-04 (IST)** at
[http://3.25.122.39/traces](http://3.25.122.39/traces). Gate E awaits the production
verification checkpoint's hosted CI. The final M8 milestone commit follows that
check; its hosted run must also pass before completion is reported.

Prepared changes were preserved from HEAD 9ecf3a1de09d020157318d4d81d52f10df299c69.
Previous local preparation on 2026-10-02 passed 194 backend, 75 integration and
46 frontend tests. The results below are fresh actual EC2/external verification.

## Architecture and access

- Existing owner-approved host; no new cloud resource or security-group change.
- Docker Engine 29.8.2 / Compose 5.6.0 from Docker's official repository; Python 3.12.
- Exactly six healthy runtime containers, each with health/restart policies.
  Only frontend/Nginx publishes 0.0.0.0:80. Host listeners and external TCP probes
  confirm no 5432/8000/8001/5173 exposure. Existing SSH was preserved.
- Reviewed source archive excluded .git, .env, SSH material and caches. SSH used
  the local key in place; key contents were never copied or logged.
- Unique database secret generated only on EC2 in a mode-600 .env. No secret value
  was displayed. Named volume microtrace_postgres-data was never deleted/reset.

## Commands actually run on EC2

Commands ran from the transferred source with sudo for Docker. Host verification
used a virtualenv with hash-locked backend dependencies; test containers had
fresh locked installations.

| Command/check | Exact result |
| --- | --- |
| Production Compose config / build / up --wait | PASS; five app images built, PostgreSQL pulled, six healthy |
| Backend alembic upgrade head / current | PASS; 0001 (head) |
| `python scripts/check_production.py --url http://127.0.0.1 --check-restart --probe-private-ports` | PASS |
| External `python scripts/check_production.py --url http://3.25.122.39 --http-only --probe-private-ports` | PASS |
| `COMPOSE_FILE=compose.production.yml python scripts/check_system.py --order-url http://127.0.0.1 --backend-url http://127.0.0.1` | PASS; outages, restart and stored-data/log privacy |
| Backend `python - < scripts/check_gate_c.py` | Gate C PASS |
| Backend `sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest'` | 194 passed, zero skips, one existing Starlette warning; 29.74 s |
| Same command with `pytest -m integration` | 75 passed, 119 deselected, zero skips, same warning; 19.34 s |
| `docker build --target development -t microtrace-frontend-development:qa frontend` | PASS; temporary QA image, not another runtime service |
| `docker run --rm --network none microtrace-frontend-development:qa sh -c 'npm test && npm run lint && npm run typecheck && npm run build'` | 46 tests / three files passed; ESLint, TypeScript and build PASS |
| `ruff check backend scripts` / `ruff format --check backend scripts` | PASS; 49 files formatted |
| Frontend nginx -t / production docker compose ps | PASS; config valid, all six healthy |
| Local check_repository.py plus candidate/screenshot privacy scan | Checked before each push; exact noreply identity retained |

The production commands were `docker compose -f compose.production.yml config
--quiet` and `docker compose -f compose.production.yml up --build -d --wait
--wait-timeout 180`. Backend commands used `docker compose -f compose.production.yml
exec -T trace-backend`. Migrations remain explicit.

A bootstrap stdin command encountered a Windows CR newline after installing Docker.
It was corrected without source changes or reinstallation. Host checks then ran
from files to avoid Docker exec consuming SSH script stdin. Acceptance checks passed.

## Deployed behavior

- Public root/static assets, /traces and direct detail navigation work. GET trace
  list/detail/services and health pass through Nginx; existing POST /orders triggers
  demos. Write methods on query routes return 405.
- POST /api/v1/spans returns 404 even for a valid stored span; encoded/trailing-slash
  variants and framework docs are blocked. Internal exporters still work.
- Healthy: Order 200, eight OK spans, three services. Slow: eight spans with a long
  process-payment path. Error: Order 502, five spans, four ERROR, Notification absent.
- Three normal requests succeed with collector stopped. Database outage yields
  sanitized query/health 503 while business requests still succeed.
- PostgreSQL restart preserves the named volume and exact original trace response.
- Request-body/auth/cookie canaries and the actual database secret are absent from
  persisted spans and all container logs, including Nginx logs.
- Gate C machine-checks exact CLIENT-to-SERVER parents, idempotency, combined filters,
  randomized/child-before-parent arrival, orphans/cycles and only spans persistence.

## Real external browser evidence

All four screenshots were refreshed from the public EC2 dashboard: fake demo data,
no browser/account chrome, private paths, credentials or desktop content. Full-page
capture was unavailable; actual viewport captures were used without altering UI.

| Screenshot | Actual deployed trace |
| --- | --- |
| trace-list.jpg | Persisted healthy/slow/error results |
| healthy-trace.jpg | 25960d56f86566edbc3896b2ab07f7ce; eight OK spans, 54 ms |
| slow-trace.jpg | bf0b2df63b07eaba5955ddb249e6af60; eight spans, 331 ms; process-payment 301 ms selected |
| error-trace.jpg | 454b8b6590367346b4120869d4353592; five spans, four errors; sanitized error selected |

Direct navigation and selection passed. Slow axis and all eight timelines share
x=348.800 px / width=325.200 px. Displayed 0/100/200/300 ms ticks and grid positions
match at x=348.800/447.013/545.237/643.463 px; long Payment bars visually align.
The approved minimum-width treatment of very short bars is unchanged.

## Git, CI and final sign-off

Author/committer: Manthan <156163069+manthan3502@users.noreply.github.com>.
No .env, key, credentials, personal email or cache is tracked. Changes concern
production configuration, verification, docs and screenshots only.

Hosted Backend, Frontend and Compose E2E must pass for the production verification
checkpoint before creating the final named M8 milestone commit. The new Compose
CI checks production edge/private ports/persistence. Its final milestone run will
also be inspected on the exact commit; YAML alone does not establish completion.
