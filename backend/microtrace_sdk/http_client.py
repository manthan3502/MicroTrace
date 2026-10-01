from typing import Any

import httpx

from microtrace_sdk.models import SpanKind
from microtrace_sdk.traceparent import format_traceparent
from microtrace_sdk.tracer import Tracer


class DownstreamHTTPError(Exception):
    """Sanitized category for a downstream HTTP failure response."""


async def traced_request(
    client: httpx.AsyncClient,
    tracer: Tracer,
    method: str,
    url: str,
    *,
    peer_service: str,
    route: str,
    json: dict[str, Any],
    headers: httpx.Headers | dict[str, str] | None = None,
) -> httpx.Response:
    with tracer.start_span(f"{method} {peer_service} {route}", SpanKind.CLIENT) as span:
        span.set_attribute("http.method", method)
        span.set_attribute("http.route", route)
        span.set_attribute("peer.service", peer_service)
        outbound = httpx.Headers(headers)
        outbound["traceparent"] = format_traceparent(span.context)
        response = await client.request(method, url, json=json, headers=outbound)
        span.set_attribute("http.status_code", response.status_code)
        if response.status_code >= 500:
            span.record_error(DownstreamHTTPError())
        return response
