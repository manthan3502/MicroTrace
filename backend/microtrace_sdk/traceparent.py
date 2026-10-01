import re

from microtrace_sdk.models import SpanContext


def parse_traceparent(header: str | None) -> SpanContext | None:
    if not isinstance(header, str):
        return None
    match = re.fullmatch(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})", header)
    if match is None:
        return None
    try:
        return SpanContext(*match.groups())
    except ValueError:
        return None


def format_traceparent(context: SpanContext) -> str:
    return f"00-{context.trace_id}-{context.span_id}-{context.trace_flags}"
