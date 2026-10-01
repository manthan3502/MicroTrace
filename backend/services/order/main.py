import asyncio
import os
import secrets
from collections.abc import Callable

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from microtrace_sdk import get_current_span
from microtrace_sdk.http_client import traced_request
from microtrace_sdk.models import FinishedSpan
from services.order.schemas import OrderRequest
from services.runtime import create_service_app


def create_app(
    on_finish: Callable[[FinishedSpan], None] | None = None,
    *,
    payment_url: str | None = None,
    notification_url: str | None = None,
) -> FastAPI:
    app = create_service_app("MicroTrace Order Service", "order-service", on_finish)
    payment_url = payment_url or os.environ.get(
        "PAYMENT_SERVICE_URL", "http://payment-service:8000"
    )
    notification_url = notification_url or os.environ.get(
        "NOTIFICATION_SERVICE_URL", "http://notification-service:8000"
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/orders")
    async def place_order(order: OrderRequest):
        if order.scenario != "normal":
            raise HTTPException(501, "Fault scenarios are implemented in M5")
        tracer = app.state.tracer
        root = get_current_span()
        order_id = "ord_" + secrets.token_hex(8)
        root.set_attribute("order.id", order_id)
        root.set_attribute("demo.scenario", order.scenario)
        with tracer.start_span("validate-order") as validation:
            validation.set_attribute("order.id", order_id)
            await asyncio.sleep(0.01)
        payment_failed = False
        try:
            payment = await traced_request(
                app.state.http_client,
                tracer,
                "POST",
                payment_url.rstrip("/") + "/charge",
                peer_service="payment-service",
                route="/charge",
                json={"order_id": order_id, "scenario": order.scenario, "slow_ms": order.slow_ms},
            )
            payment_failed = not payment.is_success
        except httpx.HTTPError:
            payment_failed = True
        if payment_failed:
            return JSONResponse(
                {
                    "order_id": order_id,
                    "status": "payment_failed",
                    "trace_id": root.context.trace_id,
                    "message": "Payment service failed",
                },
                status_code=502,
            )
        try:
            notification = await traced_request(
                app.state.http_client,
                tracer,
                "POST",
                notification_url.rstrip("/") + "/notify",
                peer_service="notification-service",
                route="/notify",
                json={"order_id": order_id},
            )
            if not notification.is_success:
                raise HTTPException(502, "Notification service failed")
        except httpx.HTTPError:
            raise HTTPException(502, "Notification service failed") from None
        return {"order_id": order_id, "status": "completed", "trace_id": root.context.trace_id}

    return app


app = create_app()
