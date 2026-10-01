import asyncio
from collections.abc import Callable

from fastapi import FastAPI

from microtrace_sdk import get_current_span
from microtrace_sdk.models import FinishedSpan
from services.notification.schemas import NotifyRequest
from services.runtime import create_service_app


def create_app(on_finish: Callable[[FinishedSpan], None] | None = None) -> FastAPI:
    app = create_service_app("MicroTrace Notification Service", "notification-service", on_finish)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/notify")
    async def notify(request: NotifyRequest):
        get_current_span().set_attribute("order.id", request.order_id)
        with app.state.tracer.start_span("send-notification") as sending:
            sending.set_attribute("order.id", request.order_id)
            await asyncio.sleep(0.01)
        return {"order_id": request.order_id, "status": "sent"}

    return app


app = create_app()
