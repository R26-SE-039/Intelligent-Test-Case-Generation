import asyncio
import sys

# Playwright spawns the browser via asyncio subprocess transport, which
# requires the Proactor loop on Windows. uvicorn / FastAPI on Windows can
# end up on the Selector loop, which raises NotImplementedError when
# subprocess_exec is called. Set the policy before anything else imports
# asyncio internals.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

from app.database import init_db
from app.routes import router
from app.dom_crawler import log_broker
from app.agent_explorer import agent_broker
from app.agent_explorer.routes import router as agent_router, register_agent_websocket
from app.execution import log_broker as execution_log_broker
from app.execution.routes import router as execution_router, register_execution_websocket
from app.github_connection.routes import router as github_connection_router
from app.integration.routes import router as integration_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB table creation on startup."""
    logger.info("Initialising database tables...")
    await init_db()
    loop = asyncio.get_running_loop()
    log_broker.bind_loop(loop)
    agent_broker.bind_loop(loop)
    execution_log_broker.bind_loop(loop)
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="NextGen QA Component 2 — Intelligent Test Case Generation",
    description="AI-powered Gherkin + Multi-Framework Code Generation with CI/CD Integration",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allow React dashboard on port 3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All pipeline routes
app.include_router(router)
app.include_router(agent_router)
app.include_router(execution_router)
app.include_router(github_connection_router)
app.include_router(integration_router)
register_agent_websocket(app)
register_execution_websocket(app)


@app.get("/")
async def root():
    return {"message": "NextGen QA Component 2 API is running.", "version": "0.2.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.websocket("/ws/dom/crawl/{run_id}")
async def dom_crawl_stream(websocket: WebSocket, run_id: str):
    """
    Live crawler log stream (Phase 3). The frontend opens this BEFORE calling
    POST /dom/crawl with the same run_id; messages are forwarded until the
    crawler publishes the sentinel (None) signalling end-of-run.
    """
    await websocket.accept()
    queue = log_broker.open(run_id)
    logger.info(f"WS subscribed to crawl run: {run_id}")
    try:
        while True:
            line = await queue.get()
            if line is None:
                await websocket.send_json({"type": "end"})
                break
            await websocket.send_json({"type": "log", "line": line})
    except Exception as e:
        logger.warning(f"WS crawl stream error for {run_id}: {e}")
    finally:
        log_broker.close(run_id)
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
