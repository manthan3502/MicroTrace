# M0 foundation

- Order, Payment, Notification and the trace backend are separate FastAPI/Uvicorn
  processes sharing one Python project. A monorepo shares code, not process state.
- Compose supplies a private network and service-name DNS. Only local frontend,
  Order and trace-backend ports are bound on the host.
- Demo services do not depend on collector health. Only the trace backend uses PostgreSQL.
- PostgreSQL is the sole persistent infrastructure. Alembic creates the frozen `spans`
  table; its `alembic_version` table records migration bookkeeping.
- The composite key is `(trace_id, span_id)`. Parent IDs have no foreign key because
  later telemetry can arrive child-first. Required checks constrain kind, status and duration.
- Trace-backend `/health` executes `SELECT 1` and returns 503 on database loss without
  exposing connection details. Demo `/health` checks process availability only.

M0 does not implement tracing primitives, export, ingestion, query APIs, demo business
logic, scenarios, UI routes or the waterfall. The React shell states this honestly.
The next milestone is M1, but it is not part of the first run.
