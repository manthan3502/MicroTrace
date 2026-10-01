import asyncio

import httpx
import pytest

from microtrace_sdk import SpanKind, SpanStatus, Tracer, get_current_span
from microtrace_sdk.http_client import traced_request
from microtrace_sdk.traceparent import parse_traceparent
from services.payment.main import create_app


@pytest.mark.parametrize("outcome", [200, 500, "timeout", "connection"])
def test_outbound_status_error_finish_and_context_restore(outcome):
    completed = []
    tracer = Tracer("order-service", completed.append)

    async def handler(request):
        active = get_current_span()
        assert active.kind == SpanKind.CLIENT
        context = parse_traceparent(request.headers["traceparent"])
        assert context == active.context
        if outcome == "timeout":
            raise httpx.ReadTimeout("private URL details", request=request)
        if outcome == "connection":
            raise httpx.ConnectError("private credentials", request=request)
        return httpx.Response(outcome)

    async def exercise():
        with tracer.start_span("root", SpanKind.SERVER) as root:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                if isinstance(outcome, str):
                    with pytest.raises(httpx.HTTPError):
                        await traced_request(
                            client,
                            tracer,
                            "POST",
                            "http://payment/charge",
                            peer_service="payment-service",
                            route="/charge",
                            json={},
                        )
                else:
                    response = await traced_request(
                        client,
                        tracer,
                        "POST",
                        "http://payment/charge",
                        peer_service="payment-service",
                        route="/charge",
                        json={},
                    )
                    assert response.status_code == outcome
                assert get_current_span() is root
        assert get_current_span() is None

    asyncio.run(exercise())
    assert len(completed) == 2
    child, root = completed
    assert child.parent_span_id == root.span_id
    assert child.trace_id == root.trace_id
    assert child.status == (SpanStatus.OK if outcome == 200 else SpanStatus.ERROR)
    assert "private" not in child.model_dump_json()


@pytest.mark.parametrize("raises", [False, True])
def test_server_failure_finishes_and_resets_context_without_sensitive_errors(raises):
    from fastapi.responses import JSONResponse

    completed = []
    app = create_app(completed.append)

    @app.get("/failure")
    async def failure():
        if raises:
            raise ValueError("private exception details")
        return JSONResponse({"detail": "controlled failure"}, status_code=500)

    async def exercise():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/failure")
        assert response.status_code == 500
        assert get_current_span() is None

    asyncio.run(exercise())
    assert len(completed) == 1
    failed = completed[0]
    assert failed.operation_name == "GET /failure"
    assert failed.span_kind == SpanKind.SERVER
    assert failed.status == SpanStatus.ERROR
    assert failed.attributes["http.status_code"] == 500
    assert "private" not in failed.model_dump_json()
