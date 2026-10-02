import asyncio
from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from microtrace_sdk import get_current_span
from microtrace_sdk.models import FinishedSpan
from services.payment.schemas import ChargeRequest
from services.runtime import create_service_app


class InjectedPaymentError(Exception):
    """Deterministic request-scoped demo failure."""


def create_app(on_finish: Callable[[FinishedSpan], None] | None = None) -> FastAPI:
    app = create_service_app("MicroTrace Payment Service", "payment-service", on_finish)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/charge")
    async def charge(request: ChargeRequest):
        get_current_span().set_attribute("order.id", request.order_id)
        try:
            with app.state.tracer.start_span("process-payment") as processing:
                processing.set_attribute("order.id", request.order_id)
                processing.set_attribute("demo.scenario", request.scenario)
                if request.scenario == "payment_error":
                    raise InjectedPaymentError()
                await asyncio.sleep(
                    request.slow_ms / 1000 if request.scenario == "slow_payment" else 0.02
                )
        except InjectedPaymentError:
            raise HTTPException(500, "Injected payment failure (demo)") from None
        return {"order_id": request.order_id, "status": "charged"}

    return app


app = create_app()
