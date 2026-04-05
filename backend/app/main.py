from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

from app.database import init_db
from app.routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB table creation on startup."""
    logger.info("Initialising database tables...")
    await init_db()
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


@app.get("/")
async def root():
    return {"message": "NextGen QA Component 2 API is running.", "version": "0.2.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.websocket("/ws/execution/{run_id}")
async def execution_stream(websocket: WebSocket, run_id: str):
    await websocket.accept()
    logger.info(f"WebSocket client connected for run_id: {run_id}")
    try:
        await websocket.send_json({
            "step": "Initializing run",
            "status": "running",
        })
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        logger.info(f"WebSocket client disconnected for run_id: {run_id}")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
