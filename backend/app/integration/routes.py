"""
Integration routes — the API Component 2 exposes to Component 3 (Failure
Analysis & Self-Healing).

This is the mirror of how Component 1 hands us user stories: C3 pulls C2's
failed test executions (shaped to match C3's `POST /analyze` request) and C2's
known-good DOM selectors (ground truth for locator self-healing), through the
API Gateway. C3 never touches C2's database.

Endpoints (reached by C3 via the gateway as `/api/test-case` + these paths):
  GET /api/v1/projects/{project_id}/failed-tests   — failed scenarios ready to analyze
  GET /api/v1/projects/{project_id}/selectors      — approved selectors for locator repair
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Project, TestRun, DomElement

router = APIRouter(prefix="/api/v1", tags=["integration (C3)"])


# ─── Response schemas ────────────────────────────────────────────────────────
# `FailureForAnalysis` intentionally matches Component 3's POST /analyze request
# body, so C3 can forward each item straight into its pipeline with no mapping.


class FailureForAnalysis(BaseModel):
    # Fields consumed by C3's /analyze pipeline
    test_name: str
    pipeline: str
    error_message: str
    stack_trace: str
    failure_stage: str = "test"
    failure_type: str = "Test Failure"
    severity: str = "MEDIUM"
    retry_count: int = 0
    test_duration_sec: float = 0.0
    cpu_usage_pct: float = 0.0
    memory_usage_mb: float = 0.0
    is_flaky_test: int = 0
    old_locator: Optional[str] = None
    # Traceability extras — C3 may ignore these, but they let a failure be
    # traced back to the exact C2 project / suite / scenario that produced it.
    source: str = "C2"
    project_id: str
    suite_id: Optional[str] = None
    framework: Optional[str] = None
    run_status: str = "failed"
    executed_at: Optional[str] = None


class FailedTestsResponse(BaseModel):
    project_id: str
    total: int
    failures: list[FailureForAnalysis]


class SelectorOut(BaseModel):
    role: str            # semantic label, e.g. "login_button"
    selector: str        # CSS selector, e.g. "#login"
    url: str
    tag: str
    text: Optional[str] = None
    attributes: dict
    confidence: Optional[float] = None
    approved: bool


class SelectorsResponse(BaseModel):
    project_id: str
    total: int
    selectors: list[SelectorOut]


# ─── Heuristics ──────────────────────────────────────────────────────────────

# Try to pull a CSS/XPath-ish selector out of a failure message so C3's locator
# healing has an `old_locator` to repair. Best-effort — returns None if nothing
# looks like a selector.
_LOCATOR_PATTERNS = [
    re.compile(r"""locator\(\s*['"]([^'"]+)['"]""", re.IGNORECASE),
    re.compile(r"""(?:selector|locator)['"]?\s*[:=]\s*['"]([^'"]+)['"]""", re.IGNORECASE),
    re.compile(r"""(?:not found|locate element|waiting for selector|no such element)[:\s]+['"]?([#.\[/][^\s'"]+)""", re.IGNORECASE),
    re.compile(r"""(#[A-Za-z0-9_-]+|\[[^\]]+\]|//[^\s'"]+)"""),
]


def _extract_locator(message: Optional[str]) -> Optional[str]:
    if not message:
        return None
    for pattern in _LOCATOR_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group(1).strip()
    return None


def _classify_failure_type(status: str, message: Optional[str]) -> str:
    msg = (message or "").lower()
    if any(k in msg for k in ("timeout", "timed out", "waiting for")):
        return "Timeout"
    if any(k in msg for k in ("econnrefused", "connection refused", "network", "http 5", "502", "503", "504")):
        return "Network Error"
    if status == "error":
        return "Error"
    return "Test Failure"


def _to_failure(row: TestRun) -> FailureForAnalysis:
    message = row.error_message or ""
    duration_sec = round((row.duration_ms or 0) / 1000.0, 3)
    return FailureForAnalysis(
        test_name=row.scenario_name,
        pipeline=f"NextGenQA C2 / {row.framework}",
        error_message=message,
        # C2 stores one combined message per scenario; feed it as the stack
        # trace too so C3's TF-IDF has the maximum available signal.
        stack_trace=message,
        failure_type=_classify_failure_type(row.status, message),
        test_duration_sec=duration_sec,
        old_locator=_extract_locator(message),
        project_id=str(row.project_id),
        suite_id=str(row.suite_id) if row.suite_id else None,
        framework=row.framework,
        run_status=row.status,
        executed_at=row.executed_at.isoformat() if row.executed_at else None,
    )


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/failed-tests", response_model=FailedTestsResponse)
async def get_failed_tests(
    project_id: str,
    limit: int = 50,
    suite_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Failed / errored test scenarios for a project, newest first, shaped for
    Component 3's `POST /analyze` pipeline.

    C3 polls this to discover fresh failures to classify + heal. Each item is a
    ready-to-analyze failure; optionally scope to one suite with `suite_id`.
    """
    proj = await db.execute(select(Project).where(Project.id == project_id))
    if not proj.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    query = (
        select(TestRun)
        .where(TestRun.project_id == project_id)
        .where(TestRun.status.in_(["failed", "error"]))
        .order_by(TestRun.executed_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    if suite_id:
        query = query.where(TestRun.suite_id == suite_id)

    rows = (await db.execute(query)).scalars().all()
    failures = [_to_failure(r) for r in rows]
    return FailedTestsResponse(project_id=project_id, total=len(failures), failures=failures)


@router.get("/projects/{project_id}/selectors", response_model=SelectorsResponse)
async def get_selectors(
    project_id: str,
    url: Optional[str] = None,
    approved_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Known-good DOM selectors crawled/curated by C2, so C3's locator self-healing
    can propose a real stable selector (by role) instead of a placeholder.

    Filter by page `url`, or set `approved_only=true` for QA-approved selectors.
    """
    proj = await db.execute(select(Project).where(Project.id == project_id))
    if not proj.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    query = select(DomElement).where(DomElement.project_id == project_id)
    if url:
        query = query.where(DomElement.url == url)
    if approved_only:
        query = query.where(DomElement.approved.is_(True))
    query = query.order_by(DomElement.url.asc(), DomElement.role.asc())

    rows = (await db.execute(query)).scalars().all()
    selectors = [
        SelectorOut(
            role=r.role,
            selector=r.selector,
            url=r.url,
            tag=r.tag,
            text=r.text,
            attributes=r.attributes or {},
            confidence=r.confidence,
            approved=bool(r.approved),
        )
        for r in rows
    ]
    return SelectorsResponse(project_id=project_id, total=len(selectors), selectors=selectors)
