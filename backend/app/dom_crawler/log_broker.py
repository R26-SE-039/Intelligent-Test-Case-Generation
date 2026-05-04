"""
In-process pub/sub for live crawler logs.

POST /dom/crawl runs the (synchronous) crawler in a worker thread and pushes
log lines into a per-run asyncio.Queue. WS /ws/dom/crawl/{run_id} subscribes
to that queue and forwards each line to the browser as JSON.

Single-process only. If you scale to multiple workers, replace the in-memory
dict with Redis pub/sub or similar.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LogBroker:
    """Per-run log fan-out."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Optional[str]]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Stash the FastAPI event loop so worker threads can push events to it."""
        self._loop = loop

    def open(self, run_id: str) -> asyncio.Queue[Optional[str]]:
        q: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=1024)
        self._queues[run_id] = q
        return q

    def close(self, run_id: str) -> None:
        q = self._queues.pop(run_id, None)
        if q is not None:
            # Sentinel — tells subscribers the run is finished.
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def publish_threadsafe(self, run_id: str, line: str) -> None:
        """
        Called from the synchronous crawler running in a worker thread.
        Hops onto the FastAPI event loop to enqueue.
        """
        if self._loop is None:
            return
        q = self._queues.get(run_id)
        if q is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._enqueue_nowait, q, line)
        except RuntimeError:
            # Loop might be closing; drop the line silently.
            pass

    @staticmethod
    def _enqueue_nowait(q: asyncio.Queue, line: str) -> None:
        try:
            q.put_nowait(line)
        except asyncio.QueueFull:
            # Drop oldest; live log streams are best-effort.
            try:
                q.get_nowait()
                q.put_nowait(line)
            except Exception:
                pass


broker = LogBroker()
