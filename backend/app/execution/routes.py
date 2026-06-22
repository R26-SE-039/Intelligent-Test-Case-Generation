"""
Execution & Report routes — REST + WebSocket.

POST /api/v1/execute                — kick off a run for the selected suite
GET  /api/v1/runs                   — list recent runs for a project
GET  /api/v1/runs/{run_id}          — fetch one run + scenarios + screenshots
GET  /api/v1/runs/{run_id}/log      — download raw log as text/plain
GET  /api/v1/runs/{run_id}/report.pdf — stream the generated PDF
GET  /api/v1/runs/{run_id}/screenshots/{file} — static PNG served from disk
POST /api/v1/webhooks/github-runs   — GH Actions final notification webhook
WS   /ws/execution/{run_id}         — live event stream
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import TestRunExecution, TestRunScreenshot, TestRun, TestSuite

from .log_broker import broker as log_broker
from .runner import start_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["execution"])

_DEFAULT_REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"
REPORTS_ROOT = Path(os.getenv("NEXTGENQA_REPORTS_DIR", str(_DEFAULT_REPORTS_DIR))).resolve()


# ─── Pydantic ────────────────────────────────────────────────────────────────


class ExecuteRequest(BaseModel):
    suite_id: str
    project_id: str
    mode: Optional[str] = None    # "github" | "local" | None (auto)


class ExecuteResponse(BaseModel):
    run_id: str
    mode: str                     # the mode that was actually picked


class ScenarioOut(BaseModel):
    scenario_name: str
    flow_name: str
    status: str
    duration_ms: Optional[int]
    error_message: Optional[str]


class ScreenshotOut(BaseModel):
    scenario: str
    label: str
    status: str
    image_url: str


class RunOut(BaseModel):
    id: str
    project_id: str
    suite_id: Optional[str]
    framework: str
    mode: str
    status: str
    github_run_id: Optional[str]
    github_run_url: Optional[str]
    github_branch: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    duration_ms: Optional[int]
    total_count: int
    passed_count: int
    failed_count: int
    pdf_url: Optional[str]
    log_url: str
    error_message: Optional[str]


class RunDetailOut(RunOut):
    scenarios: list[ScenarioOut]
    screenshots: list[ScreenshotOut]
    raw_log_preview: str


class GitHubWebhookIn(BaseModel):
    run_id: str
    github_run_id: Optional[str] = None
    status: Optional[str] = None
    framework: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _run_out(row: TestRunExecution) -> RunOut:
    return RunOut(
        id=str(row.id),
        project_id=str(row.project_id),
        suite_id=str(row.suite_id) if row.suite_id else None,
        framework=row.framework,
        mode=row.mode,
        status=row.status,
        github_run_id=row.github_run_id,
        github_run_url=row.github_run_url,
        github_branch=row.github_branch,
        started_at=row.started_at.isoformat() if row.started_at else None,
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
        duration_ms=row.duration_ms,
        total_count=row.total_count or 0,
        passed_count=row.passed_count or 0,
        failed_count=row.failed_count or 0,
        pdf_url=f"/api/v1/runs/{row.id}/report.pdf" if row.pdf_path else None,
        log_url=f"/api/v1/runs/{row.id}/log",
        error_message=row.error_message,
    )


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/execute", response_model=ExecuteResponse)
async def execute_suite(body: ExecuteRequest, db: AsyncSession = Depends(get_db)):
    """Kick off a run for the chosen suite and return its run_id."""
    suite_q = await db.execute(select(TestSuite).where(TestSuite.id == body.suite_id))
    suite = suite_q.scalar_one_or_none()
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")
    if str(suite.project_id) != body.project_id:
        raise HTTPException(status_code=400, detail="Suite does not belong to that project")

    try:
        run_id = await start_run(
            suite_id=body.suite_id,
            project_id=body.project_id,
            force_mode=body.mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Refetch the row to discover the actual mode (after fallback logic).
    row_q = await db.execute(select(TestRunExecution).where(TestRunExecution.id == run_id))
    row = row_q.scalar_one()
    return ExecuteResponse(run_id=run_id, mode=row.mode)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    project_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Recent runs for a project, newest first."""
    q = await db.execute(
        select(TestRunExecution)
        .where(TestRunExecution.project_id == project_id)
        .order_by(TestRunExecution.started_at.desc())
        .limit(limit)
    )
    return [_run_out(r) for r in q.scalars().all()]


@router.get("/runs/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    row_q = await db.execute(select(TestRunExecution).where(TestRunExecution.id == run_id))
    row = row_q.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    sc_q = await db.execute(
        select(TestRun)
        .where(TestRun.suite_id == row.suite_id)
        .order_by(TestRun.executed_at.asc())
    )
    scenarios = sc_q.scalars().all()

    sh_q = await db.execute(
        select(TestRunScreenshot)
        .where(TestRunScreenshot.run_id == row.id)
        .order_by(TestRunScreenshot.captured_at.asc())
    )
    shots = sh_q.scalars().all()

    base = _run_out(row)
    log = row.raw_log_text or ""
    return RunDetailOut(
        **base.model_dump(),
        scenarios=[
            ScenarioOut(
                scenario_name=s.scenario_name,
                flow_name=s.flow_name,
                status=s.status,
                duration_ms=s.duration_ms,
                error_message=s.error_message,
            ) for s in scenarios
        ],
        screenshots=[
            ScreenshotOut(
                scenario=s.scenario,
                label=s.label,
                status=s.status,
                image_url=f"/api/v1/runs/{row.id}/screenshots/{Path(s.image_path).name}",
            ) for s in shots
        ],
        raw_log_preview="\n".join(log.splitlines()[-400:]),
    )


@router.get("/runs/{run_id}/log")
async def download_run_log(run_id: str, db: AsyncSession = Depends(get_db)):
    """Raw log file (text/plain). Saved to DB at run end; also written to disk."""
    row_q = await db.execute(select(TestRunExecution).where(TestRunExecution.id == run_id))
    row = row_q.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return PlainTextResponse(
        row.raw_log_text or "(log not yet available — run is still in progress)",
        headers={
            "Content-Disposition": f"attachment; filename=nextgenqa-run-{run_id}.log"
        },
    )


@router.get("/runs/{run_id}/report.pdf")
async def download_run_pdf(run_id: str, db: AsyncSession = Depends(get_db)):
    row_q = await db.execute(select(TestRunExecution).where(TestRunExecution.id == run_id))
    row = row_q.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    if not row.pdf_path or not Path(row.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not generated yet")
    return FileResponse(
        row.pdf_path,
        media_type="application/pdf",
        filename=f"nextgenqa-report-{run_id}.pdf",
    )


@router.get("/runs/{run_id}/screenshots/{filename}")
async def serve_screenshot(run_id: str, filename: str):
    """Static PNG from ./reports/{run_id}/screenshots/."""
    # Path-traversal guard: filenames must be plain.
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = REPORTS_ROOT / run_id / "screenshots" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path, media_type="image/png")


@router.post("/webhooks/github-runs")
async def github_webhook(body: GitHubWebhookIn, db: AsyncSession = Depends(get_db)):
    """
    GitHub Actions final notification. The workflow's `Notify NextGen QA backend`
    step posts here with `run_id` (ours) so we can stamp completion even if the
    poller in github_runner missed the transition.
    """
    row_q = await db.execute(select(TestRunExecution).where(TestRunExecution.id == body.run_id))
    row = row_q.scalar_one_or_none()
    if not row:
        # We may receive webhooks for runs we don't know about — be polite.
        return {"ok": True, "note": "unknown run, ignored"}

    if body.github_run_id and not row.github_run_id:
        row.github_run_id = body.github_run_id
    if body.status and row.status in ("queued", "running"):
        row.status = "passed" if body.status.lower() == "success" else "failed"
    if not row.finished_at:
        row.finished_at = datetime.now(timezone.utc)
    db.add(row)
    await db.commit()

    log_broker.publish(body.run_id, {
        "type": "step",
        "step": f"GitHub webhook received: {body.status}",
        "status": row.status,
    })
    return {"ok": True}


# ─── WebSocket ───────────────────────────────────────────────────────────────


async def execution_ws_endpoint(websocket: WebSocket, run_id: str):
    """Live event stream for the execution dashboard."""
    await websocket.accept()
    queue = log_broker.open(run_id)
    logger.info("WS subscribed to execution run: %s", run_id)
    try:
        while True:
            evt = await queue.get()
            if evt is None:
                await websocket.send_json({"type": "end"})
                break
            await websocket.send_json(evt)
    except Exception as e:
        logger.warning("WS execution stream error for %s: %s", run_id, e)
    finally:
        log_broker.close(run_id)
        try:
            await websocket.close()
        except Exception:
            pass


def register_execution_websocket(app):
    """Attach the WS route once during app startup."""
    app.add_api_websocket_route("/ws/execution/{run_id}", execution_ws_endpoint)
