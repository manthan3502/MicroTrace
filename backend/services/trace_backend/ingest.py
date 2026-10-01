from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from microtrace_sdk.models import FinishedSpan
from services.trace_backend.database import get_engine
from services.trace_backend.db_models import spans

router = APIRouter()
MAX_PAYLOAD_BYTES = 64 * 1024


def store_span(engine: Engine, span: FinishedSpan) -> bool:
    statement = (
        insert(spans)
        .values(**span.model_dump())
        .on_conflict_do_nothing(index_elements=["trace_id", "span_id"])
        .returning(spans.c.span_id)
    )
    with engine.begin() as connection:
        return connection.execute(statement).scalar_one_or_none() is not None


@router.post("/api/v1/spans")
async def ingest(request: Request, engine: Annotated[Engine, Depends(get_engine)]):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Use application/json")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_PAYLOAD_BYTES:
            raise HTTPException(413, "Span payload exceeds 64 KiB")
        body.extend(chunk)
    try:
        span = FinishedSpan.model_validate_json(bytes(body))
    except ValidationError:
        # Never echo invalid attribute values, error messages or request bodies.
        raise HTTPException(422, "Invalid span payload") from None
    try:
        stored = await run_in_threadpool(store_span, engine, span)
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    return JSONResponse(
        {"status": "stored" if stored else "duplicate"}, status_code=201 if stored else 200
    )
