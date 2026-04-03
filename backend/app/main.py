from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NextGen QA Component 2 - Intelligent Test Case Generation",
    description="Backend microservice for AI-powered test generation, DOM crawling, and CI/CD execution.",
    version="0.1.0"
)

# CORS middleware to allow requests from the React dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "NextGen QA Component 2 API engine is running."}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.websocket("/ws/execution/{run_id}")
async def execution_stream(websocket: WebSocket, run_id: str):
    await websocket.accept()
    logger.info(f"WebSocket client connected for run_id: {run_id}")
    try:
        # Placeholder for streaming logs
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
