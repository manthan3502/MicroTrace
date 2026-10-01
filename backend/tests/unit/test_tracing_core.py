import asyncio
import re
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from microtrace_sdk import SpanContext, SpanKind, SpanStatus, Tracer, get_current_span, ids
from microtrace_sdk.models import FinishedSpan, validate_attributes
from microtrace_sdk.traceparent import format_traceparent, parse_traceparent

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"


@pytest.mark.parametrize("factory,length", [(ids.new_trace_id, 32), (ids.new_span_id, 16)])
def test_ids_are_lowercase_nonzero_unique(factory, length):
    sample = {factory() for _ in range(5000)}
    assert len(sample) == 5000
    assert all(re.fullmatch(rf"[0-9a-f]{{{length}}}", value) for value in sample)
    assert "0" * length not in sample


@pytest.mark.parametrize("factory,size", [(ids.new_trace_id, 16), (ids.new_span_id, 8)])
def test_all_zero_generated_id_is_regenerated(monkeypatch, factory, size):
    values = iter(["0" * (size * 2), "1" * (size * 2)])
    sizes = []

    def token_hex(byte_count):
        sizes.append(byte_count)
        return next(values)

    monkeypatch.setattr(ids.secrets, "token_hex", token_hex)
    assert factory() == "1" * (size * 2)
    assert sizes == [size, size]


@pytest.mark.parametrize("flags", ["00", "01", "ab", "ff"])
def test_traceparent_parse_format_preserves_identity_and_flags(flags):
    header = f"00-{TRACE_ID}-{SPAN_ID}-{flags}"
    context = parse_traceparent(header)
    assert context == SpanContext(TRACE_ID, SPAN_ID, flags)
    assert format_traceparent(context) == header


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "malformed",
        f"00-{TRACE_ID}-{SPAN_ID}",
        f"00-{TRACE_ID}-{SPAN_ID}-01-extra",
        f"00-{TRACE_ID[:-1]}-{SPAN_ID}-01",
        f"00-{TRACE_ID}-{SPAN_ID[:-1]}-01",
        f"00-{'g' * 32}-{SPAN_ID}-01",
        f"00-{TRACE_ID}-{'g' * 16}-01",
        f"00-{'0' * 32}-{SPAN_ID}-01",
        f"00-{TRACE_ID}-{'0' * 16}-01",
        f"01-{TRACE_ID}-{SPAN_ID}-01",
        f"ff-{TRACE_ID}-{SPAN_ID}-01",
        f"00-{TRACE_ID.upper()}-{SPAN_ID}-01",
        f"00-{TRACE_ID}-{SPAN_ID}-zz",
        f"00-{TRACE_ID}-{SPAN_ID}-1",
        f" 00-{TRACE_ID}-{SPAN_ID}-01",
    ],
)
def test_invalid_traceparent_is_missing_context(header):
    assert parse_traceparent(header) is None


def test_span_context_is_immutable_and_validated():
    context = SpanContext(TRACE_ID, SPAN_ID)
    with pytest.raises(FrozenInstanceError):
        context.trace_id = "1" * 32
    for args in [("0" * 32, SPAN_ID), (TRACE_ID, "0" * 16), (TRACE_ID, SPAN_ID, "gg")]:
        with pytest.raises(ValueError):
            SpanContext(*args)


@pytest.mark.parametrize("kind", list(SpanKind))
def test_root_kind_finish_once_and_canonical_snapshot(kind):
    completed = []
    tracer = Tracer("order-service", completed.append)
    with tracer.start_span("operation", kind, parent=None) as span:
        assert span.parent_span_id is None
        assert get_current_span() is span
        assert not span.finished
        first = span.finish()
        assert span.finished
        assert span.finish() is first
    assert get_current_span() is None
    assert completed == [first]
    assert first.span_kind == kind
    assert first.status == SpanStatus.OK
    assert first.duration_us >= 0
    assert first.end_time >= first.start_time
    assert first.start_time.tzinfo == UTC
    assert first.end_time.tzinfo == UTC
    assert set(first.model_dump()) == {
        "trace_id",
        "span_id",
        "parent_span_id",
        "service_name",
        "operation_name",
        "span_kind",
        "start_time",
        "end_time",
        "duration_us",
        "status",
        "error_type",
        "error_message",
        "attributes",
    }


def test_invalid_kind_and_bounded_names_rejected():
    with pytest.raises(ValueError):
        with Tracer("order-service").start_span("operation", "PRODUCER"):
            pass
    for service, operation in [("", "op"), ("s" * 101, "op"), ("svc", "o" * 201)]:
        with pytest.raises(ValueError):
            with Tracer(service).start_span(operation):
                pass
    assert get_current_span() is None


def test_child_identity_nested_context_restoration_and_explicit_root():
    tracer = Tracer("order-service")
    with tracer.start_span("root", SpanKind.SERVER) as root:
        with tracer.start_span("child") as child:
            assert get_current_span() is child
            assert child.context.trace_id == root.context.trace_id
            assert child.context.span_id != root.context.span_id
            assert child.parent_span_id == root.context.span_id
            with tracer.start_span("independent", parent=None) as independent:
                assert independent.context.trace_id != root.context.trace_id
                assert independent.parent_span_id is None
            assert get_current_span() is child
        assert get_current_span() is root
    assert get_current_span() is None


def test_remote_parent_is_preserved():
    parent = SpanContext(TRACE_ID, SPAN_ID, "00")
    with Tracer("payment-service").start_span("POST /charge", SpanKind.SERVER, parent=parent) as s:
        assert s.context.trace_id == TRACE_ID
        assert s.context.span_id != SPAN_ID
        assert s.parent_span_id == SPAN_ID
        assert s.context.trace_flags == "00"


def test_duration_uses_monotonic_microseconds_and_clamps_clock_regression(monkeypatch):
    from microtrace_sdk import span as span_module

    start = datetime(2026, 10, 2, tzinfo=UTC)
    times = iter([start, start - timedelta(seconds=1)])
    ticks = iter([1_000_000, 6_432_100])
    monkeypatch.setattr(span_module, "utc_now", lambda: next(times))
    monkeypatch.setattr(span_module.time, "perf_counter_ns", lambda: next(ticks))
    with Tracer("service").start_span("operation") as span:
        result = span.finish()
    assert result.duration_us == 5432
    assert result.end_time == start


def test_error_finishes_restores_context_and_never_copies_exception_text():
    completed = []
    tracer = Tracer("order-service", completed.append)
    with tracer.start_span("root") as root:
        with pytest.raises(ValueError, match="private-demo-value"):
            with tracer.start_span("fails"):
                raise ValueError("Authorization: Bearer private-demo-value " + "x" * 1000)
        assert get_current_span() is root
    failed = completed[0]
    assert failed.status == SpanStatus.ERROR
    assert failed.error_type == "ValueError"
    assert failed.error_message == "Operation failed"
    assert "private-demo-value" not in failed.model_dump_json()
    assert get_current_span() is None


def test_manual_finish_does_not_mask_later_business_exception():
    with pytest.raises(ValueError, match="business error"):
        with Tracer("service").start_span("operation") as span:
            span.finish()
            raise ValueError("business error")
    assert get_current_span() is None


@pytest.mark.parametrize("value", ["value", 42, 1.25, True, None])
def test_allowed_scalar_attributes_preserved(value):
    with Tracer("service").start_span("operation") as span:
        span.set_attribute("order.id", value)
        result = span.finish()
    assert result.attributes["order.id"] == value
    assert type(result.attributes["order.id"]) is type(value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("Authorization", "secret"),
        ("request.body", "body"),
        ("k" * 65, "x"),
        ("order.id", "x" * 257),
        ("order.id", {}),
        ("order.id", []),
        ("order.id", float("nan")),
        ("order.id", float("inf")),
    ],
)
def test_unsafe_oversized_or_nonscalar_attributes_rejected(key, value):
    with Tracer("service").start_span("operation") as span:
        with pytest.raises(ValueError):
            span.set_attribute(key, value)
        assert span.finish().attributes == {}


def test_attribute_count_boundary_and_finished_span_cannot_change():
    with pytest.raises(ValueError, match="16"):
        validate_attributes({str(i): i for i in range(17)})
    with Tracer("service").start_span("operation") as span:
        span.set_attribute("order.id", "x" * 256)
        result = span.finish()
        with pytest.raises(RuntimeError):
            span.set_attribute("order.id", "changed")
        with pytest.raises(RuntimeError):
            span.record_error(ValueError())
    assert result.attributes == {"order.id": "x" * 256}


def test_completion_callback_failure_does_not_break_business(caplog):
    def failing_callback(_):
        raise RuntimeError("private callback details")

    with Tracer("service", failing_callback).start_span("operation") as span:
        result = span.finish()
        assert span.finish() is result
    assert "private callback details" not in caplog.text
    assert "telemetry discarded" in caplog.text


def test_concurrent_tasks_keep_distinct_current_spans_and_restore_parent():
    async def exercise():
        entered = 0
        all_entered = asyncio.Event()
        tracer = Tracer("order-service")

        async def request(index):
            nonlocal entered
            assert get_current_span() is None
            with tracer.start_span(f"request-{index}", SpanKind.SERVER, parent=None) as root:
                entered += 1
                if entered == 25:
                    all_entered.set()
                await all_entered.wait()
                for _ in range(3):
                    with tracer.start_span("nested") as child:
                        await asyncio.sleep(0)
                        assert get_current_span() is child
                        assert child.parent_span_id == root.context.span_id
                        assert child.context.trace_id == root.context.trace_id
                    assert get_current_span() is root
                identity = root.context
            assert get_current_span() is None
            return identity

        contexts = await asyncio.gather(*(request(i) for i in range(25)))
        assert len({c.trace_id for c in contexts}) == 25
        assert len({c.span_id for c in contexts}) == 25
        assert get_current_span() is None

    asyncio.run(exercise())


def test_cancelled_task_finishes_error_and_resets_context():
    completed = []

    async def exercise():
        with pytest.raises(asyncio.CancelledError):
            with Tracer("service", completed.append).start_span("cancelled"):
                raise asyncio.CancelledError()
        assert get_current_span() is None

    asyncio.run(exercise())
    assert len(completed) == 1
    assert completed[0].status == SpanStatus.ERROR


def test_finished_model_rejects_invalid_timing_and_enum():
    with Tracer("service").start_span("operation") as span:
        data = span.finish().model_dump()
    for change in (
        {"duration_us": -1},
        {"span_kind": "UNKNOWN"},
        {"start_time": datetime(2026, 10, 2)},
        {"end_time": data["start_time"] - timedelta(seconds=1)},
    ):
        with pytest.raises(ValueError):
            FinishedSpan(**{**data, **change})
