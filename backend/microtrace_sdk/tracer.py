from collections.abc import Callable, Iterator
from contextlib import contextmanager

from microtrace_sdk.context import activate_span, get_current_span
from microtrace_sdk.ids import new_span_id, new_trace_id
from microtrace_sdk.models import FinishedSpan, SpanContext, SpanKind
from microtrace_sdk.span import Span

_CURRENT = object()


class Tracer:
    def __init__(
        self, service_name: str, on_finish: Callable[[FinishedSpan], None] | None = None
    ) -> None:
        self.service_name = service_name
        self.on_finish = on_finish

    @contextmanager
    def start_span(
        self,
        operation_name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        *,
        parent: SpanContext | None | object = _CURRENT,
    ) -> Iterator[Span]:
        # Omitted parent inherits current context; explicit None starts a new root.
        if parent is _CURRENT:
            active = get_current_span()
            parent = active.context if active is not None else None
        if parent is not None and not isinstance(parent, SpanContext):
            raise TypeError("Parent must be a SpanContext or None")
        context = SpanContext(
            parent.trace_id if parent else new_trace_id(),
            new_span_id(),
            parent.trace_flags if parent else "01",
        )
        span = Span(
            context,
            parent.span_id if parent else None,
            self.service_name,
            operation_name,
            kind,
            self.on_finish,
        )
        with activate_span(span):
            try:
                yield span
            except BaseException as error:
                if not span.finished:
                    span.record_error(error)
                raise
            finally:
                span.finish()
