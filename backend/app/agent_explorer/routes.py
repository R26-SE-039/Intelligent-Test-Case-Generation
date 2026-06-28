"""
Routes for the Agent Explorer.

  POST /api/v1/agent/explore   — kicks off an exploration run (returns run_id immediately,
                                  agent runs in background, events stream via WS)
  WS   /ws/agent/{run_id}      — live event stream consumed by the React dashboard
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel

from app.agent_explorer.agent import run_exploration, MAX_STEPS_DEFAULT
from app.agent_explorer.log_broker import broker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent_explorer"])


class ExploreRequest(BaseModel):
    intent: str
    url: str
    project_id: Optional[str] = None     # optional — agent doesn't need DB access for the demo
    max_steps: int = MAX_STEPS_DEFAULT
    headless: bool = False               # demo default: headed so panel sees the browser


class ExploreResponse(BaseModel):
    run_id: str
    message: str


@router.post("/explore", response_model=ExploreResponse)
async def start_exploration(body: ExploreRequest) -> ExploreResponse:
    if not body.intent.strip():
        raise HTTPException(status_code=400, detail="intent is required")
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="url must start with http:// or https://")

    run_id = uuid.uuid4().hex
    # Open the queue *before* spawning the worker so the WS subscriber, which
    # the frontend opens immediately after this POST returns, never races to
    # subscribe after the first event has already been published.
    broker.open(run_id)

    # Fire-and-forget. Errors and end-of-run are signalled via the broker, not
    # via this HTTP response.
    asyncio.create_task(_run_and_swallow(
        intent=body.intent,
        start_url=body.url,
        run_id=run_id,
        max_steps=body.max_steps,
        headless=body.headless,
    ))

    return ExploreResponse(run_id=run_id, message="Exploration started")


async def _run_and_swallow(**kwargs) -> None:
    """Run the agent; never let an exception escape into the asyncio task pool."""
    try:
        await run_exploration(**kwargs)
    except Exception as e:
        logger.exception("Agent exploration crashed: %s", e)
        broker.publish_threadsafe(kwargs["run_id"], {
            "type": "error",
            "message": f"Crash: {type(e).__name__}: {e}",
        })
        broker.close(kwargs["run_id"])


def register_agent_websocket(app) -> None:
    """
    Called from main.py during app construction. Registers the WS endpoint
    here (rather than in the APIRouter) because FastAPI WebSocket routes
    don't compose into routers as cleanly as HTTP routes.
    """

    @app.websocket("/ws/agent/{run_id}")
    async def agent_stream(websocket: WebSocket, run_id: str):
        await websocket.accept()
        # If the POST opened the queue first, this returns the same instance.
        # Otherwise it creates a fresh one (graceful for replays/manual testing).
        queue = broker.open(run_id) if run_id not in broker._queues else broker._queues[run_id]  # type: ignore[attr-defined]
        logger.info("WS subscribed to agent run: %s", run_id)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    await websocket.send_json({"type": "end"})
                    break
                await websocket.send_json(event)
        except Exception as e:
            logger.warning("Agent WS error for %s: %s", run_id, e)
        finally:
            broker.close(run_id)
            try:
                await websocket.close()
            except Exception:
                pass
