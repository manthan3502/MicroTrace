# Single-host EC2 deployment

Deployed on the owner-approved Ubuntu 24.04 EC2 host on 2026-10-04 (IST):
[public dashboard](http://3.25.122.39/traces). Host checks, external HTTP/private-port
probes, real scenarios, browser QA and restart persistence passed. Final Gate E
sign-off awaits hosted M8 CI. No instance or additional cloud resource was created,
and no security-group rules were changed. Never paste credentials or private keys.

Use one Linux EC2 VM with Docker and Compose v2 or newer. Allow enough RAM for PostgreSQL,
four Python processes and the Node build (about 4 GiB is a starting point to
assess before instance selection). No separate gateway, managed DB or orchestrator.

The frontend Dockerfile builds React then copies static assets into Nginx; its
production runtime contains no Node/Vite. Standalone compose.production.yml avoids
override merge surprises: only frontend publishes a port; all six services have
health checks and unless-stopped restart policies.

## Public routes

| Route | Method | Destination |
| --- | --- | --- |
| /, /traces, /traces/:traceId, /assets/* | GET | Static React / SPA fallback |
| /api/v1/traces | GET | Query backend |
| /api/v1/traces/:traceId | GET | Query backend; lowercase 32-hex ID |
| /api/v1/services | GET | Query backend |
| /health | GET | Existing backend health |
| /orders | POST | Existing Order business/demo endpoint |

No catch-all API proxy. Ingestion and framework docs return 404 through Nginx;
write methods on query routes return 405. Internal exporters still reach
http://trace-backend:8000/api/v1/spans. Private services publish no host ports.
Nginx re-resolves internal DNS after replacement. Access logs omit query strings,
bodies, headers and client addresses.

## Prepare the approved host

Install Docker through its [official Linux instructions](https://docs.docker.com/engine/install/)
and [Compose plugin instructions](https://docs.docker.com/compose/install/linux/).
Enable Docker's system service. Transfer the reviewed checkout using approved
Git/SSH access. Never copy a workstation .env/private key into Git.

Create .env from .env.example on the host. Set a unique database password and its
URL-encoded DATABASE_URL counterpart; restrict permissions with `chmod 600 .env`.
The example has placeholders, not credentials. Keep internal URLs unchanged.
Defaults bind only to loopback, MICROTRACE_BIND_ADDRESS=127.0.0.1 and
MICROTRACE_HTTP_PORT=8080.

After explicit public-exposure approval, set MICROTRACE_BIND_ADDRESS=0.0.0.0 and
MICROTRACE_HTTP_PORT=80. The approved security-group plan allows HTTP to the demo
and SSH only from the owner's approved address. Never open 5432/8000/8001/5173.
Do not change cloud firewall rules without approval.

```sh
docker compose -f compose.production.yml config --quiet
docker compose -f compose.production.yml up --build -d --wait --wait-timeout 180
docker compose -f compose.production.yml exec -T trace-backend alembic upgrade head
docker compose -f compose.production.yml exec -T trace-backend alembic current
docker compose -f compose.production.yml ps
```

Migrations are explicit. Preserve postgres-data and never use down -v. Rebuild
with the same project/volume for updates. A named volume is not a backup.

## Actual deployed verification

Create a Python 3.12 virtual environment and install the locked verification dependencies:
`python -m pip install --require-hashes -r backend/requirements.lock`.
Run on the deployed host and set EDGE_URL to its real listening origin:

```sh
python scripts/check_production.py --url "$EDGE_URL" --check-restart
docker compose -f compose.production.yml exec -T trace-backend python - < scripts/check_gate_c.py
```

The smoke verifies six healthy containers, restart/port boundaries, static SPA,
direct detail routing, query allowlist, blocked valid-span ingestion, all three
real scenarios and exact trace persistence across PostgreSQL restart.

From a separate computer outside the VM/Compose, set PUBLIC_URL to the actual
approved address:

```sh
python scripts/check_production.py --url "$PUBLIC_URL" --http-only --probe-private-ports
```

This intentionally tries ingestion through the edge and TCP private ports. Open
the actual dashboard externally and verify each scenario/direct navigation.
Loopback smoke alone does not establish Gate E.

Local Windows smoke can omit --probe-private-ports when a confirmed unrelated app
owns a tested port; inspect Compose bindings instead and leave that app alone.
Keep strict external probes on the deployed host and clean hosted runner.

CI checks development reliability then production edge/private ports/persistence
on Linux. It is additional evidence, not EC2 deployment. The final milestone
commit's hosted run must pass.

References: [Docker production guidance](https://docs.docker.com/compose/how-tos/production/),
[Nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
