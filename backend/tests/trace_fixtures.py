from datetime import UTC, datetime, timedelta

TRACE_ID = "a" * 32
START = datetime(2026, 10, 2, tzinfo=UTC)


def row(
    identity,
    parent=None,
    *,
    trace_id=TRACE_ID,
    service="order-service",
    operation="operation",
    kind="INTERNAL",
    start_ms=0,
    duration_us=1000,
    status="OK",
):
    start = START + timedelta(milliseconds=start_ms)
    return {
        "trace_id": trace_id,
        "span_id": f"{identity:016x}",
        "parent_span_id": f"{parent:016x}" if parent is not None else None,
        "service_name": service,
        "operation_name": operation,
        "span_kind": kind,
        "start_time": start,
        "end_time": start + timedelta(microseconds=duration_us),
        "duration_us": duration_us,
        "status": status,
        "error_type": None,
        "error_message": None,
        "attributes": {},
    }


def healthy():
    return [
        row(1, operation="POST /orders", kind="SERVER", duration_us=10000),
        row(2, 1, operation="validate-order", start_ms=1),
        row(
            3,
            1,
            operation="POST payment-service /charge",
            kind="CLIENT",
            start_ms=2,
            duration_us=4000,
        ),
        row(
            4,
            3,
            service="payment-service",
            operation="POST /charge",
            kind="SERVER",
            start_ms=3,
            duration_us=2000,
        ),
        row(5, 4, service="payment-service", operation="process-payment", start_ms=4),
        row(
            6,
            1,
            operation="POST notification-service /notify",
            kind="CLIENT",
            start_ms=7,
            duration_us=2000,
        ),
        row(
            7,
            6,
            service="notification-service",
            operation="POST /notify",
            kind="SERVER",
            start_ms=8,
        ),
        row(
            8,
            7,
            service="notification-service",
            operation="send-notification",
            start_ms=8,
            duration_us=500,
        ),
    ]
