import asyncio
from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from microtrace_sdk import get_current_span
from microtrace_sdk.models import FinishedSpan
from services.payment.schemas import ChargeRequest
from services.runtime import create_service_app


def create_app(on_finish: Callable[[FinishedSpan], None] | None = None) -> FastAPI:
    app = create_service_app("MicroTrace Payment Service", "payment-service", on_finish)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/charge")
    async def charge(request: ChargeRequest):
        if request.scenario != "normal":
            raise HTTPException(501, "Fault scenarios are implemented in M5")
        get_current_span().set_attribute("order.id", request.order_id)
        with app.state.tracer.start_span("process-payment") as processing:
            processing.set_attribute("order.id", request.order_id)
            processing.set_attribute("demo.scenario", request.scenario)
            await asyncio.sleep(0.02)
        return {"order_id": request.order_id, "status": "charged"}

    return app


app = create_app()
