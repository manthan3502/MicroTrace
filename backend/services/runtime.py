from collections.abc import Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from microtrace_sdk import Tracer
from microtrace_sdk.middleware import TracingMiddleware
from microtrace_sdk.models import FinishedSpan


@asynccontextmanager
async def service_lifespan(app: FastAPI):
    # One client per process lifecycle, never one per business request.
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
        app.state.http_client = client
        yield


def create_service_app(
    title: str,
    service_name: str,
    on_finish: Callable[[FinishedSpan], None] | None,
) -> FastAPI:
    app = FastAPI(title=title, lifespan=service_lifespan)
    app.state.tracer = Tracer(service_name, on_finish)
    app.add_middleware(TracingMiddleware, tracer=app.state.tracer)
    return app
