import random
import time
from contextlib import ExitStack

import httpx
import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import OperationalError

from services.notification.main import create_app as notification_app
from services.order.main import create_app as order_app
from services.payment.main import create_app as payment_app
from services.trace_backend.db_models import spans
from tests.integration.test_propagation import serve
from tests.trace_fixtures import TRACE_ID, healthy, row

pytestmark = pytest.mark.integration


def test_trace_list_snapshot_is_consistent_when_error_arrives_between_queries(collector, db_engine):
    assert submit(collector, row(1)).status_code == 201
    inserted = False

    def late_error(connection, cursor, statement, parameters, context, executemany):
        nonlocal inserted
        if not inserted and "GROUP BY spans.trace_id" in statement:
            inserted = True
            with db_engine.begin() as writer:
                writer.execute(spans.insert().values(**row(2, 1, status="ERROR")))

    event.listen(db_engine, "after_cursor_execute", late_error)
    try:
        first = collector.get("/api/v1/traces?status=OK").json()["items"]
    finally:
        event.remove(db_engine, "after_cursor_execute", late_error)
    assert inserted and len(first) == 1
    assert first[0]["status"] == "OK" and first[0]["span_count"] == 1
    assert collector.get("/api/v1/traces?status=OK").json()["items"] == []
    updated = collector.get("/api/v1/traces?status=ERROR").json()["items"]
    assert len(updated) == 1 and updated[0]["span_count"] == 2


def submit(client, value):
    data = {
        **value,
        "start_time": value["start_time"].isoformat(),
        "end_time": value["end_time"].isoformat(),
    }
    return client.post("/api/v1/spans", json=data)


@pytest.fixture
def seeded(collector):
    for i in range(1, 6):
        trace = f"{i:032x}"
        if i == 5:
            entries = [
                row(
                    2,
                    999,
                    trace_id=trace,
                    service="payment-service",
                    start_ms=50,
                    duration_us=700000,
                )
            ]
        else:
            entries = [
                row(
                    1,
                    trace_id=trace,
                    kind="SERVER",
                    operation=f"root-{i}",
                    start_ms=i * 10,
                    duration_us=1000 if i == 1 else (500000 if i == 2 else 600000),
                ),
                row(
                    2,
                    1,
                    trace_id=trace,
                    service="notification-service" if i == 3 else "payment-service",
                    start_ms=i * 10 + 1,
                    status="OK" if i == 2 else "ERROR",
                ),
            ]
        for entry in entries:
            assert submit(collector, entry).status_code == 201
    return collector


def test_recent_order_defaults_pagination_and_services(seeded):
    response = seeded.get("/api/v1/traces")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 50 and data["offset"] == 0
    assert [s["trace_id"] for s in data["items"]] == [f"{i:032x}" for i in (5, 4, 3, 2, 1)]
    page = seeded.get("/api/v1/traces?limit=2&offset=2").json()
    assert [s["trace_id"] for s in page["items"]] == [f"{i:032x}" for i in (3, 2)]
    assert seeded.get("/api/v1/traces?offset=5").json()["items"] == []
    assert seeded.get("/api/v1/services").json() == {
        "services": ["notification-service", "order-service", "payment-service"]
    }
    orphan = data["items"][0]
    assert orphan["incomplete"] and orphan["status"] == "OK" and orphan["duration_us"] == 700000


@pytest.mark.parametrize(
    "params,expected",
    [
        ({"service": "payment-service"}, [5, 4, 2, 1]),
        ({"service": "notification-service"}, [3]),
        ({"status": "ERROR"}, [4, 3, 1]),
        ({"status": "OK"}, [5, 2]),
        ({"min_duration_ms": 600}, [5, 4, 3]),
        ({"service": "payment-service", "status": "ERROR", "min_duration_ms": 500}, [4]),
        (
            {
                "service": "payment-service",
                "status": "OK",
                "min_duration_ms": 500,
                "limit": 1,
                "offset": 1,
            },
            [2],
        ),
        ({"service": "missing"}, []),
    ],
)
def test_filters_apply_to_whole_trace_and_combine_with_and_before_paging(seeded, params, expected):
    response = seeded.get("/api/v1/traces", params=params)
    assert response.status_code == 200
    assert [s["trace_id"] for s in response.json()["items"]] == [f"{i:032x}" for i in expected]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 101},
        {"limit": 0},
        {"offset": -1},
        {"status": "bad"},
        {"min_duration_ms": -1},
        {"min_duration_ms": "bad"},
        {"min_duration_ms": 2**63},
        {"service": "x" * 101},
    ],
)
def test_invalid_queries_are_rejected(collector, params):
    assert collector.get("/api/v1/traces", params=params).status_code == 422


@pytest.mark.parametrize("value", ["bad\x00name", "\x00", "服务\x00名称"])
def test_nul_service_filter_rejected_before_database_access(
    collector, db_engine, monkeypatch, value
):
    attempts = []

    def unexpected_connection(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Invalid service filter must not access the database")

    with monkeypatch.context() as patch:
        patch.setattr(db_engine, "connect", unexpected_connection)
        response = collector.get("/api/v1/traces", params={"service": value})
    assert attempts == []
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid service filter"}
    assert collector.get("/health").json() == {"status": "ok"}
    assert collector.get("/api/v1/traces").status_code == 200


def test_valid_unicode_service_filter_matches_persisted_span(collector):
    name = "付款服务-é-🚀"
    assert submit(collector, row(1, service=name)).status_code == 201
    response = collector.get("/api/v1/traces", params={"service": name})
    assert response.status_code == 200
    assert [item["trace_id"] for item in response.json()["items"]] == [TRACE_ID]
    assert response.json()["items"][0]["services"] == [name]


def test_unknown_invalid_trace_and_empty_data(collector):
    assert collector.get("/api/v1/traces/" + TRACE_ID).status_code == 404
    assert collector.get("/api/v1/traces/invalid").status_code == 422
    assert collector.get("/api/v1/traces").json() == {"items": [], "limit": 50, "offset": 0}
    assert collector.get("/api/v1/services").json() == {"services": []}


def test_child_before_parent_orphan_subtree_and_late_parent(collector):
    rows = healthy()
    for entry in rows[3:5]:
        assert submit(collector, entry).status_code == 201
    partial = collector.get("/api/v1/traces/" + TRACE_ID).json()
    assert (
        partial["trace"]["incomplete"] and partial["trace"]["root_operation"] == "incomplete trace"
    )
    assert partial["orphan_span_ids"] == [rows[3]["span_id"]]
    assert [s["depth"] for s in partial["spans"]] == [0, 1]
    for entry in rows[:3] + rows[5:]:
        assert submit(collector, entry).status_code == 201
    complete = collector.get("/api/v1/traces/" + TRACE_ID).json()
    assert not complete["trace"]["incomplete"]
    assert complete["orphan_span_ids"] == []
    assert [s["depth"] for s in complete["spans"]] == [0, 1, 1, 2, 3, 1, 2, 3]


def test_randomized_persisted_order_returns_identical_detail(collector):
    canonical = None
    for seed in range(5):
        rows = healthy()
        trace = f"{seed + 100:032x}"
        random.Random(seed).shuffle(rows)
        for entry in rows:
            assert submit(collector, {**entry, "trace_id": trace}).status_code == 201
        detail = collector.get("/api/v1/traces/" + trace).json()
        detail["trace"]["trace_id"] = TRACE_ID
        for span in detail["spans"]:
            span["trace_id"] = TRACE_ID
        if canonical is None:
            canonical = detail
        assert detail == canonical


def test_cycles_and_multiple_roots_are_safe_and_summary_filters_match(collector):
    entries = [
        row(1, 2),
        row(2, 1),
        row(3, trace_id="b" * 32, start_ms=10),
        row(4, trace_id="b" * 32, start_ms=20),
    ]
    for entry in entries:
        assert submit(collector, entry).status_code == 201
    cycle = collector.get("/api/v1/traces/" + TRACE_ID).json()
    assert cycle["trace"]["incomplete"] and len(cycle["spans"]) == 2
    multi = collector.get("/api/v1/traces/" + "b" * 32).json()
    assert multi["trace"]["incomplete"] and multi["trace"]["duration_us"] == 11000
    assert [
        s["trace_id"] for s in collector.get("/api/v1/traces?min_duration_ms=10").json()["items"]
    ] == ["b" * 32]


def test_root_monotonic_duration_controls_sql_filter_even_with_skew(collector):
    root, child = row(1, duration_us=1000), row(2, 1, start_ms=-10, duration_us=50000)
    for entry in [child, root]:
        assert submit(collector, entry).status_code == 201
    detail = collector.get("/api/v1/traces/" + TRACE_ID).json()
    assert detail["trace"]["duration_us"] == 1000
    assert [s["start_offset_us"] for s in detail["spans"]] == [10000, 0]
    assert collector.get("/api/v1/traces?min_duration_ms=2").json()["items"] == []


def test_query_database_failures_are_sanitized(collector, db_engine, monkeypatch):
    def failed(*args, **kwargs):
        raise OperationalError("private sql", {}, Exception("private password"))

    monkeypatch.setattr(db_engine, "connect", failed)
    for path in ["/api/v1/traces", "/api/v1/traces/" + TRACE_ID, "/api/v1/services"]:
        response = collector.get(path)
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}


def test_gate_c_real_http_export_storage_queries_and_exact_tree(
    collector_app, db_engine, monkeypatch
):
    with ExitStack() as stack:
        backend_url = stack.enter_context(serve(collector_app))
        monkeypatch.setenv("COLLECTOR_URL", backend_url + "/api/v1/spans")
        payment_url = stack.enter_context(serve(payment_app()))
        notification_url = stack.enter_context(serve(notification_app()))
        order_url = stack.enter_context(
            serve(order_app(payment_url=payment_url, notification_url=notification_url))
        )
        response = httpx.post(order_url + "/orders", json={}, timeout=5)
        assert response.status_code == 200
        trace = response.json()["trace_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            detail = httpx.get(backend_url + "/api/v1/traces/" + trace, timeout=5).json()
            if detail.get("trace", {}).get("span_count") == 8:
                break
            time.sleep(0.01)
        assert detail["trace"]["span_count"] == 8 and not detail["trace"]["incomplete"]
        assert detail["trace"]["status"] == "OK"
        by_op = {(s["service_name"], s["operation_name"]): s for s in detail["spans"]}
        root = by_op[("order-service", "POST /orders")]
        assert root["parent_span_id"] is None
        assert [s["depth"] for s in detail["spans"]] == [0, 1, 1, 2, 3, 1, 2, 3]
        for service, path, internal in [
            ("payment-service", "/charge", "process-payment"),
            ("notification-service", "/notify", "send-notification"),
        ]:
            client = by_op[("order-service", f"POST {service} {path}")]
            server = by_op[(service, f"POST {path}")]
            assert client["span_kind"] == "CLIENT" and client["parent_span_id"] == root["span_id"]
            assert server["span_kind"] == "SERVER" and server["parent_span_id"] == client["span_id"]
            assert by_op[(service, internal)]["parent_span_id"] == server["span_id"]
        assert by_op[("order-service", "validate-order")]["parent_span_id"] == root["span_id"]
        assert {s["trace_id"] for s in detail["spans"]} == {trace}
        assert len({s["span_id"] for s in detail["spans"]}) == 8
        listing = httpx.get(
            backend_url + "/api/v1/traces",
            params={"service": "payment-service", "status": "OK", "min_duration_ms": 0},
            timeout=5,
        ).json()
        assert [item["trace_id"] for item in listing["items"]] == [trace]
        for span in detail["spans"]:
            data = {
                k: v for k, v in span.items() if k not in ("depth", "is_orphan", "start_offset_us")
            }
            duplicate = httpx.post(backend_url + "/api/v1/spans", json=data, timeout=5)
            assert duplicate.status_code == 200 and duplicate.json() == {"status": "duplicate"}
        assert httpx.get(backend_url + "/api/v1/traces/" + trace, timeout=5).json() == detail
        with db_engine.connect() as connection:
            assert len(connection.execute(select(spans)).all()) == 8
            assert inspect(connection).get_table_names() == ["spans"]
            assert inspect(connection).get_foreign_keys("spans") == []
