"""Gate B uses real loopback TCP, Uvicorn, application lifespans and HTTPX."""

import asyncio
import socket
import threading
import time
from contextlib import ExitStack, contextmanager

import httpx
import pytest
import uvicorn

from microtrace_sdk import SpanKind, SpanStatus, Tracer, get_current_span
from microtrace_sdk.http_client import traced_request
from microtrace_sdk.ids import new_span_id, new_trace_id
from services.notification.main import create_app as notification_app
from services.order.main import create_app as order_app
from services.payment.main import create_app as payment_app
from services.runtime import create_service_app


class RecordingSink:
    """Bounded test-only in-memory hook. Production apps never retain this list."""

    def __init__(self):
        self.spans = []
        self.lock = threading.Lock()

    def __call__(self, span):
        with self.lock:
            if len(self.spans) >= 1000:
                raise RuntimeError("Test capture limit reached")
            self.spans.append(span)

    def trace(self, trace_id, count=8):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self.lock:
                found = [span for span in self.spans if span.trace_id == trace_id]
            if len(found) >= count:
                return found
            time.sleep(0.005)
        raise AssertionError(f"Expected {count} completed spans, got {len(found)}")


@contextmanager
def serve(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, lifespan="on")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() >= deadline:
                raise AssertionError("Test HTTP server failed to start")
            time.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive(), "Test HTTP server did not stop"


@pytest.fixture
def live_services():
    sink = RecordingSink()
    payment = payment_app(sink)
    notification = notification_app(sink)
    with ExitStack() as stack:
        payment_url = stack.enter_context(serve(payment))
        notification_url = stack.enter_context(serve(notification))
        order = order_app(sink, payment_url=payment_url, notification_url=notification_url)
        order_url = stack.enter_context(serve(order))
        yield sink, order_url, payment_url, notification_url, (order, payment, notification)
    for app in (order, payment, notification):
        assert app.state.http_client.is_closed


def assert_expected_tree(spans, trace_id, root_parent=None):
    expected = {
        ("order-service", "POST /orders"): (SpanKind.SERVER, None),
        ("order-service", "validate-order"): (SpanKind.INTERNAL, ("order-service", "POST /orders")),
        ("order-service", "POST payment-service /charge"): (
            SpanKind.CLIENT,
            ("order-service", "POST /orders"),
        ),
        ("payment-service", "POST /charge"): (
            SpanKind.SERVER,
            ("order-service", "POST payment-service /charge"),
        ),
        ("payment-service", "process-payment"): (
            SpanKind.INTERNAL,
            ("payment-service", "POST /charge"),
        ),
        ("order-service", "POST notification-service /notify"): (
            SpanKind.CLIENT,
            ("order-service", "POST /orders"),
        ),
        ("notification-service", "POST /notify"): (
            SpanKind.SERVER,
            ("order-service", "POST notification-service /notify"),
        ),
        ("notification-service", "send-notification"): (
            SpanKind.INTERNAL,
            ("notification-service", "POST /notify"),
        ),
    }
    by_operation = {(s.service_name, s.operation_name): s for s in spans}
    assert len(spans) == len(by_operation) == len(expected) == 8
    assert set(by_operation) == set(expected)
    assert {s.trace_id for s in spans} == {trace_id}
    assert len({s.span_id for s in spans}) == 8
    for key, (kind, parent_key) in expected.items():
        span = by_operation[key]
        assert span.span_kind == kind
        assert span.status == SpanStatus.OK
        assert span.duration_us >= 0
        assert span.end_time >= span.start_time
        assert span.parent_span_id == (
            by_operation[parent_key].span_id if parent_key is not None else root_parent
        )
    # Keep the two cross-service requirements explicit, in addition to the entire tree.
    assert (
        by_operation[("payment-service", "POST /charge")].parent_span_id
        == by_operation[("order-service", "POST payment-service /charge")].span_id
    )
    assert (
        by_operation[("notification-service", "POST /notify")].parent_span_id
        == by_operation[("order-service", "POST notification-service /notify")].span_id
    )
    root = by_operation[("order-service", "POST /orders")]
    for span in spans:
        if "order.id" in span.attributes:
            assert span.attributes["order.id"] == root.attributes["order.id"]
    return root


def test_real_http_canonical_tree_and_client_server_parents(live_services):
    sink, url, _, _, _ = live_services
    response = httpx.post(url + "/orders", json={"item": "demo-item"}, timeout=5)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert_expected_tree(sink.trace(response.json()["trace_id"]), response.json()["trace_id"])
    assert get_current_span() is None


def test_sequential_requests_have_independent_ids_and_reuse_lifecycle_client(live_services):
    sink, url, _, _, apps = live_services
    original_clients = [app.state.http_client for app in apps]
    trace_ids = []
    for _ in range(2):
        response = httpx.post(url + "/orders", json={}, timeout=5)
        assert response.status_code == 200
        trace_id = response.json()["trace_id"]
        assert_expected_tree(sink.trace(trace_id), trace_id)
        trace_ids.append(trace_id)
        assert [app.state.http_client for app in apps] == original_clients
        assert all(not client.is_closed for client in original_clients)
    assert len(set(trace_ids)) == 2


@pytest.mark.parametrize("flags", ["00", "01", "ab"])
def test_valid_incoming_traceparent_continues_real_http_trace(live_services, flags):
    sink, url, _, _, _ = live_services
    trace_id, parent_id = new_trace_id(), new_span_id()
    response = httpx.post(
        url + "/orders",
        json={},
        headers={"traceparent": f"00-{trace_id}-{parent_id}-{flags}"},
        timeout=5,
    )
    assert response.status_code == 200
    assert response.json()["trace_id"] == trace_id
    assert_expected_tree(sink.trace(trace_id), trace_id, root_parent=parent_id)


@pytest.mark.parametrize("header", ["malformed", "00-" + "0" * 32 + "-" + "1" * 16 + "-01"])
def test_invalid_context_does_not_fail_business_request(live_services, header):
    sink, url, _, _, _ = live_services
    response = httpx.post(url + "/orders", json={}, headers={"traceparent": header}, timeout=5)
    assert response.status_code == 200
    trace_id = response.json()["trace_id"]
    assert_expected_tree(sink.trace(trace_id), trace_id)


def test_duplicate_traceparent_starts_new_trace_safely(live_services):
    sink, url, _, _, _ = live_services
    incoming = new_trace_id()
    header = f"00-{incoming}-{new_span_id()}-01"
    response = httpx.post(
        url + "/orders",
        json={},
        headers=[("traceparent", header), ("traceparent", header)],
        timeout=5,
    )
    assert response.status_code == 200
    trace_id = response.json()["trace_id"]
    assert trace_id != incoming
    assert_expected_tree(sink.trace(trace_id), trace_id)


def test_concurrent_real_http_requests_never_cross_trace_or_parent_context(live_services):
    sink, url, _, _, _ = live_services

    async def run_requests():
        async with httpx.AsyncClient(timeout=10) as client:

            async def request(index):
                trace_id, parent_id = new_trace_id(), new_span_id()
                header = f"00-{trace_id}-{parent_id}-01" if index % 3 == 0 else "malformed"
                headers = {"traceparent": header} if index % 3 != 2 else {}
                response = await client.post(url + "/orders", json={}, headers=headers)
                assert response.status_code == 200
                if index % 3 == 0:
                    assert response.json()["trace_id"] == trace_id
                return response.json()["trace_id"], parent_id if index % 3 == 0 else None

            return await asyncio.gather(*(request(index) for index in range(25)))

    identities = asyncio.run(run_requests())
    assert len({trace_id for trace_id, _ in identities}) == 25
    roots = [
        assert_expected_tree(sink.trace(trace_id), trace_id, parent_id)
        for trace_id, parent_id in identities
    ]
    all_spans = [span for trace_id, _ in identities for span in sink.trace(trace_id)]
    assert len(all_spans) == len({span.span_id for span in all_spans}) == 200
    ordered_roots = sorted(roots, key=lambda span: span.start_time)
    assert ordered_roots[1].start_time < ordered_roots[0].end_time, "Requests must overlap"
    assert get_current_span() is None


def test_health_endpoints_emit_no_spans(live_services):
    sink, order, payment, notification, _ = live_services
    for url in (order, payment, notification):
        assert httpx.get(url + "/health?readiness=1", timeout=5).json() == {"status": "ok"}
    assert sink.spans == []


def test_outbound_header_overrides_caller_and_uses_client_as_parent(live_services):
    sink, _, payment_url, _, _ = live_services

    async def request():
        tracer = Tracer("order-service", sink)
        with tracer.start_span("test-root", SpanKind.SERVER, parent=None) as root:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await traced_request(
                    client,
                    tracer,
                    "POST",
                    payment_url + "/charge",
                    peer_service="payment-service",
                    route="/charge",
                    json={"order_id": "ord_test"},
                    headers={"TraceParent": f"00-{new_trace_id()}-{new_span_id()}-01"},
                )
                assert response.status_code == 200
                assert get_current_span() is root
            return root.context.trace_id

    trace_id = asyncio.run(request())
    spans = sink.trace(trace_id, count=4)
    caller = next(s for s in spans if s.span_kind == SpanKind.CLIENT)
    server = next(
        s for s in spans if s.service_name == "payment-service" and s.span_kind == "SERVER"
    )
    assert server.trace_id == caller.trace_id == trace_id
    assert server.parent_span_id == caller.span_id
    assert get_current_span() is None


def test_route_template_and_privacy_do_not_capture_raw_path_body_or_headers(live_services):
    sink, _, _, notification_url, apps = live_services

    @apps[2].get("/items/{item_id}")
    async def item(item_id: str):
        return {"status": "ok"}

    response = httpx.get(
        notification_url + "/items/private-demo-id",
        headers={"Authorization": "Bearer private-demo-value", "Cookie": "private-demo-cookie"},
        timeout=5,
    )
    assert response.status_code == 200
    deadline = time.monotonic() + 5
    while not sink.spans and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(sink.spans) == 1
    span = sink.spans[0]
    assert span.operation_name == "GET /items/{item_id}"
    assert span.attributes["http.route"] == "/items/{item_id}"
    assert "private-demo" not in span.model_dump_json()


def test_order_body_and_sensitive_headers_never_enter_telemetry(live_services):
    sink, url, _, _, _ = live_services
    response = httpx.post(
        url + "/orders",
        json={"item": "private-demo-body"},
        headers={"Authorization": "Bearer private-demo-value", "Cookie": "private-demo-cookie"},
        timeout=5,
    )
    assert response.status_code == 200
    trace_id = response.json()["trace_id"]
    spans = sink.trace(trace_id)
    assert_expected_tree(spans, trace_id)
    assert all("private-demo" not in span.model_dump_json() for span in spans)


def test_normal_request_ignores_unused_delay(live_services):
    sink, url, _, _, _ = live_services
    response = httpx.post(url + "/orders", json={"scenario": "normal", "slow_ms": 0}, timeout=5)
    assert response.status_code == 200
    trace_id = response.json()["trace_id"]
    assert_expected_tree(sink.trace(trace_id), trace_id)


def test_notification_is_not_called_after_downstream_payment_failure():
    from fastapi.responses import JSONResponse

    sink = RecordingSink()
    payment = create_service_app("Payment test double", "payment-service", sink)

    @payment.post("/charge")
    async def failed_payment():
        return JSONResponse({"detail": "Controlled downstream failure"}, status_code=503)

    with ExitStack() as stack:
        payment_url = stack.enter_context(serve(payment))
        notification_url = stack.enter_context(serve(notification_app(sink)))
        order_url = stack.enter_context(
            serve(order_app(sink, payment_url=payment_url, notification_url=notification_url))
        )
        response = httpx.post(order_url + "/orders", json={}, timeout=5)
        assert response.status_code == 502
        assert response.json()["status"] == "payment_failed"
        spans = sink.trace(response.json()["trace_id"], count=4)
        assert len(spans) == 4
        assert {s.service_name for s in spans} == {"order-service", "payment-service"}
        failed = [s for s in spans if s.operation_name != "validate-order"]
        assert len(failed) == 3
        assert all(s.status == SpanStatus.ERROR for s in failed)
