# M0 verification record

Verified on 2026-10-02 (Asia/Kolkata). Scope: M0 only. M1 was not started.
Docker Desktop was already installed; its CLI directory was temporarily added to
the verification shell's PATH. No Docker reinstall or machine-wide PATH change occurred.

## Final acceptance checks

| Command actually run | Result |
| --- | --- |
| `docker --version` | Docker 29.8.1 |
| `docker compose version` | Compose v5.5.1 |
| `docker info --format '{{.OSType}}'` | `linux` |
| `docker compose config --quiet` | PASS |
| `docker compose up --build -d --wait` | PASS; all six containers healthy |
| `docker compose exec -T trace-backend alembic upgrade head` | PASS; initial revision 0001 applied, subsequent run safely did nothing |
| `docker compose exec -T trace-backend alembic current` | `0001 (head)` |
| `docker compose exec -T trace-backend sh -c 'MICROTRACE_TEST_DATABASE_URL="$DATABASE_URL" pytest'` | 6 passed; includes the real PostgreSQL schema check; no skips |
| `docker compose exec -T trace-backend ruff check .` | PASS |
| `docker compose exec -T trace-backend ruff format --check .` | PASS; 15 Python files |
| `Get-Content -Raw scripts/check_foundation.py \| docker compose exec -T trace-backend python -` | All four real HTTP health endpoints returned 200 and `{"status":"ok"}` |
| `docker compose ps` | All six healthy; PostgreSQL, Payment and Notification have no host port bindings |
| `docker compose exec -T frontend npm test` | 1 smoke test passed with Vitest 4.1.11 |
| `docker compose exec -T frontend npm run lint` | PASS |
| `docker compose exec -T frontend npm run build` | TypeScript check and Vite production build PASS |
| `docker compose exec -T frontend npm audit --json` | 0 vulnerabilities |
| `docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d+ spans"'` | Live column types, nullability, defaults, composite PK, three checks and three additional indexes match the contract; no parent FK |
| `Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing` | HTTP 200 |
| `Invoke-RestMethod -Uri 'http://localhost:8000/health'` | `status: ok`; database reachable |
| `Invoke-RestMethod -Uri 'http://localhost:8001/health'` | `status: ok` |

The backend suite emits a Starlette warning about future TestClient HTTPX compatibility.
The tests pass with the approved HTTPX dependency. Dependency installation also reports
deprecation notices for ESLint 9 and a transitive jsdom encoding package.
FastAPI brings `opentelemetry-api` transitively; this project installs no OpenTelemetry SDK,
configures no OpenTelemetry instrumentation and implements no tracing in M0.

## Setup, earlier attempts and repairs

Local runtime paths are omitted for privacy. `Python312` below denotes the bundled
Python 3.12 executable; local Python/pytest/Ruff commands used the backend virtual environment.

- `uv --version`, `node --version`, `npm.cmd --version`, `Python312 --version`:
  uv 0.11.0, Node 24.14.1, npm 11.11.0, Python 3.12.14.
- `uv python list --only-installed`: initial default cache access failed; the later
  `uv --cache-dir ./.cache/uv python list --only-installed` ran successfully with no entries.
- `wsl.exe --list --quiet`: sandbox access denied. Docker subsequently confirmed Linux
  containers directly; no WSL configuration changes were made.
- The first Docker executable attempt in the sandbox was denied. The permitted execution
  context accessed the user's existing Docker installation successfully.
- `uv --cache-dir ./.cache/uv sync --project backend --python <Python312>`:
  sandbox network denied, then succeeded in the permitted execution context.
- `uv --cache-dir ./.cache/uv export --project backend --locked --no-emit-project --format requirements-txt --output-file backend/requirements.lock`:
  succeeded; hash-pinned requirements generated from `uv.lock`.
- `npm.cmd install --cache ../.cache/npm --no-fund --no-audit`: sandbox attempt stopped;
  permitted Windows attempt failed on esbuild (`EFTYPE`) and left incomplete local modules.
- `npm.cmd install --package-lock-only --ignore-scripts --cache ../.cache/npm --no-fund --no-audit`:
  exited successfully, but its initial lockfile caused `npm ci` in the first Docker build
  to fail with `Invalid Version`.
- The lockfile was regenerated from `package.json` in a clean `node:24-bookworm-slim`
  container using `npm install --package-lock-only --ignore-scripts --no-fund --no-audit`.
  The full Compose build then succeeded. The same regeneration command was used after
  updating Vitest to 4.1.11.
- Local `python -m pytest`: 5 passed, 1 schema check skipped without a database URL;
  the first invocation from the repository root also warned about the unregistered
  integration marker.
- Local `ruff check backend scripts` and `ruff format --check backend scripts` initially
  found one long line and two formatting issues. `ruff format backend scripts` fixed them;
  both checks subsequently passed (16 Python files including the root script).
- Local `python -m pytest -c backend/pyproject.toml backend/tests`: 5 passed, 1 explicit
  database skip. The final container run with a real database passed all six tests.
- The first container backend test run failed collection because `services` was missing
  from pytest's path. Explicit pytest `pythonpath` fixed it. Recursive bytecode exclusions
  were added to the Docker context to keep host-generated caches and paths out of images.
- The first frontend container test/lint/build run passed with Vitest 3.2.7, but
  `npm audit --json` identified two related moderate findings for the Vitest mocker.
  Vitest 4.1.11 resolved them; tests, lint, build and audit were rerun successfully.
- `docker compose up --build -d --wait` ran three times: first failed on the invalid
  frontend lockfile, second passed, third passed with the final corrected source/dependencies.

## Git/privacy verification

- Inspected local/global Git name/email; global configuration was not changed.
- Initialized `main` and set repository-local name and the approved GitHub noreply address.
  The empty sandbox-owned Git initialization was preserved in an ignored backup and
  reinitialized under the user's account to avoid ownership errors in normal PowerShell.
- `git credential-manager github list` identified the existing account. The existing
  credential was validated against GitHub's `/user` and dedicated repository APIs without
  displaying or saving it. Account ID/name match the supplied noreply address and existing
  authorization has push permission.
- `git ls-remote https://github.com/manthan3502/MicroTrace.git` confirmed an empty remote.
  Only this dedicated repository was configured as `origin`.
- Checked local `user.name`/`user.email` and author/committer environment overrides.
- `git check-ignore .env backend/.venv frontend/node_modules .cache` confirmed exclusions.
- `git diff --check`, `git diff --cached --check`, `git diff --cached --stat`, and
  `git status --short --branch` were inspected before committing.
- Staged text content was scanned for personal email addresses, credential patterns,
  the actual local-only database password, private paths, generated dependencies and
  large files. The scan passed. No preceding commit history existed.

Final commit hash, author/committer metadata, push outcome and post-commit working-tree
status are supplied in the milestone completion report because this record is included
in that milestone commit.
