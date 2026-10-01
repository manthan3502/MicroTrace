import os
from collections.abc import Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from microtrace_sdk import Tracer
from microtrace_sdk.exporter import SpanExporter
from microtrace_sdk.middleware import TracingMiddleware
from microtrace_sdk.models import FinishedSpan


@asynccontextmanager
async def service_lifespan(app: FastAPI):
    # One client per process lifecycle, never one per business request.
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
        app.state.http_client = client
        exporter = app.state.exporter
        if exporter is not None:
            exporter.start(client)
        try:
            yield
        finally:
            if exporter is not None:
                await exporter.close()


def create_service_app(
    title: str,
    service_name: str,
    on_finish: Callable[[FinishedSpan], None] | None,
) -> FastAPI:
    app = FastAPI(title=title, lifespan=service_lifespan)
    # An explicit test hook replaces delivery. Normal apps always use bounded export.
    exporter = (
        None
        if on_finish is not None
        else SpanExporter(
            os.environ.get("COLLECTOR_URL", "http://trace-backend:8000/api/v1/spans"),
            int(os.environ.get("EXPORT_QUEUE_SIZE", "256")),
            float(os.environ.get("EXPORT_TIMEOUT_SECONDS", "1")),
        )
    )
    app.state.exporter = exporter
    app.state.tracer = Tracer(service_name, on_finish if exporter is None else exporter.enqueue)
    app.add_middleware(TracingMiddleware, tracer=app.state.tracer)
    return app
