import asyncio
import json
import time

import httpx
import pytest

from microtrace_sdk import Tracer, get_current_span
from microtrace_sdk.exporter import SpanExporter


def finished():
    with Tracer("order-service").start_span("operation") as span:
        span.set_attribute("order.id", "ord_test")
    return span.finish()


def test_completed_span_enqueued_once_and_exported_as_json_without_request_context():
    async def exercise():
        bodies = []

        async def handler(request):
            assert get_current_span() is None
            bodies.append(request.content)
            return httpx.Response(201)

        exporter = SpanExporter("http://collector/api/v1/spans")
        assert exporter.queue.maxsize == 256 and exporter.timeout == 1
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with Tracer("service").start_span("ambient"):
                exporter.start(client)
                with Tracer("order-service", exporter.enqueue).start_span("operation") as span:
                    span.set_attribute("order.id", "ord_test")
                    span.finish()
                    span.finish()
            await exporter.close()
        assert len(bodies) == 1
        assert json.loads(bodies[0]) == span.finish().model_dump(mode="json")
        assert exporter.dropped == 0
        assert exporter.worker.done()

    asyncio.run(exercise())


@pytest.mark.parametrize("outcome", [400, 422, 500, "connection", "slow"])
def test_failed_delivery_dropped_once_without_retry_and_safe_warning(outcome, caplog):
    async def exercise():
        calls = []

        async def handler(request):
            calls.append(request)
            if outcome == "connection":
                raise httpx.ConnectError("private credentials")
            if outcome == "slow":
                await asyncio.Event().wait()
            return httpx.Response(outcome)

        exporter = SpanExporter("http://collector/private", timeout=0.03)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            exporter.start(client)
            exporter.enqueue(finished())
            await asyncio.wait_for(exporter.queue.join(), timeout=0.5)
            await exporter.close()
        assert len(calls) == 1 and exporter.dropped == 1
        assert "private" not in caplog.text

    asyncio.run(exercise())


def test_queue_full_drops_newest_immediately_with_controlled_warning(caplog):
    async def exercise():
        exporter = SpanExporter("http://collector", capacity=2)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(201))
        ) as client:
            exporter.start(client)
            oldest = [finished(), finished()]
            newest = [finished() for _ in range(100)]

            def identities(values):
                return [(s.trace_id, s.span_id) for s in values]

            assert len(set(identities(oldest + newest))) == 102
            for span in oldest:
                exporter.enqueue(span)
            start = time.monotonic()
            for span in newest:
                exporter.enqueue(span)
            assert time.monotonic() - start < 0.1
            assert exporter.queue.qsize() == 2
            retained = [exporter.queue.get_nowait(), exporter.queue.get_nowait()]
            assert identities(retained) == identities(oldest)
            for _ in retained:
                exporter.queue.task_done()
            assert exporter.dropped == 100
            await exporter.close()
        assert len(caplog.records) == 1

    asyncio.run(exercise())


def test_shutdown_drain_is_bounded_and_client_remains_owned_by_lifespan():
    async def exercise():
        entered = asyncio.Event()

        async def handler(_):
            entered.set()
            await asyncio.Event().wait()

        exporter = SpanExporter("http://collector", capacity=2, timeout=10)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            exporter.start(client)
            exporter.enqueue(finished())
            await entered.wait()
            exporter.enqueue(finished())
            start = time.monotonic()
            await exporter.close(drain_timeout=0.03)
            assert time.monotonic() - start < 0.5
            assert exporter.worker.done() and exporter.queue.empty()
            assert exporter.dropped == 2
            assert not client.is_closed
            exporter.enqueue(finished())
            assert exporter.dropped == 3

    asyncio.run(exercise())


@pytest.mark.parametrize("capacity,timeout", [(0, 1), (-1, 1), (1, 0), (1, float("inf"))])
def test_invalid_export_configuration_rejected(capacity, timeout):
    with pytest.raises(ValueError):
        SpanExporter("http://collector", capacity, timeout)
