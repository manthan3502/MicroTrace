import asyncio
import logging
import math
import time
from contextvars import Context

import httpx

from microtrace_sdk.models import FinishedSpan

logger = logging.getLogger(__name__)


class SpanExporter:
    """One bounded queue and worker. Each accepted span gets one delivery attempt."""

    def __init__(self, url: str, capacity: int = 256, timeout: float = 1.0):
        if capacity <= 0 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Export capacity and timeout must be positive")
        self.url = url
        self.timeout = timeout
        self.queue: asyncio.Queue[FinishedSpan] = asyncio.Queue(maxsize=capacity)
        self.worker: asyncio.Task | None = None
        self.accepting = False
        self.dropped = 0
        self._last_warning = float("-inf")

    def _warn(self):
        now = time.monotonic()
        if now - self._last_warning >= 5:
            logger.warning("Span export dropped telemetry; delivery is best effort")
            self._last_warning = now

    def enqueue(self, span: FinishedSpan) -> None:
        try:
            if not self.accepting:
                raise asyncio.QueueFull
            self.queue.put_nowait(span)
        except asyncio.QueueFull:
            self.dropped += 1
            self._warn()

    def start(self, client: httpx.AsyncClient) -> None:
        if self.worker is not None:
            raise RuntimeError("Exporter already started")
        self.accepting = True
        self.worker = asyncio.create_task(self._run(client), context=Context())

    async def _run(self, client: httpx.AsyncClient):
        while True:
            span = await self.queue.get()
            try:
                async with asyncio.timeout(self.timeout):
                    response = await client.post(
                        self.url, json=span.model_dump(mode="json"), timeout=self.timeout
                    )
                    response.raise_for_status()
            except asyncio.CancelledError:
                self.dropped += 1
                raise
            except Exception:
                self.dropped += 1
                self._warn()
            finally:
                self.queue.task_done()

    async def close(self, drain_timeout: float = 2.0) -> None:
        self.accepting = False
        if self.worker is None:
            return
        try:
            await asyncio.wait_for(self.queue.join(), timeout=drain_timeout)
        except TimeoutError:
            self._warn()
        finally:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
                self.dropped += 1
