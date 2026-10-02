import time
from contextlib import ExitStack

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from microtrace_sdk import SpanKind, SpanStatus, Tracer
from microtrace_sdk.models import FinishedSpan
from services.notification.main import create_app as notification_app
from services.order.main import create_app as order_app
from services.payment.main import create_app as payment_app
from services.trace_backend.db_models import spans
from tests.integration.test_propagation import assert_expected_tree, serve


def payload():
    with Tracer("order-service").start_span("POST /orders", SpanKind.SERVER) as span:
        span.set_attribute("http.method", "POST")
    return span.finish().model_dump(mode="json")


def test_store_duplicate_does_not_overwrite_original(collector, db_engine):
    data = payload()
    assert collector.post("/api/v1/spans", json=data).status_code == 201
    response = collector.post("/api/v1/spans", json={**data, "operation_name": "changed"})
    assert response.status_code == 200 and response.json() == {"status": "duplicate"}
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(spans)) == 1
        assert connection.scalar(select(spans.c.operation_name)) == "POST /orders"


@pytest.mark.parametrize(
    "change",
    [
        {"trace_id": "0" * 32},
        {"trace_id": "G" * 32},
        {"span_id": "short"},
        {"parent_span_id": "0" * 16},
        {"span_kind": "PRODUCER"},
        {"status": "UNSET"},
        {"duration_us": -1},
        {"duration_us": 2**63},
        {"duration_us": 1.5},
        {"start_time": "2026-10-02T00:00:00"},
        {"end_time": "2000-01-01T00:00:00Z"},
        {"service_name": "x" * 101},
        {"operation_name": "x" * 201},
        {"error_type": "x" * 129},
        {"error_message": "x" * 513},
        {"attributes": {"order.id": "x" * 257}},
        {"attributes": {"order.id": {}}},
        {"attributes": {str(i): i for i in range(17)}},
        {"attributes": {"Authorization": "private"}},
        {"unexpected": "private"},
        {"attributes": []},
    ],
)
def test_invalid_telemetry_rejected_safely(collector, db_engine, change):
    response = collector.post("/api/v1/spans", json={**payload(), **change})
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid span payload"}
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(spans)) == 0


def test_request_size_malformed_json_and_content_type(collector):
    assert (
        collector.post(
            "/api/v1/spans", content="x" * 65537, headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
    assert (
        collector.post(
            "/api/v1/spans", content="{", headers={"content-type": "application/json"}
        ).status_code
        == 422
    )
    assert collector.post("/api/v1/spans", content="{}").status_code == 415


def test_child_before_parent_and_permanent_orphan_are_accepted(collector, db_engine):
    root = payload()
    child = {**root, "span_id": "1234567890abcdef", "parent_span_id": root["span_id"]}
    orphan = {**root, "span_id": "1234567890abcdee", "parent_span_id": "1234567890abcddd"}
    for data in (child, orphan, root):
        assert collector.post("/api/v1/spans", json=data).status_code == 201
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(spans)) == 3


def test_database_failure_is_sanitized(collector, monkeypatch):
    def failure(*_):
        raise OperationalError("private statement", {}, Exception("private password"))

    monkeypatch.setattr("services.trace_backend.ingest.store_span", failure)
    response = collector.post("/api/v1/spans", json=payload())
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def persisted_trace(engine, trace_id, count=8):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            rows = (
                connection.execute(select(spans).where(spans.c.trace_id == trace_id))
                .mappings()
                .all()
            )
        if len(rows) == count:
            return [
                FinishedSpan(
                    **{
                        **{k: v for k, v in row.items() if k != "created_at"},
                        "span_kind": SpanKind(row["span_kind"]),
                        "status": SpanStatus(row["status"]),
                    }
                )
                for row in rows
            ]
        time.sleep(0.01)
    raise AssertionError(f"Expected {count} persisted spans, got {len(rows)}")


def test_real_services_export_all_eight_spans_to_real_postgresql(
    collector_app, db_engine, monkeypatch
):
    with ExitStack() as stack:
        collector_url = stack.enter_context(serve(collector_app))
        monkeypatch.setenv("COLLECTOR_URL", collector_url + "/api/v1/spans")
        payment = payment_app()
        notification = notification_app()
        payment_url = stack.enter_context(serve(payment))
        notification_url = stack.enter_context(serve(notification))
        order = order_app(payment_url=payment_url, notification_url=notification_url)
        order_url = stack.enter_context(serve(order))
        response = httpx.post(order_url + "/orders", json={}, timeout=5)
        assert response.status_code == 200
        trace_id = response.json()["trace_id"]
        assert_expected_tree(persisted_trace(db_engine, trace_id), trace_id)
        for app in (order, payment, notification):
            assert app.state.exporter.queue.maxsize == 256
            assert not app.state.exporter.worker.done()
    assert all(app.state.exporter.worker.done() for app in (order, payment, notification))


def test_unavailable_collector_never_fails_real_business_flow(monkeypatch):
    monkeypatch.setenv("COLLECTOR_URL", "http://127.0.0.1:1/api/v1/spans")
    monkeypatch.setenv("EXPORT_TIMEOUT_SECONDS", "0.05")
    with ExitStack() as stack:
        payment, notification = payment_app(), notification_app()
        payment_url = stack.enter_context(serve(payment))
        notification_url = stack.enter_context(serve(notification))
        order = order_app(payment_url=payment_url, notification_url=notification_url)
        order_url = stack.enter_context(serve(order))
        response = httpx.post(order_url + "/orders", json={}, timeout=5)
        assert response.status_code == 200 and response.json()["status"] == "completed"
    assert sum(app.state.exporter.dropped for app in (order, payment, notification)) == 8


def test_concurrent_duplicate_ingestion_keeps_one_row(collector_app, db_engine):
    import concurrent.futures

    data = payload()
    with serve(collector_app) as url:

        def submit(_):
            return httpx.post(url + "/api/v1/spans", json=data, timeout=5).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            codes = list(pool.map(submit, range(8)))
    assert codes.count(201) == 1 and codes.count(200) == 7
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(spans)) == 1
