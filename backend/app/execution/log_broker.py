"""
In-process pub/sub for live execution logs.

The runner (subprocess or GitHub Actions poller) pushes structured events
into a per-run asyncio.Queue. WS /ws/execution/{run_id} subscribes to the
queue and forwards each event to the dashboard.

Events are dicts so the runner can multiplex log lines, step transitions,
screenshot URLs, and the final summary over one channel.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ExecutionLogBroker:
    """Per-run event fan-out for the execution dashboard."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Optional[dict[str, Any]]]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def open(self, run_id: str) -> asyncio.Queue[Optional[dict[str, Any]]]:
        q: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue(maxsize=2048)
        self._queues[run_id] = q
        return q

    def close(self, run_id: str) -> None:
        q = self._queues.pop(run_id, None)
        if q is not None:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        """Coroutine-safe enqueue from the main loop (or already inside it)."""
        q = self._queues.get(run_id)
        if q is None:
            return
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(event)
            except Exception:
                pass

    def publish_threadsafe(self, run_id: str, event: dict[str, Any]) -> None:
        """For runners executing in a worker thread (subprocess wrapper)."""
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self.publish, run_id, event)
        except RuntimeError:
            pass


broker = ExecutionLogBroker()
