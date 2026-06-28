"""
Per-run pub/sub for live agent events. Same shape as dom_crawler.log_broker
but each queue carries dict events (typed messages) instead of plain strings,
because the agent emits structured items: thought / action / observation /
screenshot / coverage / done / error.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AgentBroker:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Optional[dict]]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def open(self, run_id: str) -> asyncio.Queue[Optional[dict]]:
        q: asyncio.Queue[Optional[dict]] = asyncio.Queue(maxsize=2048)
        self._queues[run_id] = q
        return q

    def close(self, run_id: str) -> None:
        q = self._queues.pop(run_id, None)
        if q is not None:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def publish_threadsafe(self, run_id: str, event: dict[str, Any]) -> None:
        if self._loop is None:
            return
        q = self._queues.get(run_id)
        if q is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._enqueue_nowait, q, event)
        except RuntimeError:
            pass

    @staticmethod
    def _enqueue_nowait(q: asyncio.Queue, event: dict) -> None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(event)
            except Exception:
                pass


broker = AgentBroker()
