"""M5 real HTTP, export, PostgreSQL and query scenario regressions."""

import asyncio
import time
from contextlib import ExitStack

import httpx
import pytest
from fastapi import FastAPI

from services.notification.main import create_app as notification_app
from services.order.main import create_app as order_app
from services.payment.main import create_app as payment_app
from tests.integration.test_propagation import serve

pytestmark = pytest.mark.integration


@pytest.fixture
def platform(collector_app, monkeypatch):
    with ExitStack() as stack:
        backend = stack.enter_context(serve(collector_app))
        monkeypatch.setenv("COLLECTOR_URL", backend + "/api/v1/spans")
        payment = stack.enter_context(serve(payment_app()))
        notification = stack.enter_context(serve(notification_app()))
        order = stack.enter_context(
            serve(order_app(payment_url=payment, notification_url=notification))
        )
        yield order, backend


def detail(client, backend, trace_id, count):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(backend + "/api/v1/traces/" + trace_id)
        value = response.json()
        if response.status_code == 200 and value["trace"]["span_count"] == count:
            return value
        time.sleep(0.01)
    raise AssertionError("Expected scenario telemetry did not arrive")


def assert_scenario(value, scenario, slow_ms=250):
    entries = value["spans"]
    by_op = {(s["service_name"], s["operation_name"]): s for s in entries}
    root = by_op["order-service", "POST /orders"]
    client = by_op["order-service", "POST payment-service /charge"]
    server = by_op["payment-service", "POST /charge"]
    internal = by_op["payment-service", "process-payment"]
    assert server["parent_span_id"] == client["span_id"]
    assert internal["parent_span_id"] == server["span_id"]
    assert client["parent_span_id"] == root["span_id"]
    assert len({s["trace_id"] for s in entries}) == 1
    assert len({s["span_id"] for s in entries}) == len(entries)
    assert not value["trace"]["incomplete"]
    assert "slow" not in value["trace"]
    if scenario == "payment_error":
        assert len(entries) == 5 and value["trace"]["status"] == "ERROR"
        assert all(s["service_name"] != "notification-service" for s in entries)
        assert all(s["status"] == "ERROR" for s in (root, client, server, internal))
        assert internal["error_type"] == "InjectedPaymentError"
        assert by_op["order-service", "validate-order"]["status"] == "OK"
    else:
        assert len(entries) == 8 and all(s["status"] == "OK" for s in entries)
        notification = by_op["notification-service", "POST /notify"]
        assert (
            notification["parent_span_id"]
            == by_op["order-service", "POST notification-service /notify"]["span_id"]
        )
        if scenario == "slow_payment":
            assert internal["duration_us"] >= (slow_ms - 5) * 1000
            assert (
                root["duration_us"]
                >= client["duration_us"]
                >= server["duration_us"]
                >= internal["duration_us"]
            )
    return root


@pytest.mark.parametrize("scenario", ["normal", "slow_payment", "payment_error"])
def test_real_persisted_scenarios(platform, scenario):
    order, backend = platform
    with httpx.Client(timeout=5) as client:
        response = client.post(order + "/orders", json={"scenario": scenario, "slow_ms": 250})
        assert response.status_code == (502 if scenario == "payment_error" else 200)
        trace_id = response.json()["trace_id"]
        value = detail(client, backend, trace_id, 5 if scenario == "payment_error" else 8)
        assert_scenario(value, scenario)


def test_mixed_concurrent_scenarios_remain_isolated(platform):
    order, backend = platform

    async def requests():
        async with httpx.AsyncClient(timeout=10) as client:

            async def request(i):
                scenario = ["normal", "slow_payment", "payment_error"][i % 3]
                response = await client.post(
                    order + "/orders", json={"scenario": scenario, "slow_ms": 150}
                )
                assert response.status_code == (502 if scenario == "payment_error" else 200)
                return response.json()["trace_id"], scenario

            return await asyncio.gather(*(request(i) for i in range(18)))

    results = asyncio.run(requests())
    assert len({trace for trace, _ in results}) == 18
    identities = set()
    roots = []
    with httpx.Client(timeout=5) as client:
        for trace, scenario in results:
            value = detail(client, backend, trace, 5 if scenario == "payment_error" else 8)
            roots.append(assert_scenario(value, scenario, 150))
            assert {s["trace_id"] for s in value["spans"]} == {trace}
            spans = {s["span_id"] for s in value["spans"]}
            assert not identities.intersection(spans)
            identities.update(spans)
    ordered = sorted(roots, key=lambda s: s["start_time"])
    assert ordered[1]["start_time"] < ordered[0]["end_time"]


@pytest.mark.parametrize(
    "scenario,delay", [("slow_payment", 99), ("slow_payment", 3001), ("unapproved", 800)]
)
def test_scenario_validation(platform, scenario, delay):
    with httpx.Client(timeout=5) as client:
        assert (
            client.post(
                platform[0] + "/orders", json={"scenario": scenario, "slow_ms": delay}
            ).status_code
            == 422
        )


def test_slow_collector_and_saturated_queues_do_not_block_business(monkeypatch, caplog):
    slow = FastAPI()

    @slow.post("/api/v1/spans")
    async def collect():
        await asyncio.sleep(0.3)
        return {"status": "stored"}

    with ExitStack() as stack:
        backend = stack.enter_context(serve(slow))
        monkeypatch.setenv("COLLECTOR_URL", backend + "/api/v1/spans")
        monkeypatch.setenv("EXPORT_QUEUE_SIZE", "1")
        monkeypatch.setenv("EXPORT_TIMEOUT_SECONDS", "0.03")
        p, n = payment_app(), notification_app()
        payment = stack.enter_context(serve(p))
        notification = stack.enter_context(serve(n))
        o = order_app(payment_url=payment, notification_url=notification)
        order = stack.enter_context(serve(o))

        async def requests():
            async with httpx.AsyncClient(timeout=5) as client:
                started = time.monotonic()
                responses = await asyncio.gather(
                    *(client.post(order + "/orders", json={}) for _ in range(6))
                )
                assert time.monotonic() - started < 1.5
                assert all(r.status_code == 200 for r in responses)

        asyncio.run(requests())
        assert all(app.state.exporter.queue.maxsize == 1 for app in (o, p, n))
    assert sum(app.state.exporter.dropped for app in (o, p, n)) == 48
    assert all(app.state.exporter.worker.done() for app in (o, p, n))
    assert "private" not in caplog.text
