from starlette.types import ASGIApp, Message, Receive, Scope, Send

from microtrace_sdk.models import SpanKind
from microtrace_sdk.traceparent import parse_traceparent
from microtrace_sdk.tracer import Tracer


class HTTPServerError(Exception):
    """Sanitized category for an HTTP server failure response."""


class TracingMiddleware:
    """Pure ASGI middleware keeps context in the same task as the handler."""

    def __init__(self, app: ASGIApp, tracer: Tracer) -> None:
        self.app = app
        self.tracer = tracer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].rstrip("/") == "/health":
            await self.app(scope, receive, send)
            return
        incoming = [value for key, value in scope["headers"] if key.lower() == b"traceparent"]
        header = incoming[0].decode("latin-1") if len(incoming) == 1 else None
        parent = parse_traceparent(header)
        method = scope["method"].upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}:
            method = "HTTP"
        status_code = 500
        with self.tracer.start_span(f"{method} unmatched", SpanKind.SERVER, parent=parent) as span:
            span.set_attribute("http.method", method)

            async def send_traced(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                await send(message)

            try:
                await self.app(scope, receive, send_traced)
            finally:
                route = getattr(scope.get("route"), "path", "unmatched")
                span.operation_name = f"{method} {route}"[:200]
                span.set_attribute("http.route", route[:256])
                span.set_attribute("http.status_code", status_code)
                if status_code >= 500:
                    span.record_error(HTTPServerError())
