from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from microtrace_sdk.span import Span

_current_span: ContextVar["Span | None"] = ContextVar("microtrace_current_span", default=None)


def get_current_span() -> "Span | None":
    return _current_span.get()


@contextmanager
def activate_span(span: "Span") -> Iterator[None]:
    token = _current_span.set(span)
    try:
        yield
    finally:
        _current_span.reset(token)
