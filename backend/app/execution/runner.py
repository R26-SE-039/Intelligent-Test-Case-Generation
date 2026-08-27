"""
Run orchestrator — bridges the DB row, the chosen runner (GitHub or local),
the WebSocket log broker, and the PDF generator.

The public entry point is `start_run(...)`. It is launched as an asyncio
background task by the /api/v1/execute route handler so the HTTP request
returns immediately with the run_id while execution proceeds.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import TestRunExecution, TestRunScreenshot, TestSuite, TestRun

from . import github_runner
from .github_runner import GitHubConfig
from .local_runner import LocalRunResult, REPORTS_ROOT, run_suite_locally, ScenarioResult
from .log_broker import broker as log_broker
from .pdf_generator import render_run_pdf

logger = logging.getLogger(__name__)


_FLOW_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("login", "login_flow"),
    ("logout", "login_flow"),
    ("auth", "login_flow"),
    ("cart", "cart_ops"),
    ("checkout", "checkout"),
    ("payment", "checkout"),
    ("search", "search"),
)


def _flow_name_for(scenario: str) -> str:
    name = scenario.lower()
    for needle, flow in _FLOW_KEYWORDS:
        if needle in name:
            return flow
    return "other"


async def detect_mode(
    project_id: str,
    force: Optional[str] = None,
    auth_header: Optional[str] = None,
) -> str:
    """
    Pick 'github' if the project has a saved connection (or the legacy
    GITHUB_TOKEN env var is set), else 'local'. `force` wins when the
    caller wants to override the auto-detection (e.g. demo mode).
    """
    if force in ("github", "local"):
        return force
    project_cfg = await GitHubConfig.from_project(project_id, auth_header)
    if project_cfg is not None:
        return "github"
    return "github" if GitHubConfig.from_env() else "local"


async def start_run(
    *,
    suite_id: str,
    project_id: str,
    force_mode: Optional[str] = None,
    auth_header: Optional[str] = None,
) -> str:
    """
    Create the TestRunExecution row, hand off to the chosen runner in a
    background task, return the run_id so the HTTP caller can subscribe to
    the WebSocket immediately.
    """
    run_id = str(uuid.uuid4())
    log_broker.open(run_id)  # subscribers can attach before the worker pushes

    async with AsyncSessionLocal() as db:
        suite_q = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
        suite = suite_q.scalar_one_or_none()
        if not suite:
            log_broker.publish(run_id, {"type": "error", "message": "Suite not found"})
            log_broker.close(run_id)
            raise ValueError("Suite not found")

        mode = await detect_mode(project_id, force_mode, auth_header)
        row = TestRunExecution(
            id=uuid.UUID(run_id),
            project_id=project_id,
            suite_id=suite.id,
            framework=suite.framework,
            mode=mode,
            status="queued",
        )
        db.add(row)
        await db.commit()

    # Fire-and-forget background task. asyncio.create_task pins it to the
    # current event loop so it survives past the HTTP response.
    asyncio.create_task(_drive_run(run_id, suite_id, project_id, auth_header))
    return run_id


async def start_rerun(*, prev_run_id: str, auth_header: Optional[str] = None) -> str:
    """
    Trigger GitHub's "re-run" on an existing TestRunExecution. Creates a
    fresh DB row that tracks the new attempt, but reuses the previous run's
    branch + suite. Much faster than `start_run` because there's no branch
    creation, no file push, no workflow_dispatch round-trip.

    Errors:
      ValueError      — prev run not found, isn't a GH run, or has no GH run id.
      RuntimeError    — propagated from the GH rerun API (returned via WS too).
    """
    new_run_id = str(uuid.uuid4())
    log_broker.open(new_run_id)

    async with AsyncSessionLocal() as db:
        prev_q = await db.execute(
            select(TestRunExecution).where(TestRunExecution.id == prev_run_id)
        )
        prev = prev_q.scalar_one_or_none()
        if not prev:
            log_broker.publish(new_run_id, {"type": "error", "message": "Previous run not found"})
            log_broker.close(new_run_id)
            raise ValueError("Previous run not found")
        if prev.mode != "github" or not prev.github_run_id:
            log_broker.publish(new_run_id, {
                "type": "error",
                "message": "Re-run is only available for GitHub Actions runs.",
            })
            log_broker.close(new_run_id)
            raise ValueError("Re-run requires a prior GitHub run with a github_run_id")

        new_row = TestRunExecution(
            id=uuid.UUID(new_run_id),
            project_id=prev.project_id,
            suite_id=prev.suite_id,
            framework=prev.framework,
            mode="github",
            status="queued",
            github_run_id=prev.github_run_id,    # same GH run — new attempt
            github_branch=prev.github_branch,
        )
        db.add(new_row)
        await db.commit()

    asyncio.create_task(_drive_rerun(new_run_id, prev_run_id, auth_header))
    return new_run_id


async def _drive_run(
    run_id: str,
    suite_id: str,
    project_id: str,
    auth_header: Optional[str],
) -> None:
    """The actual long-running coroutine. Catches every exception so a crash
    here never leaks into the FastAPI request handler."""
    try:
        async with AsyncSessionLocal() as db:
            row_q = await db.execute(select(TestRunExecution).where(TestRunExecution.id == run_id))
            row = row_q.scalar_one()
            suite_q = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
            suite = suite_q.scalar_one()

            row.status = "running"
            db.add(row)
            await db.commit()

            if row.mode == "github":
                await _run_via_github(db, row, suite, auth_header)
            else:
                await _run_locally(db, row, suite)

            # PDF generation is the same for both paths since artifacts +
            # log are already persisted by the time we get here.
            await _finalise_run(db, row)

    except Exception as e:
        logger.exception("Execution run %s crashed", run_id)
        log_broker.publish(run_id, {"type": "error", "message": str(e)})
        try:
            async with AsyncSessionLocal() as db:
                row_q = await db.execute(
                    select(TestRunExecution).where(TestRunExecution.id == run_id)
                )
                row = row_q.scalar_one_or_none()
                if row is not None:
                    row.status = "error"
                    row.error_message = str(e)
                    row.finished_at = datetime.now(timezone.utc)
                    db.add(row)
                    await db.commit()
        except Exception:
            logger.exception("Failed to persist error state for run %s", run_id)
    finally:
        log_broker.publish(run_id, {"type": "end"})
        log_broker.close(run_id)


async def _drive_rerun(
    new_run_id: str,
    prev_run_id: str,
    auth_header: Optional[str],
) -> None:
    """
    Background worker for `start_rerun`. Calls GitHub's rerun API on the
    previous run's gh_run_id, then streams progress of the new attempt
    against the same gh_run_id (GitHub increments run_attempt server-side).
    """
    try:
        async with AsyncSessionLocal() as db:
            row_q = await db.execute(
                select(TestRunExecution).where(TestRunExecution.id == new_run_id)
            )
            row = row_q.scalar_one()
            suite_q = await db.execute(select(TestSuite).where(TestSuite.id == row.suite_id))
            suite = suite_q.scalar_one()

            row.status = "running"
            db.add(row)
            await db.commit()

            cfg = await GitHubConfig.from_project(str(row.project_id), auth_header)
            if cfg is None:
                cfg = GitHubConfig.from_env()
            if cfg is None:
                raise RuntimeError("No GitHub connection available for this project.")

            try:
                trigger = await github_runner.rerun_workflow_run(cfg, row.github_run_id)
            except Exception as e:
                msg = f"GitHub re-run failed: {type(e).__name__}: {e}"
                log_broker.publish(new_run_id, {"type": "error", "message": msg})
                row.status = "error"
                row.error_message = msg
                db.add(row)
                await db.commit()
                return

            row.github_run_url = trigger.run_url
            db.add(row)
            await db.commit()

            log_broker.publish(new_run_id, {
                "type": "github",
                "run_url": trigger.run_url,
                "branch": trigger.branch or "",
            })

            # GH needs a beat to flip the run back to in_progress on the
            # new attempt — otherwise the first poll still sees the
            # previous attempt's completed state and we exit immediately.
            await asyncio.sleep(5)

            def _emit(step_event: dict) -> None:
                log_broker.publish(new_run_id, {"type": "step", **step_event})

            conclusion = await github_runner.stream_run_progress(
                cfg, row.github_run_id, on_step=_emit
            )

            log_text = await github_runner.fetch_run_log(cfg, row.github_run_id)
            row.raw_log_text = log_text
            passed, failed = _parse_pytest_summary(log_text)
            row.passed_count = passed
            row.failed_count = failed
            row.total_count = passed + failed
            row.status = "passed" if conclusion == "success" and failed == 0 else "failed"
            if conclusion not in ("success", "failure"):
                row.status = "error"
                row.error_message = f"GitHub conclusion: {conclusion}"
            db.add(row)
            await db.commit()

            await _finalise_run(db, row)

    except Exception as e:
        logger.exception("Re-run %s crashed", new_run_id)
        log_broker.publish(new_run_id, {"type": "error", "message": str(e)})
        try:
            async with AsyncSessionLocal() as db:
                row_q = await db.execute(
                    select(TestRunExecution).where(TestRunExecution.id == new_run_id)
                )
                row = row_q.scalar_one_or_none()
                if row is not None:
                    row.status = "error"
                    row.error_message = str(e)
                    row.finished_at = datetime.now(timezone.utc)
                    db.add(row)
                    await db.commit()
        except Exception:
            logger.exception("Failed to persist error state for re-run %s", new_run_id)
    finally:
        log_broker.publish(new_run_id, {"type": "end"})
        log_broker.close(new_run_id)


async def _run_locally(
    db: AsyncSession,
    row: TestRunExecution,
    suite: TestSuite,
) -> None:
    result = await run_suite_locally(
        run_id=str(row.id),
        suite_code=suite.code,
        framework=suite.framework,
        language=suite.language,
        staging_url=suite.url,
    )
    _apply_results_to_row(row, result)
    await _persist_scenarios(db, row, suite, result.scenarios, result.screenshots)
    db.add(row)
    await db.commit()


async def _run_via_github(
    db: AsyncSession,
    row: TestRunExecution,
    suite: TestSuite,
    auth_header: Optional[str],
) -> None:
    # Prefer project configuration from auth-service (repo_url + PAT).
    # Fall back to the legacy per-project GitHub connection and env vars.
    cfg = await GitHubConfig.from_project(str(row.project_id), auth_header)
    if cfg is None:
        cfg = GitHubConfig.from_env()
    assert cfg is not None  # detect_mode guarantees this when mode='github'

    try:
        trigger = await github_runner.trigger_run(
            cfg,
            run_id=str(row.id),
            suite_code=suite.code,
            filename=suite.filename,
            framework=suite.framework,
            staging_url=suite.url,
        )
        row.github_run_id = trigger.run_id_github
        row.github_run_url = trigger.run_url
        row.github_branch = trigger.branch
        db.add(row)
        await db.commit()

        log_broker.publish(str(row.id), {
            "type": "github",
            "run_url": trigger.run_url,
            "branch": trigger.branch,
        })

        run_id_str = str(row.id)
        def _emit(step_event: dict) -> None:
            log_broker.publish(run_id_str, {"type": "step", **step_event})

        conclusion = await github_runner.stream_run_progress(
            cfg, trigger.run_id_github, on_step=_emit
        )

        # Fetch the full log archive once the run is done.
        log_text = await github_runner.fetch_run_log(cfg, trigger.run_id_github)
        row.raw_log_text = log_text

        # Parse counts from the log just like the local runner does.
        passed, failed = _parse_pytest_summary(log_text)
        row.passed_count = passed
        row.failed_count = failed
        row.total_count = passed + failed
        row.status = "passed" if conclusion == "success" and failed == 0 else "failed"
        if conclusion not in ("success", "failure"):
            row.status = "error"
            row.error_message = f"GitHub conclusion: {conclusion}"

    except Exception as e:
        # GH path failed — try local as a graceful fallback so the demo
        # always produces a result.
        logger.warning("GitHub path failed (%s); falling back to local runner.", e)
        log_broker.publish(str(row.id), {
            "type": "step", "step": "Fetching log archive", "status": "failed",
        })
        log_broker.publish(str(row.id), {
            "type": "step",
            "step": f"GitHub path failed ({e}); falling back to local runner",
            "status": "failed",
        })
        row.mode = "local"
        db.add(row)
        await db.commit()
        await _run_locally(db, row, suite)
        return

    db.add(row)
    await db.commit()


def _apply_results_to_row(row: TestRunExecution, result: LocalRunResult) -> None:
    row.status = result.status
    row.total_count = result.total
    row.passed_count = result.passed
    row.failed_count = result.failed
    row.duration_ms = result.duration_ms
    row.raw_log_text = result.raw_log_text
    row.error_message = result.error_message
    row.artifacts_json = {
        "screenshots": [
            {"scenario": s.name, "path": s.screenshot_path, "status": s.status}
            for s in result.screenshots
        ],
    }


async def _persist_scenarios(
    db: AsyncSession,
    row: TestRunExecution,
    suite: TestSuite,
    scenarios: list[ScenarioResult],
    screenshots: list[ScenarioResult],
) -> None:
    # Per-scenario rows feed the ML risk model and the dashboard breakdown.
    for sc in scenarios:
        db.add(TestRun(
            id=uuid.uuid4(),
            project_id=row.project_id,
            suite_id=suite.id,
            execution_id=row.id,
            scenario_name=sc.name,
            flow_name=_flow_name_for(sc.name),
            framework=suite.framework,
            status=sc.status,
            duration_ms=sc.duration_ms or None,
            error_message=sc.error_message,
        ))

    for sh in screenshots:
        if not sh.screenshot_path:
            continue
        db.add(TestRunScreenshot(
            id=uuid.uuid4(),
            run_id=row.id,
            scenario=sh.name,
            label=sh.name.replace("_", " "),
            status=sh.status,
            image_path=sh.screenshot_path,
        ))


async def _finalise_run(db: AsyncSession, row: TestRunExecution) -> None:
    """Stamp finished_at, generate PDF, broadcast 'done'."""
    row.finished_at = datetime.now(timezone.utc)
    if row.started_at and row.finished_at and not row.duration_ms:
        row.duration_ms = int(
            (row.finished_at - row.started_at).total_seconds() * 1000
        )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Fetch screenshot rows for the PDF.
    shots_q = await db.execute(
        select(TestRunScreenshot).where(TestRunScreenshot.run_id == row.id)
    )
    shots = shots_q.scalars().all()

    suite_q = await db.execute(select(TestSuite).where(TestSuite.id == row.suite_id))
    suite = suite_q.scalar_one_or_none()

    try:
        pdf_path = await render_run_pdf(
            run_id=str(row.id),
            row=row,
            suite=suite,
            screenshots=[
                {
                    "scenario": s.scenario,
                    "label": s.label,
                    "status": s.status,
                    "image_path": s.image_path,
                }
                for s in shots
            ],
        )
        row.pdf_path = pdf_path
        db.add(row)
        await db.commit()
        log_broker.publish(str(row.id), {
            "type": "pdf_ready",
            "url": f"/api/v1/runs/{row.id}/report.pdf",
        })
    except Exception as e:
        logger.exception("PDF generation failed for run %s", row.id)
        log_broker.publish(str(row.id), {
            "type": "step",
            "step": f"PDF generation failed: {e}",
            "status": "failed",
        })

    log_broker.publish(str(row.id), {
        "type": "done",
        "status": row.status,
        "passed": row.passed_count,
        "failed": row.failed_count,
        "total": row.total_count,
        "duration_ms": row.duration_ms,
    })


_PYTEST_SUMMARY = re.compile(
    r"(?P<failed>\d+)\s+failed[^=]*?(?P<passed>\d+)\s+passed", re.I
)
_PYTEST_PASS_ONLY = re.compile(r"(?P<passed>\d+)\s+passed", re.I)


def _parse_pytest_summary(log: str) -> tuple[int, int]:
    m = _PYTEST_SUMMARY.search(log)
    if m:
        return int(m.group("passed")), int(m.group("failed"))
    m2 = _PYTEST_PASS_ONLY.search(log)
    if m2:
        return int(m2.group("passed")), 0
    return 0, 0
