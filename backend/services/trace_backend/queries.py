from collections import defaultdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import BigInteger, Engine, case, cast, func, select
from sqlalchemy.exc import SQLAlchemyError

from microtrace_sdk.ids import valid_id
from microtrace_sdk.models import reject_nul
from services.trace_backend.database import get_engine
from services.trace_backend.db_models import spans
from services.trace_backend.reconstruction import reconstruct

router = APIRouter()
Database = Annotated[Engine, Depends(get_engine)]


def service_filter(service: Annotated[str | None, Query(min_length=1, max_length=100)] = None):
    try:
        return reject_nul(service)
    except ValueError:
        raise HTTPException(422, "Invalid service filter") from None


def list_traces(engine, service, status, min_duration_ms, limit, offset):
    root = spans.c.parent_span_id.is_(None)
    roots = func.sum(case((root, 1), else_=0))
    fallback = cast(
        func.extract("epoch", func.max(spans.c.end_time) - func.min(spans.c.start_time)) * 1000000,
        BigInteger,
    )
    duration = case((roots == 1, func.max(spans.c.duration_us).filter(root)), else_=fallback)
    statement = select(spans.c.trace_id).group_by(spans.c.trace_id)
    if service is not None:
        statement = statement.having(func.bool_or(spans.c.service_name == service))
    if status is not None:
        statement = statement.having(func.bool_or(spans.c.status == "ERROR") == (status == "ERROR"))
    if min_duration_ms is not None:
        statement = statement.having(duration >= min_duration_ms * 1000)
    statement = (
        statement.order_by(func.min(spans.c.start_time).desc(), spans.c.trace_id)
        .limit(limit)
        .offset(offset)
    )
    # Candidate selection and reconstruction see the same snapshot while spans arrive.
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            identities = connection.execute(statement).scalars().all()
            grouped = defaultdict(list)
            if identities:
                for row in connection.execute(
                    select(spans).where(spans.c.trace_id.in_(identities))
                ).mappings():
                    grouped[row["trace_id"]].append(row)
            return {
                "items": [reconstruct(grouped[identity])["trace"] for identity in identities],
                "limit": limit,
                "offset": offset,
            }


@router.get("/api/v1/traces")
def traces_list(
    engine: Database,
    service: Annotated[str | None, Depends(service_filter)] = None,
    status: Literal["OK", "ERROR"] | None = None,
    min_duration_ms: Annotated[int | None, Query(ge=0, le=9223372036854775)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
):
    try:
        return list_traces(engine, service, status, min_duration_ms, limit, offset)
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None


@router.get("/api/v1/traces/{trace_id}")
def trace_detail(trace_id: str, engine: Database):
    if not valid_id(trace_id, 32):
        raise HTTPException(422, "Invalid trace ID")
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(select(spans).where(spans.c.trace_id == trace_id))
                .mappings()
                .all()
            )
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    if not rows:
        raise HTTPException(404, "Trace not found")
    return reconstruct(rows)


@router.get("/api/v1/services")
def services_list(engine: Database):
    try:
        with engine.connect() as connection:
            names = (
                connection.execute(
                    select(spans.c.service_name).distinct().order_by(spans.c.service_name)
                )
                .scalars()
                .all()
            )
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    return {"services": names}
