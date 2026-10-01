import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from microtrace_sdk.models import (
    FinishedSpan,
    Scalar,
    SpanContext,
    SpanKind,
    SpanStatus,
    validate_attributes,
)

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Span:
    def __init__(
        self,
        context: SpanContext,
        parent_span_id: str | None,
        service_name: str,
        operation_name: str,
        kind: SpanKind,
        on_finish: Callable[[FinishedSpan], None] | None = None,
    ) -> None:
        if not 1 <= len(service_name) <= 100 or not 1 <= len(operation_name) <= 200:
            raise ValueError("Service/operation name exceeds its bounds")
        self.context = context
        self.parent_span_id = parent_span_id
        self.service_name = service_name
        self.operation_name = operation_name
        self.kind = SpanKind(kind)
        self.start_time = utc_now()
        self._monotonic_start = time.perf_counter_ns()
        self.status = SpanStatus.OK
        self.error_type: str | None = None
        self.error_message: str | None = None
        self._attributes: dict[str, Scalar] = {}
        self._completed: FinishedSpan | None = None
        self._on_finish = on_finish

    @property
    def finished(self) -> bool:
        return self._completed is not None

    def set_attribute(self, key: str, value: Scalar) -> None:
        if self.finished:
            raise RuntimeError("Span is finished")
        self._attributes = validate_attributes({**self._attributes, key: value})

    def record_error(self, error: BaseException) -> None:
        if self.finished:
            raise RuntimeError("Span is finished")
        self.status = SpanStatus.ERROR
        self.error_type = type(error).__name__[:128]
        # Exception text may contain credentials, bodies or URLs. Never copy it.
        self.error_message = "Operation failed"

    def finish(self) -> FinishedSpan:
        if self._completed is not None:
            return self._completed
        self._completed = FinishedSpan(
            trace_id=self.context.trace_id,
            span_id=self.context.span_id,
            parent_span_id=self.parent_span_id,
            service_name=self.service_name,
            operation_name=self.operation_name,
            span_kind=self.kind,
            start_time=self.start_time,
            end_time=max(utc_now(), self.start_time),
            duration_us=max(0, (time.perf_counter_ns() - self._monotonic_start) // 1000),
            status=self.status,
            error_type=self.error_type,
            error_message=self.error_message,
            attributes=dict(self._attributes),
        )
        if self._on_finish is not None:
            try:
                self._on_finish(self._completed)
            except Exception:
                logger.warning("Span completion callback failed; telemetry discarded")
        return self._completed
